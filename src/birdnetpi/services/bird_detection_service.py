import logging
import math
import operator
import os

import numpy as np

try:
    import tflite_runtime.interpreter as tflite  # type: ignore[import-untyped]
except ImportError:
    import tensorflow.lite as tflite  # type: ignore[import-untyped,attr-defined]

from birdnetpi.models.config import BirdNETConfig

log = logging.getLogger(__name__)


class BirdDetectionService:
    """Manage BirdNET analysis involving TensorFlow Lite model interactions."""

    def __init__(self, config: BirdNETConfig) -> None:
        self.config = config
        self.user_dir = os.path.expanduser("~")
        self.interpreter: tflite.Interpreter | None = None  # type: ignore[name-defined]
        self.m_interpreter: tflite.Interpreter | None = None  # type: ignore[name-defined]
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
        modelpath = file_resolver.get_model_path(self.model_name or "")  # Handle None case
        if modelpath is None:
            raise ValueError(f"Model path not found for model: {self.model_name}")
        self.interpreter = tflite.Interpreter(model_path=modelpath, num_threads=2)  # type: ignore[attr-defined]
        self.interpreter.allocate_tensors()  # type: ignore[union-attr]

        if self.interpreter is None:
            raise RuntimeError("Interpreter not initialized")

        input_details = self.interpreter.get_input_details()
        output_details = self.interpreter.get_output_details()

        self.input_layer_index = input_details[0]["index"]
        if self.model_name == "BirdNET_6K_GLOBAL_MODEL":
            self.mdata_input_index = input_details[1]["index"]
        self.output_layer_index = output_details[0]["index"]

        # Get number of output classes from model
        output_shape = output_details[0]["shape"]
        num_classes = output_shape[-1]  # Last dimension is number of classes
        log.info(f"BirdDetectionService: Model has {num_classes} output classes")

        # TODO: Load actual species labels from IOC database or model metadata
        # For now, create placeholder labels to enable testing
        self.classes = [f"Species_{i:04d}" for i in range(num_classes)]

        log.info("BirdDetectionService: LOADING DONE!")

    def _load_meta_model(self) -> None:
        # Use FilePathResolver for data model path
        from birdnetpi.utils.file_path_resolver import FilePathResolver

        file_resolver = FilePathResolver()
        model_path = file_resolver.get_model_path(self.config.metadata_model)
        if model_path is None:
            raise ValueError(
                f"Model path not found for metadata model: {self.config.metadata_model}"
            )

        self.m_interpreter = tflite.Interpreter(model_path=model_path)  # type: ignore[attr-defined]
        self.m_interpreter.allocate_tensors()  # type: ignore[union-attr]

        if self.m_interpreter is None:
            raise RuntimeError("Meta interpreter not initialized")

        input_details = self.m_interpreter.get_input_details()
        output_details = self.m_interpreter.get_output_details()

        self.m_input_layer_index = input_details[0]["index"]
        self.m_output_layer_index = output_details[0]["index"]

        log.info("BirdDetectionService: loaded META model")

    def _predict_filter_raw(self, lat: float, lon: float, week: int) -> np.ndarray:
        if self.m_interpreter is None:
            self._load_meta_model()

        if self.m_interpreter is None:
            raise RuntimeError("Meta interpreter not initialized after load")

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
                threshold = self.sf_threshold if self.sf_threshold is not None else 0.03
                l_filter = np.where(l_filter >= float(threshold), l_filter, 0)

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
        if self.interpreter is None:
            raise RuntimeError("Interpreter not initialized")

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

        privacy_threshold = self.privacy_threshold if self.privacy_threshold is not None else 10.0
        human_cutoff = max(10, int(len(p_sorted) * privacy_threshold / 100.0))

        # Convert numpy float32 to Python float for consistent type handling
        return [(species, float(confidence)) for species, confidence in p_sorted[:human_cutoff]]

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

        sf_threshold = self.sf_threshold if self.sf_threshold is not None else 0.03
        filtered_results = []
        for species, confidence in raw_predictions:
            if confidence >= sf_threshold:
                filtered_results.append((species, confidence))

        return filtered_results
