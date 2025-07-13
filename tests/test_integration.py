from unittest.mock import patch

from fastapi.testclient import TestClient

from web.main import app


def test_read_main(file_path_resolver):
    with patch("web.main.FilePathResolver") as mock_resolver:
        mock_resolver.return_value = file_path_resolver
        with TestClient(app) as client:
            response = client.get("/")
            assert response.status_code == 200
            assert "BirdNET-Pi" in response.text
