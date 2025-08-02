"""Tests for the audio filtering framework."""

import logging

import numpy as np
import pytest

from birdnetpi.utils.filters import (
    AudioFilter,
    FilterChain,
    HighPassFilter,
    LowPassFilter,
    PassThroughFilter,
)


class TestAudioFilter:
    """Test the abstract AudioFilter base class."""

    def test_passthrough_filter_initialization(self):
        """Test that PassThroughFilter initializes correctly."""
        filter_instance = PassThroughFilter("TestFilter", enabled=True)

        assert filter_instance.name == "TestFilter"
        assert filter_instance.enabled is True
        assert filter_instance._sample_rate is None
        assert filter_instance._channels is None

    def test_passthrough_filter_configuration(self):
        """Test filter configuration with audio parameters."""
        filter_instance = PassThroughFilter()
        filter_instance.configure(48000, 1)

        assert filter_instance._sample_rate == 48000
        assert filter_instance._channels == 1

    def test_passthrough_filter_process(self):
        """Test that PassThroughFilter returns data unchanged."""
        filter_instance = PassThroughFilter()
        filter_instance.configure(48000, 1)

        # Create test audio data
        test_data = np.array([1000, 2000, 3000, -1000, -2000], dtype=np.int16)
        result = filter_instance.apply(test_data)

        np.testing.assert_array_equal(result, test_data)

    def test_filter_disabled_returns_original_data(self):
        """Test that disabled filter returns original data."""
        filter_instance = PassThroughFilter(enabled=False)
        filter_instance.configure(48000, 1)

        test_data = np.array([1000, 2000, 3000], dtype=np.int16)
        result = filter_instance.apply(test_data)

        np.testing.assert_array_equal(result, test_data)

    def test_filter_not_configured_raises_error(self):
        """Test that unconfigured filter raises RuntimeError."""
        filter_instance = PassThroughFilter()
        test_data = np.array([1000, 2000, 3000], dtype=np.int16)

        with pytest.raises(RuntimeError, match="not configured"):
            filter_instance.apply(test_data)

    def test_filter_wrong_dtype_raises_error(self):
        """Test that wrong audio data type raises ValueError."""
        filter_instance = PassThroughFilter()
        filter_instance.configure(48000, 1)

        # Wrong dtype (float32 instead of int16)
        test_data = np.array([0.1, 0.2, 0.3], dtype=np.float32)

        with pytest.raises(ValueError, match="Expected int16"):
            filter_instance.apply(test_data)

    def test_filter_enable_disable(self):
        """Test filter enable/disable functionality."""
        filter_instance = PassThroughFilter(enabled=False)

        assert filter_instance.enabled is False

        filter_instance.enable()
        assert filter_instance.enabled is True

        filter_instance.disable()
        assert filter_instance.enabled is False

    def test_filter_get_parameters(self):
        """Test filter parameter retrieval."""
        filter_instance = PassThroughFilter("TestFilter")
        filter_instance.configure(48000, 2)

        params = filter_instance.get_parameters()

        assert params["name"] == "TestFilter"
        assert params["enabled"] is True
        assert params["type"] == "PassThroughFilter"
        assert params["sample_rate"] == 48000
        assert params["channels"] == 2

    def test_filter_string_representation(self):
        """Test filter string representation."""
        filter_instance = PassThroughFilter("TestFilter", enabled=True)
        str_repr = str(filter_instance)

        assert "PassThroughFilter" in str_repr
        assert "TestFilter" in str_repr
        assert "enabled" in str_repr


