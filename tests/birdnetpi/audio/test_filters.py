"""Tests for the audio filtering framework."""

import logging

import numpy as np
import pytest

from birdnetpi.audio.filters import (
    AudioFilter,
    FilterChain,
    HighPassFilter,
    LowPassFilter,
    PassThroughFilter,
)


@pytest.fixture
def test_audio_config():
    """Provide test audio configuration data."""
    return {"sample_rate": 48000, "channels": 1, "duration_seconds": 0.1, "chunk_size": 1024}


@pytest.fixture
def test_filter_config():
    """Provide test filter configuration data."""
    return {
        "highpass_cutoff": 1000.0,
        "lowpass_cutoff": 2000.0,
        "filter_order": 4,
        "high_cutoff_warning": 30000.0,  # Above Nyquist for 48kHz
    }


@pytest.fixture
def test_audio_signals(test_audio_config):
    """Provide test audio signals for filtering tests."""
    sample_rate = test_audio_config["sample_rate"]
    duration = test_audio_config["duration_seconds"]
    t = np.linspace(0, duration, int(sample_rate * duration), False)

    return {
        "low_freq_100hz": np.sin(2 * np.pi * 100 * t),
        "mid_freq_1500hz": np.sin(2 * np.pi * 1500 * t),
        "high_freq_5000hz": np.sin(2 * np.pi * 5000 * t),
        "very_high_8000hz": np.sin(2 * np.pi * 8000 * t),
        "time_array": t,
        "scale_factor": 16384,  # Use half of int16 range
    }


@pytest.fixture
def sample_int16_data():
    """Provide sample int16 audio data for basic tests."""
    return {
        "small": np.array([1000, 2000, 3000], dtype=np.int16),
        "medium": np.array([1000, 2000, 3000, -1000, -2000], dtype=np.int16),
        "zeros": np.zeros(100, dtype=np.int16),
        "wrong_dtype": np.array([0.1, 0.2, 0.3], dtype=np.float32),
    }


