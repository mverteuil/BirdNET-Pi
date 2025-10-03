import logging

import numpy as np
import pytest

from birdnetpi.detections.birdnet import BirdDetectionService

log = logging.getLogger(__name__)


@pytest.fixture
def bird_detection_service(test_config, path_resolver, mocker):
    """Provide a BirdDetectionService instance for testing using real models."""
    # Mock PathResolver to use our test resolver
    # It's imported inside the _load_model method
    mocker.patch(
        "birdnetpi.system.path_resolver.PathResolver",
        return_value=path_resolver,
    )

    service = BirdDetectionService(test_config)
    return service


def test_get_raw_prediction(bird_detection_service):
    """Should return raw predictions for an audio chunk."""
    # Create a realistic audio chunk (3 seconds at 48kHz sample rate)
    audio_chunk = np.random.random(144000).astype(np.float32)
    latitude, longitude, week, sensitivity = 63.4591, -19.3647, 1, 1.0

    predictions = bird_detection_service.get_raw_prediction(
        audio_chunk, latitude, longitude, week, sensitivity
    )

    assert isinstance(predictions, list)
    assert len(predictions) > 0
    assert isinstance(predictions[0], tuple)
    assert isinstance(predictions[0][0], str)
    assert isinstance(predictions[0][1], float)


def test_get_filtered_species_list(bird_detection_service):
    """Should return a filtered list of species based on meta-model prediction."""
    latitude, longitude, week = 63.4591, -19.3647, 1

    species_list = bird_detection_service.get_filtered_species_list(latitude, longitude, week)

    assert isinstance(species_list, list)
    # Note: The filtered species list may be empty if the meta-model doesn't predict
    # any species for the given location/week, which is valid behavior
    if len(species_list) > 0:
        assert isinstance(species_list[0], str)