class TestHighPassFilter:
    """Test the HighPassFilter implementation."""

    def test_highpass_filter_initialization(self):
        """Test HighPassFilter initialization."""
        filter_instance = HighPassFilter(cutoff_frequency=500.0, name="TrafficFilter")

        assert filter_instance.name == "TrafficFilter"
        assert filter_instance.cutoff_frequency == 500.0
        assert filter_instance.order == 4
        assert filter_instance._sos is None

    def test_highpass_filter_configuration(self):
        """Test HighPassFilter configuration."""
        filter_instance = HighPassFilter(cutoff_frequency=500.0)
        filter_instance.configure(48000, 1)

        assert filter_instance._sample_rate == 48000
        assert filter_instance._channels == 1
        assert filter_instance._sos is not None

    def test_highpass_filter_processing(self):
        """Test HighPassFilter processing functionality."""
        filter_instance = HighPassFilter(cutoff_frequency=1000.0)
        filter_instance.configure(48000, 1)

        # Create test signal: low frequency (100Hz) + high frequency (5000Hz)
        duration = 0.1  # 100ms
        sample_rate = 48000
        t = np.linspace(0, duration, int(sample_rate * duration), False)

        # Low frequency component (should be attenuated)
        low_freq = np.sin(2 * np.pi * 100 * t)
        # High frequency component (should pass through)
        high_freq = np.sin(2 * np.pi * 5000 * t)

        # Combine signals and convert to int16
        combined = (low_freq + high_freq) * 16384  # Scale to use half of int16 range
        test_data = combined.astype(np.int16)

        result = filter_instance.apply(test_data)

        # Result should be different from input (filtered)
        assert not np.array_equal(result, test_data)
        # Result should have same shape and dtype
        assert result.shape == test_data.shape
        assert result.dtype == np.int16

    def test_highpass_filter_cutoff_too_high_warning(self, caplog):
        """Test warning when cutoff frequency is too high."""
        filter_instance = HighPassFilter(cutoff_frequency=30000.0)  # Higher than Nyquist for 48kHz

        with caplog.at_level(logging.WARNING):
            filter_instance.configure(48000, 1)

        assert "cutoff" in caplog.text.lower()
        assert "nyquist" in caplog.text.lower()

    def test_highpass_filter_not_configured_error(self):
        """Test error when processing without configuration."""
        filter_instance = HighPassFilter(cutoff_frequency=500.0)
        test_data = np.array([1000, 2000, 3000], dtype=np.int16)

        with pytest.raises(RuntimeError, match="not configured"):
            filter_instance.process(test_data)

    def test_highpass_filter_parameters(self):
        """Test HighPassFilter parameter retrieval."""
        filter_instance = HighPassFilter(cutoff_frequency=800.0, order=6)
        filter_instance.configure(48000, 1)

        params = filter_instance.get_parameters()

        assert params["cutoff_frequency"] == 800.0
        assert params["order"] == 6
        assert params["type"] == "HighPassFilter"


class TestLowPassFilter:
    """Test the LowPassFilter implementation."""

    def test_lowpass_filter_initialization(self):
        """Test LowPassFilter initialization."""
        filter_instance = LowPassFilter(cutoff_frequency=3000.0, name="SchoolFilter")

        assert filter_instance.name == "SchoolFilter"
        assert filter_instance.cutoff_frequency == 3000.0
        assert filter_instance.order == 4
        assert filter_instance._sos is None

    def test_lowpass_filter_configuration(self):
        """Test LowPassFilter configuration."""
        filter_instance = LowPassFilter(cutoff_frequency=3000.0)
        filter_instance.configure(48000, 1)

        assert filter_instance._sample_rate == 48000
        assert filter_instance._channels == 1
        assert filter_instance._sos is not None

    def test_lowpass_filter_processing(self):
        """Test LowPassFilter processing functionality."""
        filter_instance = LowPassFilter(cutoff_frequency=2000.0)
        filter_instance.configure(48000, 1)

        # Create test signal: low frequency (500Hz) + high frequency (8000Hz)
        duration = 0.1  # 100ms
        sample_rate = 48000
        t = np.linspace(0, duration, int(sample_rate * duration), False)

        # Low frequency component (should pass through)
        low_freq = np.sin(2 * np.pi * 500 * t)
        # High frequency component (should be attenuated)
        high_freq = np.sin(2 * np.pi * 8000 * t)

        # Combine signals and convert to int16
        combined = (low_freq + high_freq) * 16384  # Scale to use half of int16 range
        test_data = combined.astype(np.int16)

        result = filter_instance.apply(test_data)

        # Result should be different from input (filtered)
        assert not np.array_equal(result, test_data)
        # Result should have same shape and dtype
        assert result.shape == test_data.shape
        assert result.dtype == np.int16

    def test_lowpass_filter_parameters(self):
        """Test LowPassFilter parameter retrieval."""
        filter_instance = LowPassFilter(cutoff_frequency=2500.0, order=8)
        filter_instance.configure(48000, 1)

        params = filter_instance.get_parameters()

        assert params["cutoff_frequency"] == 2500.0
        assert params["order"] == 8
        assert params["type"] == "LowPassFilter"


