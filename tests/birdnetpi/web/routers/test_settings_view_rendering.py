"""Tests for settings view rendering to validate route-to-template data passing."""

from unittest.mock import MagicMock

import pytest
from jinja2 import Environment, FileSystemLoader, TemplateSyntaxError
from jinja2.exceptions import UndefinedError
from starlette.requests import Request

from birdnetpi.audio.devices import AudioDevice
from birdnetpi.config import BirdNETConfig


class TestSettingsViewRendering:
    """Settings views render correctly with proper data."""

    @pytest.fixture
    def template_env(self, repo_root):
        """Create Jinja2 environment for template testing."""
        template_dir = repo_root / "src" / "birdnetpi" / "web" / "templates"
        env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)
        env.globals["get_update_status"] = lambda: None
        env.globals["update_available"] = lambda: False
        env.globals["show_development_warning"] = lambda: False
        env.globals["url_for"] = lambda name, **kwargs: f"/{name}"
        env.globals["_"] = lambda x, **kwargs: x % kwargs if kwargs else x
        env.globals["gettext"] = env.globals["_"]
        env.globals["ngettext"] = lambda singular, plural, n: plural if n != 1 else singular
        return env

    @pytest.fixture
    def mock_request(self):
        """Create a mock request object."""
        request = MagicMock(spec=Request)
        return request

    @pytest.fixture
    def sample_config(self):
        """Create a sample configuration for testing."""
        return BirdNETConfig(
            site_name="Test Site",
            latitude=45.5,
            longitude=-73.6,
            sensitivity_setting=1.25,
            species_confidence_threshold=0.7,
            audio_device_index=0,
            sample_rate=48000,
            audio_channels=1,
            audio_overlap=0.5,
            model="BirdNET_GLOBAL_6K_V2.4_Model_FP16",
            metadata_model="BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16",
        )

    @pytest.fixture
    def sample_audio_devices(self):
        """Create sample audio devices."""
        return [
            AudioDevice(
                name="USB Audio Device",
                index=0,
                host_api_index=0,
                max_input_channels=2,
                max_output_channels=0,
                default_low_input_latency=0.01,
                default_low_output_latency=0.0,
                default_high_input_latency=0.04,
                default_high_output_latency=0.0,
                default_samplerate=48000.0,
            ),
            AudioDevice(
                name="Built-in Microphone",
                index=1,
                host_api_index=0,
                max_input_channels=1,
                max_output_channels=0,
                default_low_input_latency=0.02,
                default_low_output_latency=0.0,
                default_high_input_latency=0.08,
                default_high_output_latency=0.0,
                default_samplerate=44100.0,
            ),
        ]

    def test_settings_template_syntax_valid(self, template_env):
        """Should settings template has valid Jinja2 syntax."""
        try:
            template = template_env.get_template("admin/settings.html.j2")
            assert template is not None
        except TemplateSyntaxError as e:
            pytest.fail(f"Template syntax error in settings.html.j2: {e}")

    def test_settings_template_renders_with_data(
        self, template_env, mock_request, sample_config, sample_audio_devices
    ):
        """Should render settings template with actual data correctly."""
        template = template_env.get_template("admin/settings.html.j2")
        html = template.render(
            request=mock_request,
            config=sample_config,
            audio_devices=sample_audio_devices,
            model_files=["BirdNET_GLOBAL_6K_V2.4_Model_FP16"],
            metadata_model_files=["BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16"],
            system_status={"device_name": "Test Device"},
            language="en",
            page_name="Settings",
            active_page="settings",
        )
        assert "Test Site" in html
        assert "45.5" in html
        assert "-73.6" in html
        assert "USB Audio Device" in html
        assert "Built-in Microphone" in html
        assert "<form" in html
        assert 'method="post"' in html

    def test_settings_template_handles_no_audio_devices(
        self, template_env, mock_request, sample_config
    ):
        """Should handle case with no audio devices in settings template."""
        template = template_env.get_template("admin/settings.html.j2")
        html = template.render(
            request=mock_request,
            config=sample_config,
            audio_devices=[],
            model_files=["BirdNET_GLOBAL_6K_V2.4_Model_FP16"],
            metadata_model_files=["BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16"],
            system_status={"device_name": "Test Device"},
            language="en",
        )
        assert "No audio devices detected" in html
        assert "Check your audio system configuration" in html

    def test_settings_template_handles_missing_config_fields(
        self, template_env, mock_request, sample_audio_devices
    ):
        """Should handle missing or None config fields gracefully in template."""
        config = BirdNETConfig()
        try:
            template = template_env.get_template("admin/settings.html.j2")
            html = template.render(
                request=mock_request,
                config=config,
                audio_devices=sample_audio_devices,
                model_files=["BirdNET_GLOBAL_6K_V2.4_Model_FP16"],
                metadata_model_files=["BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16"],
                system_status={"device_name": "Test Device"},
                language="en",
            )
            assert html is not None
        except UndefinedError as e:
            pytest.fail(f"Template failed to handle missing/None config fields: {e}")

    def test_settings_template_all_form_inputs_present(
        self, template_env, mock_request, sample_config, sample_audio_devices
    ):
        """Should render all required form inputs in the template."""
        template = template_env.get_template("admin/settings.html.j2")
        html = template.render(
            request=mock_request,
            config=sample_config,
            audio_devices=sample_audio_devices,
            model_files=["BirdNET_GLOBAL_6K_V2.4_Model_FP16"],
            metadata_model_files=["BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16"],
            system_status={"device_name": "Test Device"},
            language="en",
        )
        assert 'name="site_name"' in html
        assert 'name="model"' in html
        assert 'name="metadata_model"' in html
        assert 'name="species_confidence_threshold"' in html
        assert 'name="sensitivity"' in html
        assert 'name="audio_device_index"' in html
        assert 'name="latitude"' in html
        assert 'name="longitude"' in html
        assert 'name="sample_rate"' in html
        assert 'name="audio_channels"' in html

    def test_settings_template_javascript_functions_present(
        self, template_env, mock_request, sample_config, sample_audio_devices
    ):
        """Should include all required JavaScript functions in the template."""
        template = template_env.get_template("admin/settings.html.j2")
        html = template.render(
            request=mock_request,
            config=sample_config,
            audio_devices=sample_audio_devices,
            model_files=["BirdNET_GLOBAL_6K_V2.4_Model_FP16"],
            metadata_model_files=["BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16"],
            system_status={"device_name": "Test Device"},
            language="en",
        )
        assert "function selectOption" in html
        assert "function selectAudioDevice" in html
        assert "function updateSliderValue" in html

    def test_all_template_blocks_properly_closed(self, template_env):
        """Should all Jinja2 blocks are properly closed."""
        template_path = template_env.loader.searchpath[0] + "/admin/settings.html.j2"
        with open(template_path) as f:
            content = f.read()
        if_count = content.count("{% if")
        endif_count = content.count("{% endif")
        for_count = content.count("{% for")
        endfor_count = content.count("{% endfor")
        block_count = content.count("{% block")
        endblock_count = content.count("{% endblock")
        assert if_count == endif_count, f"Mismatched if/endif: {if_count} vs {endif_count}"
        assert for_count == endfor_count, f"Mismatched for/endfor: {for_count} vs {endfor_count}"
        assert block_count == endblock_count, (
            f"Mismatched block/endblock: {block_count} vs {endblock_count}"
        )

    def test_template_escapes_user_input(self, template_env, mock_request, sample_audio_devices):
        """Should template properly escapes user input to prevent XSS."""
        config = BirdNETConfig(
            site_name="<script>alert('XSS')</script>", latitude=45.5, longitude=-73.6
        )
        template = template_env.get_template("admin/settings.html.j2")
        html = template.render(
            request=mock_request,
            config=config,
            audio_devices=sample_audio_devices,
            model_files=["BirdNET_GLOBAL_6K_V2.4_Model_FP16"],
            metadata_model_files=["BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16"],
            system_status={"device_name": "Test Device"},
            language="en",
        )
        assert "&lt;script&gt;" in html or "&amp;lt;script&amp;gt;" in html
        assert "<script>alert" not in html
