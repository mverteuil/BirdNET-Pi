import logging
from unittest.mock import Mock, mock_open, patch

import numpy as np
import pytest

from birdnetpi.models.config import BirdNETConfig
from birdnetpi.services.bird_detection_service import BirdDetectionService

log = logging.getLogger(__name__)


@pytest.fixture
def mock_config():
    """Provide a mock BirdNETConfig instance."""
    mock = Mock(spec=BirdNETConfig)
    mock.model = "BirdNET_GLOBAL_6K_V2.4_Model_FP16"
    mock.privacy_threshold = 0.5
    mock.species_confidence_thresholdold = 0.1
    mock.data_model_version = 2
    return mock


@pytest.fixture
def bird_detection_service(mock_config) -> BirdDetectionService:
    """Provide a BirdDetectionService instance for testing."""
    # Patch the Interpreter class where it's imported in BirdDetectionService
    with (
        patch(
            "birdnetpi.services.bird_detection_service.tflite.Interpreter"
        ) as mock_interpreter_class,
        patch("os.path.expanduser", return_value="/mock/home"),
        patch("builtins.open", new_callable=mock_open, read_data="species1\nspecies2\n"),
        patch("os.path.join", side_effect=lambda *args: "/".join(args)),
    ):
        # Configure the mock interpreter instance
        mock_interpreter_instance = Mock()
        mock_interpreter_instance.get_input_details.return_value = [
            {"index": 0},
            {"index": 1},
        ]
        mock_interpreter_instance.get_output_details.return_value = [{"index": 0}]
        mock_interpreter_instance.get_tensor.return_value = np.array(
            [[0.9, 0.1, 0.0, 0.0]]
        )  # Ensure it's a 2D array

        mock_interpreter_class.return_value = mock_interpreter_instance

        service = BirdDetectionService(mock_config)
        service.interpreter = mock_interpreter_instance  # Ensure the service uses the mock
        service.m_interpreter = (
            mock_interpreter_instance  # Ensure the service uses the mock for meta-model
        )
        return service


def test_get_raw_prediction(bird_detection_service):
    """Should return raw predictions for an audio chunk."""
    audio_chunk = np.array([1.0, 2.0, 3.0])
    lat, lon, week, sensitivity = 0.0, 0.0, 1, 1.0

    predictions = bird_detection_service.get_raw_prediction(
        audio_chunk, lat, lon, week, sensitivity
    )

    assert isinstance(predictions, list)
    assert len(predictions) > 0
    assert isinstance(predictions[0], tuple)
    assert isinstance(predictions[0][0], str)
    assert isinstance(predictions[0][1], float)


def test_get_filtered_species_list(bird_detection_service):
    """Should return a filtered list of species based on meta-model prediction."""
    lat, lon, week = 0.0, 0.0, 1

    species_list = bird_detection_service.get_filtered_species_list(lat, lon, week)

    assert isinstance(species_list, list)
    assert len(species_list) > 0
    assert isinstance(species_list[0], str)