class TestFilterChain:
    """Test the FilterChain implementation."""

    def test_filter_chain_initialization(self):
        """Test FilterChain initialization."""
        chain = FilterChain("TestChain")

        assert chain.name == "TestChain"
        assert len(chain.filters) == 0
        assert len(chain) == 0
        assert chain._configured is False

    def test_filter_chain_add_remove_filters(self):
        """Test adding and removing filters from chain."""
        chain = FilterChain("TestChain")
        filter1 = PassThroughFilter("Filter1")
        filter2 = PassThroughFilter("Filter2")

        # Add filters
        chain.add_filter(filter1)
        chain.add_filter(filter2)

        assert len(chain) == 2
        assert chain.get_filter_names() == ["Filter1", "Filter2"]

        # Remove filter
        removed = chain.remove_filter("Filter1")
        assert removed is True
        assert len(chain) == 1
        assert chain.get_filter_names() == ["Filter2"]

        # Try to remove non-existent filter
        removed = chain.remove_filter("NonExistent")
        assert removed is False

    def test_filter_chain_configuration(self):
        """Test FilterChain configuration propagates to filters."""
        chain = FilterChain("TestChain")
        filter1 = PassThroughFilter("Filter1")
        filter2 = PassThroughFilter("Filter2")

        chain.add_filter(filter1)
        chain.add_filter(filter2)
        chain.configure(48000, 2)

        assert chain._configured is True
        assert filter1._sample_rate == 48000
        assert filter1._channels == 2
        assert filter2._sample_rate == 48000
        assert filter2._channels == 2

    def test_filter_chain_configuration_after_add(self):
        """Test that filters added after configuration are automatically configured."""
        chain = FilterChain("TestChain")
        chain.configure(48000, 1)

        # Add filter after chain is configured
        filter1 = PassThroughFilter("Filter1")
        chain.add_filter(filter1)

        assert filter1._sample_rate == 48000
        assert filter1._channels == 1

    def test_filter_chain_processing(self):
        """Test FilterChain processes audio through all filters."""
        chain = FilterChain("TestChain")

        # Create mock filters that modify data in a predictable way
        class AddOneFilter(AudioFilter):
            def __init__(self, name):
                super().__init__(name)

            def process(self, audio_data):
                return audio_data + 1

        filter1 = AddOneFilter("AddOne1")
        filter2 = AddOneFilter("AddOne2")

        chain.add_filter(filter1)
        chain.add_filter(filter2)
        chain.configure(48000, 1)

        test_data = np.array([100, 200, 300], dtype=np.int16)
        result = chain.process(test_data)

        # Should have added 1 twice (once per filter)
        expected = np.array([102, 202, 302], dtype=np.int16)
        np.testing.assert_array_equal(result, expected)

    def test_filter_chain_processing_with_disabled_filter(self):
        """Test FilterChain skips disabled filters."""
        chain = FilterChain("TestChain")

        class AddTenFilter(AudioFilter):
            def __init__(self, name):
                super().__init__(name)

            def process(self, audio_data):
                return audio_data + 10

        filter1 = AddTenFilter("AddTen1")
        filter2 = AddTenFilter("AddTen2")
        filter2.disable()  # Disable second filter

        chain.add_filter(filter1)
        chain.add_filter(filter2)
        chain.configure(48000, 1)

        test_data = np.array([100, 200, 300], dtype=np.int16)
        result = chain.process(test_data)

        # Should have added 10 only once (second filter disabled)
        expected = np.array([110, 210, 310], dtype=np.int16)
        np.testing.assert_array_equal(result, expected)

    def test_filter_chain_clear(self):
        """Test FilterChain clear functionality."""
        chain = FilterChain("TestChain")
        filter1 = PassThroughFilter("Filter1")
        filter2 = PassThroughFilter("Filter2")

        chain.add_filter(filter1)
        chain.add_filter(filter2)
        assert len(chain) == 2

        chain.clear()
        assert len(chain) == 0
        assert chain.get_filter_names() == []

    def test_filter_chain_string_representation(self):
        """Test FilterChain string representation."""
        chain = FilterChain("TestChain")
        filter1 = PassThroughFilter("Filter1", enabled=True)
        filter2 = PassThroughFilter("Filter2", enabled=False)

        chain.add_filter(filter1)
        chain.add_filter(filter2)

        str_repr = str(chain)
        assert "TestChain" in str_repr
        assert "1/2" in str_repr  # 1 enabled out of 2 total


class TestFilterErrorHandling:
    """Test error handling in filter framework."""

    def test_filter_process_exception_returns_original_data(self, caplog):
        """Test that filter exceptions return original data and log error."""

        class BrokenFilter(AudioFilter):
            def __init__(self):
                super().__init__("BrokenFilter")

            def process(self, audio_data):
                raise ValueError("Simulated filter error")

        filter_instance = BrokenFilter()
        filter_instance.configure(48000, 1)

        test_data = np.array([1000, 2000, 3000], dtype=np.int16)

        with caplog.at_level(logging.ERROR):
            result = filter_instance.apply(test_data)

        # Should return original data on error
        np.testing.assert_array_equal(result, test_data)
        # Should log the error
        assert "Error in filter" in caplog.text
        assert "BrokenFilter" in caplog.text


@pytest.fixture(autouse=True)
def setup_logging(caplog):
    """Set up logging for tests."""
    caplog.set_level(logging.DEBUG, logger="birdnetpi.utils.filters")
