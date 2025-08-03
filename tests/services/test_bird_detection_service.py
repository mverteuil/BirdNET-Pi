import logging

import numpy as np
import pytest

from birdnetpi.services.bird_detection_service import BirdDetectionService

log = logging.getLogger(__name__)


@pytest.fixture
def bird_detection_service(test_config) -> BirdDetectionService:
    """Provide a BirdDetectionService instance for testing using real models."""
    service = BirdDetectionService(test_config)
    return service


def test_get_raw_prediction(bird_detection_service):
    """Should return raw predictions for an audio chunk."""
    # Create a realistic audio chunk (3 seconds at 48kHz sample rate)
    audio_chunk = np.random.random(144000).astype(np.float32)
    lat, lon, week, sensitivity = 40.7128, -74.0060, 1, 1.0

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
    lat, lon, week = 40.7128, -74.0060, 1

    species_list = bird_detection_service.get_filtered_species_list(lat, lon, week)

    assert isinstance(species_list, list)
    # Note: The filtered species list may be empty if the meta-model doesn't predict
    # any species for the given location/week, which is valid behavior
    if len(species_list) > 0:
        assert isinstance(species_list[0], str)
