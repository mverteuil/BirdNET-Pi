import datetime
import os

import librosa
import numpy as np

try:
    import tflite_runtime.interpreter as tflite
except ImportError:
    import tensorflow.lite as tflite

from birdnetpi.models.birdnet_config import BirdNETConfig


class AnalysisClientService:
    """Manages communication with the BirdNET analysis backend."""

    def __init__(self, config: BirdNETConfig) -> None:
        self.config = config
        self.interpreter = tflite.Interpreter(model_path=self.config.model)
        self.interpreter.allocate_tensors()
        self.input_details = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()
        self.labels = self._load_labels()  # Load labels from file

    def _load_labels(self) -> list[str]:
        labels_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "model", "labels_lang.txt"
        )  # Assuming labels_lang.txt is the correct labels file
        with open(labels_path) as f:
            labels = [line.strip() for line in f.readlines()]
        return labels

    def analyze_audio(self, audio_file_path: str) -> list[dict]:
        """Send an audio file for analysis to the BirdNET backend and return results."""
        results = []
        try:
            # Load and preprocess audio
            y, sr = librosa.load(
                audio_file_path, sr=self.input_details[0]["shape"][1]
            )  # Load with model's expected sample rate
            # Pad/truncate to model's expected input length
            input_length = self.input_details[0]["shape"][1]
            if len(y) < input_length:
                y = np.pad(y, (0, input_length - len(y)), "constant")
            else:
                y = y[:input_length]

            input_data = np.array(y, dtype=np.float32)[np.newaxis, :]

            # Perform inference
            self.interpreter.set_tensor(self.input_details[0]["index"], input_data)
            self.interpreter.invoke()
            output_data = self.interpreter.get_tensor(self.output_details[0]["index"])

            # Post-process results
            # Assuming output_data is a 2D array where rows are detections and
            # columns are probabilities for each species
            # This part needs to be adapted based on the actual model output format
            for _i, detection_probabilities in enumerate(output_data):
                # Get top species and confidence
                top_confidence = np.max(detection_probabilities)
                top_species_idx = np.argmax(detection_probabilities)
                species_name = self.labels[top_species_idx]

                # Apply confidence threshold from config
                if top_confidence >= self.config.confidence:
                    # Create a dummy timestamp for now, actual timestamp logic needs to be implemented
                    timestamp = datetime.datetime.now().isoformat()
                    results.append(
                        {
                            "Com_Name": species_name,
                            "DateTime": timestamp,
                            "Date": datetime.datetime.now().strftime("%Y-%m-%d"),
                            "Time": datetime.datetime.now().strftime("%H:%M:%S"),
                            "Sci_Name": species_name,  # Placeholder, ideally derived from labels
                            "Confidence": float(top_confidence),
                            "Lat": self.config.latitude,
                            "Lon": self.config.longitude,
                            "Cutoff": self.config.cutoff,
                            "Week": self.config.week,
                            "Sens": self.config.sensitivity,
                            "Overlap": self.config.overlap,
                        }
                    )
        except Exception as e:
            print(f"Error during TFLite analysis: {e}")
        return results
