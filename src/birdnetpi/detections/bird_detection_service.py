import logging
import math
import operator

import numpy as np
from ai_edge_litert.interpreter import Interpreter

from birdnetpi.config import BirdNETConfig

logger = logging.getLogger(__name__)


class BirdDetectionService:
    """Service for bird species detection using BirdNET TensorFlow Lite models.

    This service manages the loading and execution of BirdNET models for acoustic
    bird species identification. It supports both global and region-specific models
    with metadata-based filtering for location and time-aware predictions.

    The service handles:
    - Loading and managing TensorFlow Lite models for inference
    - Location and temporal filtering using metadata models
    - Converting raw audio chunks into species predictions
    - Applying confidence thresholds and sensitivity adjustments
    """

    def __init__(self, config: BirdNETConfig) -> None:
        """Initialize the bird detection service with configuration.

        Args:
            config: BirdNET configuration containing model paths, thresholds,
                   and other detection parameters
        """
        self.config = config
        self.interpreter: Interpreter | None = None  # type: ignore[name-defined]
        self.metadata_interpreter: Interpreter | None = None  # type: ignore[name-defined]
        self.predicted_species_list = []  # This list is populated by the meta-model
        self.current_week = None
        self.model_name = None
        self.privacy_threshold = None
        self.species_frequency_threshold = None
        self.metadata = None
        self.metadata_params = None

        self.input_layer_index = None
        self.output_layer_index = None
        self.metadata_input_index = None
        self.classes = []

        self.metadata_input_layer_index = None
        self.metadata_output_layer_index = None

        self._load_global_model()

    def _load_global_model(self) -> None:
        """Load the global BirdNET model and initialize configuration parameters.

        This method sets up the model name, privacy threshold, and species frequency
        threshold from the configuration, then loads the main detection model.
        """
        self.model_name = self.config.model
        self.privacy_threshold = self.config.privacy_threshold
        self.species_frequency_threshold = self.config.species_confidence_threshold
        self._load_model()

    def _load_model(self) -> None:
        """Load the main TensorFlow Lite model for bird species detection.

        This method:
        - Loads the TensorFlow Lite model from the configured path
        - Allocates tensors and prepares the interpreter
        - Extracts input/output layer indices for inference
        - Initializes the species class labels

        Raises:
            ValueError: If the model path is not found
            RuntimeError: If the interpreter fails to initialize
        """
        logger.info("BirdDetectionService: LOADING TF LITE MODEL...")

        # Use PathResolver to get model path (filename-only approach)
        from birdnetpi.system.path_resolver import PathResolver

        path_resolver = PathResolver()
        model_path = path_resolver.get_model_path(self.model_name or "")  # Handle None
        # case
        if model_path is None:
            raise ValueError(f"Model path not found for model: {self.model_name}")
        self.interpreter = Interpreter(model_path=str(model_path), num_threads=2)  # type: ignore[attr-defined]
        self.interpreter.allocate_tensors()  # type: ignore[union-attr]

        if self.interpreter is None:
            raise RuntimeError("Interpreter not initialized")

        input_details = self.interpreter.get_input_details()
        output_details = self.interpreter.get_output_details()

        self.input_layer_index = input_details[0]["index"]
        if self.model_name == "BirdNET_6K_GLOBAL_MODEL":
            self.metadata_input_index = input_details[1]["index"]
        self.output_layer_index = output_details[0]["index"]

        # Get number of output classes from model
        output_shape = output_details[0]["shape"]
        num_classes = output_shape[-1]  # Last dimension is number of classes
        logger.info(f"BirdDetectionService: Model has {num_classes} output classes")

        # Load species labels from labels file
        self.classes = self._load_species_labels(num_classes)

        logger.info("BirdDetectionService: LOADING DONE!")

    def _load_species_labels(self, expected_count: int) -> list[str]:
        """Load species labels from the labels text file.

        Args:
            expected_count: Expected number of labels to match model output classes

        Returns:
            List of species labels in format "ScientificName_CommonName"

        Notes:
            Falls back to placeholder labels if file not found or count mismatch
        """
        # Ensure model_name is set
        if not self.model_name:
            raise ValueError("Model name is not set. Cannot load species labels.")

        # Map model names to their corresponding label files
        label_files = {
            "BirdNET_GLOBAL_6K_V2.4_Model_FP16": "BirdNET_GLOBAL_6K_V2.4_Labels.txt",
            "BirdNET_6K_GLOBAL_MODEL": "BirdNET_GLOBAL_6K_V2.4_Labels.txt",  # Use same labels
        }

        labels_filename = label_files.get(self.model_name)
        if not labels_filename:
            logger.warning(
                "No labels file mapping for model %s, using placeholder labels", self.model_name
            )
            return [f"Species_{i:04d}" for i in range(expected_count)]

        # Get the labels file path from models directory
        from birdnetpi.system.path_resolver import PathResolver

        path_resolver = PathResolver()
        models_dir = path_resolver.get_models_dir()
        labels_path = models_dir / labels_filename

        if not labels_path.exists():
            logger.warning("Labels file %s not found, using placeholder labels", labels_filename)
            return [f"Species_{i:04d}" for i in range(expected_count)]

        # Load the labels using Path.read_text()
        try:
            labels_text = labels_path.read_text(encoding="utf-8")
            labels = [line.strip() for line in labels_text.splitlines() if line.strip()]

            if len(labels) != expected_count:
                logger.warning(
                    "Labels count mismatch: file has %d, model expects %d. Using available labels.",
                    len(labels),
                    expected_count,
                )
                # Pad with placeholders if needed, or truncate
                if len(labels) < expected_count:
                    labels.extend([f"Species_{i:04d}" for i in range(len(labels), expected_count)])
                else:
                    labels = labels[:expected_count]

            logger.info("Loaded %d species labels from %s", len(labels), labels_filename)
            return labels

        except Exception:
            logger.exception(
                "Error loading labels file %s, using placeholder labels", labels_filename
            )
            return [f"Species_{i:04d}" for i in range(expected_count)]

    def _load_meta_model(self) -> None:
        """Load the metadata model for location and temporal filtering.

        The metadata model predicts which species are likely to be present
        at a given location and time of year, enabling more accurate
        species identification by filtering out unlikely candidates.

        Raises:
            ValueError: If the metadata model path is not found
            RuntimeError: If the metadata interpreter fails to initialize
        """
        # Use PathResolver for data model path
        from birdnetpi.system.path_resolver import PathResolver

        path_resolver = PathResolver()
        model_path = path_resolver.get_model_path(self.config.metadata_model)
        if model_path is None:
            raise ValueError(
                f"Model path not found for metadata model: {self.config.metadata_model}"
            )

        self.metadata_interpreter = Interpreter(model_path=str(model_path))  # type: ignore[attr-defined]
        self.metadata_interpreter.allocate_tensors()  # type: ignore[union-attr]

        if self.metadata_interpreter is None:
            raise RuntimeError("Meta interpreter not initialized")

        input_details = self.metadata_interpreter.get_input_details()
        output_details = self.metadata_interpreter.get_output_details()

        self.metadata_input_layer_index = input_details[0]["index"]
        self.metadata_output_layer_index = output_details[0]["index"]

        logger.info("BirdDetectionService: loaded META model")

    def _predict_filter_raw(self, latitude: float, longitude: float, week: int) -> np.ndarray:
        """Generate species occurrence probabilities for a location and time.

        Uses the metadata model to predict which species are likely to be
        present at the specified location during the given week of the year.

        Args:
            latitude: Geographic latitude (-90 to 90)
            longitude: Geographic longitude (-180 to 180)
            week: Week of the year (1-48)

        Returns:
            Array of occurrence probabilities for each species

        Raises:
            RuntimeError: If the metadata interpreter is not initialized
        """
        if self.metadata_interpreter is None:
            self._load_meta_model()

        if self.metadata_interpreter is None:
            raise RuntimeError("Meta interpreter not initialized after load")

        sample = np.expand_dims(np.array([latitude, longitude, week], dtype="float32"), 0)

        self.metadata_interpreter.set_tensor(self.metadata_input_layer_index, sample)
        self.metadata_interpreter.invoke()

        return self.metadata_interpreter.get_tensor(self.metadata_output_layer_index)[0]

    def get_filtered_species_list(self, latitude: float, longitude: float, week: int) -> list[str]:
        """Get species likely to be present at a location and time.

        Filters the complete species list based on location and temporal
        occurrence data from the metadata model. Only species with occurrence
        probability above the threshold are included.

        Args:
            latitude: Geographic latitude (-90 to 90)
            longitude: Geographic longitude (-180 to 180)
            week: Week of the year (1-48)

        Returns:
            List of species names likely to be present at the specified
            location and time

        Notes:
            - Results are cached per week to avoid redundant predictions
            - Only applies to certain model versions that support metadata filtering
        """
        if self.model_name == "BirdNET_GLOBAL_6K_V2.4_Model_FP16":
            if week != self.current_week or not self.predicted_species_list:
                self.current_week = week
                self.predicted_species_list = []  # Clear previous list
                location_filter = self._predict_filter_raw(latitude, longitude, week)
                threshold = (
                    self.species_frequency_threshold
                    if self.species_frequency_threshold is not None
                    else 0.03
                )
                location_filter = np.where(location_filter >= float(threshold), location_filter, 0)

                # Zip with labels and filter for non-zero scores
                filtered_species = [
                    s[1] for s in zip(location_filter, self.classes, strict=False) if s[0] > 0
                ]
                self.predicted_species_list.extend(filtered_species)
        return self.predicted_species_list

    def _convert_metadata(self, m: np.ndarray) -> np.ndarray:
        """Convert location and week metadata into model-compatible format.

        This method transforms geographic coordinates and week number into a format
        suitable for the BirdNET model's metadata input layer. It applies temporal
        encoding to the week number and creates a validity mask for the metadata.

        Args:
            m: A numpy array containing [latitude, longitude, week] where:
               - latitude: Geographic latitude (-90 to 90)
               - longitude: Geographic longitude (-180 to 180)
               - week: Week of the year (1-48, representing 48 time periods throughout the year)

        Returns:
            A numpy array of length 6 containing:
            - Original latitude (or -1 if invalid)
            - Original longitude (or -1 if invalid)
            - Encoded week value using cosine transformation (or -1 if out of range)
            - Three mask values indicating validity of each metadata component

        Notes:
            - Week values 1-48 are encoded using cosine transformation to capture
              seasonal periodicity: cos(week * 7.5°) + 1
            - Invalid coordinates (latitude/longitude = -1) result in all mask values
              being set to 0
            - Week values outside 1-48 range are set to -1 with corresponding mask = 0
        """
        if 1 <= m[2] <= 48:
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
        """Apply a custom sigmoid activation function with adjustable sensitivity.

        This method applies a sigmoid transformation to convert raw model outputs
        into probability values between 0 and 1. The sensitivity parameter allows
        fine-tuning of the sigmoid curve's steepness.

        Args:
            x: Input array of raw prediction scores from the model
            sensitivity: Scaling factor for the sigmoid function (default: 1.0)
                        Higher values create a steeper curve (more decisive thresholding)
                        Lower values create a gentler curve (smoother transitions)

        Returns:
            Array of probability values between 0 and 1, same shape as input

        Notes:
            The sigmoid function is: f(x) = 1 / (1 + e^(-sensitivity * x))
            - When sensitivity = 1.0, this is the standard sigmoid function
            - Higher sensitivity makes the function more like a step function
            - Lower sensitivity makes the transition more gradual
        """
        return 1 / (1.0 + np.exp(-sensitivity * x))

    def get_raw_prediction(
        self,
        audio_chunk: np.ndarray,
        latitude: float,
        longitude: float,
        week: int,
        sensitivity: float,
    ) -> list[tuple[str, float]]:
        """Generate species predictions from an audio chunk.

        Processes a 3-second audio chunk through the BirdNET model to identify
        bird species present in the recording. Applies location and temporal
        metadata for context-aware predictions.

        Args:
            audio_chunk: Audio samples as numpy array (typically 3 seconds at 48kHz)
            latitude: Recording location latitude (-90 to 90)
            longitude: Recording location longitude (-180 to 180)
            week: Week of the year when recording was made (1-48)
            sensitivity: Detection sensitivity adjustment (0.5-1.5 typical)
                        Higher values increase sensitivity to faint sounds

        Returns:
            List of (species_name, confidence_score) tuples, sorted by
            confidence in descending order. Confidence scores range from 0 to 1.

        Raises:
            RuntimeError: If the model interpreter is not initialized
        """
        # Prepare metadata for the main model
        if self.metadata_params != [latitude, longitude, week]:
            self.metadata_params = [latitude, longitude, week]
            self.metadata = self._convert_metadata(np.array([latitude, longitude, week]))
            self.metadata = np.expand_dims(self.metadata, 0)

        # Prepare audio chunk as input signal
        sig = np.expand_dims(audio_chunk, 0)

        # Make a prediction
        if self.interpreter is None:
            raise RuntimeError("Interpreter not initialized")

        self.interpreter.set_tensor(self.input_layer_index, np.array(sig, dtype="float32"))
        if self.model_name == "BirdNET_6K_GLOBAL_MODEL":
            self.interpreter.set_tensor(
                self.metadata_input_index, np.array(self.metadata, dtype="float32")
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
        latitude: float,
        longitude: float,
        week: int,
        sensitivity: float,
    ) -> list[tuple[str, float]]:
        """Analyze audio and return filtered species detections.

        Similar to get_raw_prediction but applies additional filtering based on
        the species frequency threshold. Only returns species with confidence
        scores above the configured threshold.

        Args:
            audio_chunk: Audio samples as numpy array (typically 3 seconds at 48kHz)
            latitude: Recording location latitude (-90 to 90)
            longitude: Recording location longitude (-180 to 180)
            week: Week of the year when recording was made (1-48)
            sensitivity: Detection sensitivity adjustment (0.5-1.5 typical)

        Returns:
            List of (species_name, confidence_score) tuples for species
            exceeding the confidence threshold, sorted by confidence

        Notes:
            This is the primary method for production use as it filters out
            low-confidence predictions that are likely to be false positives.
        """
        raw_predictions = self.get_raw_prediction(
            audio_chunk,
            latitude,
            longitude,
            week,
            sensitivity,
        )

        species_frequency_threshold = (
            self.species_frequency_threshold
            if self.species_frequency_threshold is not None
            else 0.03
        )
        filtered_results = []
        for species, confidence in raw_predictions:
            if confidence >= species_frequency_threshold:
                filtered_results.append((species, confidence))

        return filtered_results
