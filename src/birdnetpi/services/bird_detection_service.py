import datetime
import logging
import math
import operator
import os

import numpy as np

try:
    import tflite_runtime.interpreter as tflite
except ImportError:
    import tensorflow.lite as tflite

from birdnetpi.models.config import BirdNETConfig

log = logging.getLogger(__name__)


class BirdDetectionService:
    """Manage BirdNET analysis involving TensorFlow Lite model interactions."""

    def __init__(self, config: BirdNETConfig) -> None:
        self.config = config
        self.user_dir = os.path.expanduser("~")
        self.interpreter = None
        self.m_interpreter = None
        self.predicted_species_list = []  # This list is populated by the meta-model
        self.current_week = None
        self.model_name = None
        self.privacy_threshold = None
        self.sf_threshold = None
        self.mdata = None
        self.mdata_params = None

        self.input_layer_index = None
        self.output_layer_index = None
        self.mdata_input_index = None
        self.classes = []

        self.m_input_layer_index = None
        self.m_output_layer_index = None

        self._load_global_model()

    def _load_global_model(self) -> None:
        self.model_name = self.config.model
        self.privacy_threshold = self.config.privacy_threshold
        self.sf_threshold = self.config.species_confidence_threshold
        self._load_model()

    def _load_model(self) -> None:
        log.info("BirdDetectionService: LOADING TF LITE MODEL...")

        # Use FilePathResolver to get model path (filename-only approach)
        from birdnetpi.utils.file_path_resolver import FilePathResolver

        file_resolver = FilePathResolver()
        modelpath = file_resolver.get_model_path(self.model_name)
        self.interpreter = tflite.Interpreter(model_path=modelpath, num_threads=2)
        self.interpreter.allocate_tensors()

        input_details = self.interpreter.get_input_details()
        output_details = self.interpreter.get_output_details()

        self.input_layer_index = input_details[0]["index"]
        if self.model_name == "BirdNET_6K_GLOBAL_MODEL":
            self.mdata_input_index = input_details[1]["index"]
        self.output_layer_index = output_details[0]["index"]

        self.classes = []
        # Use FilePathResolver for labels path
        file_resolver = FilePathResolver()
        labelspath = file_resolver.get_model_path("labels.txt")
        with open(labelspath) as lfile:
            for line in lfile.readlines():
                self.classes.append(line.replace("\n", ""))

        log.info("BirdDetectionService: LOADING DONE!")

    def _load_meta_model(self) -> None:
        if self.config.data_model_version == 2:
            data_model = "BirdNET_GLOBAL_6K_V2.4_MData_Model_V2_FP16.tflite"
        else:
            data_model = "BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16.tflite"

        # Use FilePathResolver for data model path
        from birdnetpi.utils.file_path_resolver import FilePathResolver

        file_resolver = FilePathResolver()
        self.m_interpreter = tflite.Interpreter(model_path=file_resolver.get_model_path(data_model))
        self.m_interpreter.allocate_tensors()

        input_details = self.m_interpreter.get_input_details()
        output_details = self.m_interpreter.get_output_details()

        self.m_input_layer_index = input_details[0]["index"]
        self.m_output_layer_index = output_details[0]["index"]

        log.info("BirdDetectionService: loaded META model")

    def _predict_filter_raw(self, lat: float, lon: float, week: int) -> np.ndarray:
        if self.m_interpreter is None:
            self._load_meta_model()

        sample = np.expand_dims(np.array([lat, lon, week], dtype="float32"), 0)

        self.m_interpreter.set_tensor(self.m_input_layer_index, sample)
        self.m_interpreter.invoke()

        return self.m_interpreter.get_tensor(self.m_output_layer_index)[0]

    def get_filtered_species_list(self, lat: float, lon: float, week: int) -> list[str]:
        """Return a list of species predicted by the meta-model for a given location and week."""
        if self.model_name == "BirdNET_GLOBAL_6K_V2.4_Model_FP16":
            if week != self.current_week or not self.predicted_species_list:
                self.current_week = week
                self.predicted_species_list = []  # Clear previous list
                l_filter = self._predict_filter_raw(lat, lon, week)
                l_filter = np.where(l_filter >= float(self.sf_threshold), l_filter, 0)

                # Zip with labels and filter for non-zero scores
                filtered_species = [
                    s[1] for s in zip(l_filter, self.classes, strict=False) if s[0] > 0
                ]
                self.predicted_species_list.extend(filtered_species)
        return self.predicted_species_list

    def _convert_metadata(self, m: np.ndarray) -> np.ndarray:
        if m[2] >= 1 and m[2] <= 48:
            m[2] = math.cos(math.radians(m[2] * 7.5)) + 1
        else:
            m[2] = -1

        mask = np.ones((3,))
        if m[0] == -1 or m[1] == -1:
            mask = np.zeros((3,))
        if m[2] == -1:
            mask[2] = 0.0

        return np.concatenate([m, mask])

    def _custom_sigmoid(self, x: np.ndarray, sensitivity: float = 1.0) -> np.ndarray:
        return 1 / (1.0 + np.exp(-sensitivity * x))

    def get_raw_prediction(
        self,
        audio_chunk: np.ndarray,
        lat: float,
        lon: float,
        week: int,
        sensitivity: float,
    ) -> list[tuple[str, float]]:
        """Perform raw prediction on an audio chunk."""
        # Prepare metadata for the main model
        if self.mdata_params != [lat, lon, week]:
            self.mdata_params = [lat, lon, week]
            self.mdata = self._convert_metadata(np.array([lat, lon, week]))
            self.mdata = np.expand_dims(self.mdata, 0)

        # Prepare audio chunk as input signal
        sig = np.expand_dims(audio_chunk, 0)

        # Make a prediction
        self.interpreter.set_tensor(self.input_layer_index, np.array(sig, dtype="float32"))
        if self.model_name == "BirdNET_6K_GLOBAL_MODEL":
            self.interpreter.set_tensor(
                self.mdata_input_index, np.array(self.mdata, dtype="float32")
            )
        self.interpreter.invoke()
        prediction = self.interpreter.get_tensor(self.output_layer_index)[0]

        # Apply custom sigmoid
        p_sigmoid = self._custom_sigmoid(prediction, sensitivity)

        # Get label and scores for pooled predictions
        p_labels = dict(zip(self.classes, p_sigmoid, strict=False))

        # Sort by score
        p_sorted = sorted(p_labels.items(), key=operator.itemgetter(1), reverse=True)

        human_cutoff = max(10, int(len(p_sorted) * self.privacy_threshold / 100.0))

        log.debug("BirdDetectionService: DATABASE SIZE: %d", len(p_sorted))
        log.debug("BirdDetectionService: HUMAN-CUTOFF AT: %d", human_cutoff)

        for i in range(min(10, len(p_sorted))):
            if p_sorted[i][0] == "Human_Human":
                with open(os.path.join(self.user_dir, "BirdNET-Pi/HUMAN.txt"), "a") as rfile:
                    rfile.write(
                        str(datetime.datetime.now())
                        + str(p_sorted[i])
                        + " "
                        + str(human_cutoff)
                        + "\n"
                    )

        return p_sorted[:human_cutoff]

    def get_analysis_results(
        self,
        audio_chunk: np.ndarray,
        lat: float,
        lon: float,
        week: int,
        sensitivity: float,
    ) -> list[tuple[str, float]]:
        """Perform analysis on an audio chunk and return filtered (species, confidence) pairs."""
        raw_predictions = self.get_raw_prediction(audio_chunk, lat, lon, week, sensitivity)

        filtered_results = []
        for species, confidence in raw_predictions:
            if confidence >= self.sf_threshold:
                filtered_results.append((species, confidence))

        return filtered_results