class TestAudioFilter:
    """Test the abstract AudioFilter base class."""

    def test_passthrough_filter_initialization(self):
        """Should initialize PassThroughFilter with correct default values."""
        filter_instance = PassThroughFilter("TestFilter", enabled=True)

        assert filter_instance.name == "TestFilter"
        assert filter_instance.enabled is True
        assert filter_instance._sample_rate is None
        assert filter_instance._channels is None

    def test_passthrough_filter_configuration(self, test_audio_config):
        """Should configure filter with audio parameters from test data."""
        filter_instance = PassThroughFilter()
        filter_instance.configure(test_audio_config["sample_rate"], test_audio_config["channels"])

        assert filter_instance._sample_rate == test_audio_config["sample_rate"]
        assert filter_instance._channels == test_audio_config["channels"]

    def test_passthrough_filter_process(self, test_audio_config, sample_int16_data):
        """Should return audio data unchanged through PassThroughFilter."""
        filter_instance = PassThroughFilter()
        filter_instance.configure(test_audio_config["sample_rate"], test_audio_config["channels"])

        # Use test data
        test_data = sample_int16_data["medium"]
        result = filter_instance.apply(test_data)

        np.testing.assert_array_equal(result, test_data)

    def test_filter_disabled_returns_original_data(self, test_audio_config, sample_int16_data):
        """Should return original data when filter is disabled."""
        filter_instance = PassThroughFilter(enabled=False)
        filter_instance.configure(test_audio_config["sample_rate"], test_audio_config["channels"])

        test_data = sample_int16_data["small"]
        result = filter_instance.apply(test_data)

        np.testing.assert_array_equal(result, test_data)

    @pytest.mark.parametrize(
        "filter_class,init_kwargs",
        [
            pytest.param(PassThroughFilter, {}, id="passthrough_filter"),
            pytest.param(HighPassFilter, {"cutoff_frequency": 1000.0}, id="highpass_filter"),
            pytest.param(LowPassFilter, {"cutoff_frequency": 2000.0}, id="lowpass_filter"),
        ],
    )
    def test_filter_not_configured_raises_error(self, filter_class, init_kwargs, sample_int16_data):
        """Should raise RuntimeError when filter is not configured."""
        filter_instance = filter_class(**init_kwargs)
        test_data = sample_int16_data["small"]

        with pytest.raises(RuntimeError, match="not configured"):
            filter_instance.apply(test_data)

    def test_filter_wrong_dtype_raises_error(self, test_audio_config, sample_int16_data):
        """Should raise ValueError when audio data has wrong dtype."""
        filter_instance = PassThroughFilter()
        filter_instance.configure(test_audio_config["sample_rate"], test_audio_config["channels"])

        # Use test data with wrong dtype
        test_data = sample_int16_data["wrong_dtype"]

        with pytest.raises(ValueError, match="Expected int16"):
            filter_instance.apply(test_data)

    def test_filter_enable_disable(self):
        """Should enable and disable filter correctly."""
        filter_instance = PassThroughFilter(enabled=False)

        assert filter_instance.enabled is False

        filter_instance.enable()
        assert filter_instance.enabled is True

        filter_instance.disable()
        assert filter_instance.enabled is False

    def test_filter_get_parameters(self):
        """Should return correct filter parameters."""
        filter_instance = PassThroughFilter("TestFilter")
        filter_instance.configure(48000, 2)

        params = filter_instance.get_parameters()

        assert params["name"] == "TestFilter"
        assert params["enabled"] is True
        assert params["type"] == "PassThroughFilter"
        assert params["sample_rate"] == 48000
        assert params["channels"] == 2

    def test_filter_string_representation(self):
        """Should include filter type, name and status in string representation."""
        filter_instance = PassThroughFilter("TestFilter", enabled=True)
        str_repr = str(filter_instance)

        assert "PassThroughFilter" in str_repr
        assert "TestFilter" in str_repr
        assert "enabled" in str_repr

    def test_abstract_filter_process_method(self):
        """Should allow calling abstract process method from subclass."""

        # Create a minimal concrete implementation that implements process
        class MinimalFilter(AudioFilter):
            def process(self, audio_data):
                # Call the abstract parent method to cover the 'pass' line
                super().process(audio_data)
                return audio_data

        filter_instance = MinimalFilter("TestFilter")
        test_data = np.array([1000, 2000, 3000], dtype=np.int16)

        # The concrete process method should call the abstract parent
        result = filter_instance.process(test_data)
        np.testing.assert_array_equal(result, test_data)


