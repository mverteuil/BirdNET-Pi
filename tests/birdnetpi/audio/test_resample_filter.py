"""Tests for the audio resampling filter."""

import numpy as np
import pytest

from birdnetpi.audio.filters import ResampleFilter


class TestResampleFilter:
    """Tests for the ResampleFilter class."""

    def test_resample_filter_initialization(self):
        """Test ResampleFilter initialization."""
        filter_obj = ResampleFilter(target_sample_rate=48000, name="TestResample")
        assert filter_obj.target_sample_rate == 48000
        assert filter_obj.name == "TestResample"
        assert filter_obj.enabled is True
        assert filter_obj.source_sample_rate is None

    def test_resample_filter_configuration(self):
        """Test ResampleFilter configuration."""
        filter_obj = ResampleFilter(target_sample_rate=48000)
        filter_obj.configure(sample_rate=44100, channels=1)

        assert filter_obj.source_sample_rate == 44100
        assert filter_obj._sample_rate == 44100
        assert filter_obj._channels == 1

    def test_resample_filter_passthrough_when_rates_match(self):
        """Test that filter passes through audio when sample rates match."""
        filter_obj = ResampleFilter(target_sample_rate=48000)
        filter_obj.configure(sample_rate=48000, channels=1)

        # Create test audio (1 second at 48kHz)
        test_audio = np.random.randint(-32768, 32767, 48000, dtype=np.int16)

        # Process audio
        result = filter_obj.process(test_audio)

        # Should return the exact same array (not a copy)
        assert result is test_audio
        assert len(result) == 48000

    def test_resample_filter_upsampling(self):
        """Test resampling from lower to higher sample rate."""
        filter_obj = ResampleFilter(target_sample_rate=48000)
        filter_obj.configure(sample_rate=44100, channels=1)

        # Create test audio (0.1 second at 44.1kHz)
        test_audio = np.random.randint(-32768, 32767, 4410, dtype=np.int16)

        # Process audio
        result = filter_obj.process(test_audio)

        # Should have more samples after upsampling
        # 4410 samples at 44.1kHz = 0.1 seconds
        # 0.1 seconds at 48kHz = 4800 samples
        expected_samples = int(4410 * (48000 / 44100))
        assert abs(len(result) - expected_samples) <= 1  # Allow for rounding
        assert result.dtype == np.int16

    def test_resample_filter_downsampling(self):
        """Test resampling from higher to lower sample rate."""
        filter_obj = ResampleFilter(target_sample_rate=22050)
        filter_obj.configure(sample_rate=44100, channels=1)

        # Create test audio (0.1 second at 44.1kHz)
        test_audio = np.random.randint(-32768, 32767, 4410, dtype=np.int16)

        # Process audio
        result = filter_obj.process(test_audio)

        # Should have fewer samples after downsampling
        # 4410 samples at 44.1kHz = 0.1 seconds
        # 0.1 seconds at 22.05kHz = 2205 samples
        expected_samples = int(4410 * (22050 / 44100))
        assert abs(len(result) - expected_samples) <= 1  # Allow for rounding
        assert result.dtype == np.int16

    def test_resample_filter_not_configured_error(self):
        """Test that filter raises error when not configured."""
        filter_obj = ResampleFilter(target_sample_rate=48000)
        test_audio = np.random.randint(-32768, 32767, 1000, dtype=np.int16)

        with pytest.raises(RuntimeError, match="not configured"):
            filter_obj.process(test_audio)

    def test_resample_filter_parameters(self):
        """Test getting filter parameters."""
        filter_obj = ResampleFilter(target_sample_rate=48000, name="TestResample")
        filter_obj.configure(sample_rate=44100, channels=2)

        params = filter_obj.get_parameters()
        assert params["name"] == "TestResample"
        assert params["enabled"] is True
        assert params["type"] == "ResampleFilter"
        assert params["target_sample_rate"] == 48000
        assert params["source_sample_rate"] == 44100
        assert params["sample_rate"] == 44100
        assert params["channels"] == 2
