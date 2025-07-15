import pytest

from birdnetpi.services.analysis_client_service import AnalysisClientService


@pytest.fixture
def analysis_client_service() -> AnalysisClientService:
    """Provide an AnalysisClientService instance for testing."""
    return AnalysisClientService()


def test_analyze_audio(analysis_client_service, capsys):
    """Should print a message indicating audio analysis"""
    audio_file = "/path/to/audio.wav"
    analysis_client_service.analyze_audio(audio_file)
    captured = capsys.readouterr()
    assert f"Analyzing audio file: {audio_file}" in captured.out


def test_get_analysis_results(analysis_client_service, capsys):
    """Should print a message and return an empty dictionary for analysis results"""
    analysis_id = "12345"
    results = analysis_client_service.get_analysis_results(analysis_id)
    captured = capsys.readouterr()
    assert f"Getting analysis results for ID: {analysis_id}" in captured.out
    assert results == {}