class TestFrequencyFilters:
    """Test shared behavior of HighPassFilter and LowPassFilter."""

    @pytest.mark.parametrize(
        "filter_class,cutoff_freq,filter_name,expected_order",
        [
            pytest.param(HighPassFilter, 1000.0, "TrafficFilter", 4, id="highpass_filter"),
            pytest.param(LowPassFilter, 3000.0, "SchoolFilter", 4, id="lowpass_filter"),
        ],
    )
    def test_frequency_filter_initialization(
        self, filter_class, cutoff_freq, filter_name, expected_order
    ):
        """Should initialize frequency filters with correct parameters."""
        filter_instance = filter_class(cutoff_frequency=cutoff_freq, name=filter_name)

        assert filter_instance.name == filter_name
        assert filter_instance.cutoff_frequency == cutoff_freq
        assert filter_instance.order == expected_order
        assert filter_instance._sos is None

    @pytest.mark.parametrize(
        "filter_class,cutoff_freq",
        [
            pytest.param(HighPassFilter, 1000.0, id="highpass_filter"),
            pytest.param(LowPassFilter, 3000.0, id="lowpass_filter"),
        ],
    )
    def test_frequency_filter_configuration(self, filter_class, cutoff_freq, test_audio_config):
        """Should configure frequency filters and create filter coefficients."""
        filter_instance = filter_class(cutoff_frequency=cutoff_freq)
        filter_instance.configure(test_audio_config["sample_rate"], test_audio_config["channels"])

        assert filter_instance._sample_rate == test_audio_config["sample_rate"]
        assert filter_instance._channels == test_audio_config["channels"]
        assert filter_instance._sos is not None

    @pytest.mark.parametrize(
        "filter_class,cutoff_freq,sample_rate",
        [
            pytest.param(HighPassFilter, 30000.0, 48000, id="highpass_filter"),
            pytest.param(LowPassFilter, 30000.0, 48000, id="lowpass_filter"),
        ],
    )
    def test_frequency_filter_cutoff_too_high_warning(
        self, filter_class, cutoff_freq, sample_rate, caplog
    ):
        """Should warn when cutoff frequency exceeds Nyquist limit."""
        filter_instance = filter_class(cutoff_frequency=cutoff_freq)

        with caplog.at_level(logging.WARNING):
            filter_instance.configure(sample_rate, 1)

        assert "cutoff" in caplog.text.lower()
        assert "nyquist" in caplog.text.lower()

    @pytest.mark.parametrize(
        "filter_class,cutoff_freq",
        [
            pytest.param(HighPassFilter, 1000.0, id="highpass_filter"),
            pytest.param(LowPassFilter, 2000.0, id="lowpass_filter"),
        ],
    )
    def test_frequency_filter_processing(
        self, filter_class, cutoff_freq, test_audio_config, test_audio_signals
    ):
        """Should filter frequencies and preserve output shape/dtype."""
        filter_instance = filter_class(cutoff_frequency=cutoff_freq)
        filter_instance.configure(test_audio_config["sample_rate"], test_audio_config["channels"])

        # Create test signal: low frequency (100Hz) + high frequency (5000Hz)
        low_freq = test_audio_signals["low_freq_100hz"]
        high_freq = test_audio_signals["high_freq_5000hz"]

        # Combine signals and convert to int16
        combined = (low_freq + high_freq) * test_audio_signals["scale_factor"]
        test_data = combined.astype(np.int16)

        result = filter_instance.apply(test_data)

        # Result should be different from input (filtered)
        assert not np.array_equal(result, test_data)
        # Result should have same shape and dtype
        assert result.shape == test_data.shape
        assert result.dtype == np.int16

    @pytest.mark.parametrize(
        "filter_class,cutoff_freq,order,expected_type",
        [
            pytest.param(HighPassFilter, 800.0, 6, "HighPassFilter", id="highpass_filter"),
            pytest.param(LowPassFilter, 2500.0, 8, "LowPassFilter", id="lowpass_filter"),
        ],
    )
    def test_frequency_filter_parameters(
        self, filter_class, cutoff_freq, order, expected_type, test_audio_config
    ):
        """Should return correct filter parameters after configuration."""
        filter_instance = filter_class(cutoff_frequency=cutoff_freq, order=order)
        filter_instance.configure(test_audio_config["sample_rate"], test_audio_config["channels"])

        params = filter_instance.get_parameters()

        assert params["cutoff_frequency"] == cutoff_freq
        assert params["order"] == order
        assert params["type"] == expected_type
        assert params["sample_rate"] == test_audio_config["sample_rate"]


class TestFilterChain:
    """Test the FilterChain implementation."""

    def test_filter_chain_initialization(self):
        """Should initialize FilterChain with empty filter list."""
        chain = FilterChain("TestChain")

        assert chain.name == "TestChain"
        assert len(chain.filters) == 0
        assert len(chain) == 0
        assert chain._configured is False

    def test_filter_chain_add_remove_filters(self):
        """Should add and remove filters from chain correctly."""
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
        """Should propagate configuration to all filters in chain."""
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
        """Should automatically configure filters added after chain configuration."""
        chain = FilterChain("TestChain")
        chain.configure(48000, 1)

        # Add filter after chain is configured
        filter1 = PassThroughFilter("Filter1")
        chain.add_filter(filter1)

        assert filter1._sample_rate == 48000
        assert filter1._channels == 1

    def test_filter_chain_processing(self):
        """Should process audio through all filters in sequence."""
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

    def test_filter_chain_processing__disabled_filter(self):
        """Should skip disabled filters during processing."""
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
        """Should remove all filters when cleared."""
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
        """Should show chain name and enabled filter count in string representation."""
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

    def test_filter_process__exception_returns_original_data(self, caplog):
        """Should return original data and log error when filter raises exception."""

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
