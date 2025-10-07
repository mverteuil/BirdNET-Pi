"""Tests for git management API endpoints in update_api_routes."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from birdnetpi.system.git_operations import GitOperationsService, GitRemote


@pytest.fixture
def mock_git_service():
    """Create a mock GitOperationsService."""
    return MagicMock(spec=GitOperationsService)


@pytest.fixture
def mock_deployment_docker():
    """Mock deployment environment as Docker."""
    with patch("birdnetpi.web.routers.update_api_routes.SystemUtils", autospec=True) as mock:
        mock.get_deployment_environment.return_value = "docker"
        yield mock


@pytest.fixture
def mock_deployment_sbc():
    """Mock deployment environment as SBC."""
    with patch("birdnetpi.web.routers.update_api_routes.SystemUtils", autospec=True) as mock:
        mock.get_deployment_environment.return_value = "sbc"
        yield mock


class TestListGitRemotes:
    """Tests for GET /api/update/git/remotes."""

    def test_list_remotes_sbc(self, app_with_temp_data, mock_deployment_sbc):
        """Should list remotes for SBC deployment."""
        client = TestClient(app_with_temp_data)

        mock_remotes = [
            GitRemote("origin", "https://github.com/user/repo.git"),
            GitRemote("upstream", "https://github.com/original/repo.git"),
        ]

        with patch(
            "birdnetpi.web.routers.update_api_routes.GitOperationsService", autospec=True
        ) as mock_service:
            mock_instance = MagicMock(spec=GitOperationsService)
            mock_instance.list_remotes.return_value = mock_remotes
            mock_service.return_value = mock_instance

            response = client.get("/api/update/git/remotes")

            assert response.status_code == 200
            data = response.json()
            assert len(data["remotes"]) == 2
            assert data["remotes"][0]["name"] == "origin"
            assert data["remotes"][0]["url"] == "https://github.com/user/repo.git"
            assert data["remotes"][1]["name"] == "upstream"

    def test_list_remotes_docker(self, app_with_temp_data, mock_deployment_docker):
        """Should return empty list for Docker deployment."""
        client = TestClient(app_with_temp_data)

        response = client.get("/api/update/git/remotes")

        assert response.status_code == 200
        data = response.json()
        assert data["remotes"] == []

    def test_list_remotes_error(self, app_with_temp_data, mock_deployment_sbc):
        """Should handle errors when listing remotes fails."""
        client = TestClient(app_with_temp_data)

        with patch(
            "birdnetpi.web.routers.update_api_routes.GitOperationsService", autospec=True
        ) as mock_service:
            mock_instance = MagicMock(spec=GitOperationsService)
            mock_instance.list_remotes.side_effect = Exception("Git error")
            mock_service.return_value = mock_instance

            response = client.get("/api/update/git/remotes")

            assert response.status_code == 500


class TestAddGitRemote:
    """Tests for POST /api/update/git/remotes."""

    def test_add_remote_sbc(self, app_with_temp_data, mock_deployment_sbc):
        """Should add new remote for SBC deployment."""
        client = TestClient(app_with_temp_data)

        with patch(
            "birdnetpi.web.routers.update_api_routes.GitOperationsService", autospec=True
        ) as mock_service:
            mock_instance = MagicMock(spec=GitOperationsService)
            mock_service.return_value = mock_instance

            response = client.post(
                "/api/update/git/remotes",
                json={"name": "upstream", "url": "https://github.com/original/repo.git"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "added successfully" in data["message"].lower()

            mock_instance.add_remote.assert_called_once_with(
                "upstream", "https://github.com/original/repo.git"
            )

    def test_add_remote_docker(self, app_with_temp_data, mock_deployment_docker):
        """Should reject adding remote for Docker deployment."""
        client = TestClient(app_with_temp_data)

        response = client.post(
            "/api/update/git/remotes",
            json={"name": "upstream", "url": "https://github.com/original/repo.git"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "not available for Docker" in data["error"]

    def test_add_remote_already_exists(self, app_with_temp_data, mock_deployment_sbc):
        """Should handle adding duplicate remote."""
        client = TestClient(app_with_temp_data)

        with patch(
            "birdnetpi.web.routers.update_api_routes.GitOperationsService", autospec=True
        ) as mock_service:
            mock_instance = MagicMock(spec=GitOperationsService)
            mock_instance.add_remote.side_effect = ValueError("Remote 'upstream' already exists")
            mock_service.return_value = mock_instance

            response = client.post(
                "/api/update/git/remotes",
                json={"name": "upstream", "url": "https://github.com/original/repo.git"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert "already exists" in data["error"]


class TestUpdateGitRemote:
    """Tests for PUT /api/update/git/remotes/{remote_name}."""

    def test_update_remote_url_only(self, app_with_temp_data, mock_deployment_sbc):
        """Should update only the URL of a remote."""
        client = TestClient(app_with_temp_data)

        with patch(
            "birdnetpi.web.routers.update_api_routes.GitOperationsService", autospec=True
        ) as mock_service:
            mock_instance = MagicMock(spec=GitOperationsService)
            mock_service.return_value = mock_instance

            response = client.put(
                "/api/update/git/remotes/origin",
                json={"name": "origin", "url": "https://github.com/new/repo.git"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

            mock_instance.update_remote.assert_called_once_with(
                "origin", "https://github.com/new/repo.git"
            )
            mock_instance.delete_remote.assert_not_called()

    def test_update_remote_rename(self, app_with_temp_data, mock_deployment_sbc):
        """Should rename non-origin remote."""
        client = TestClient(app_with_temp_data)

        with patch(
            "birdnetpi.web.routers.update_api_routes.GitOperationsService", autospec=True
        ) as mock_service:
            mock_instance = MagicMock(spec=GitOperationsService)
            mock_service.return_value = mock_instance

            response = client.put(
                "/api/update/git/remotes/upstream",
                json={"name": "fork", "url": "https://github.com/new/repo.git"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

            # Should delete old and add new
            mock_instance.delete_remote.assert_called_once_with("upstream")
            mock_instance.add_remote.assert_called_once_with(
                "fork", "https://github.com/new/repo.git"
            )

    def test_update_remote_rename_origin_blocked(self, app_with_temp_data, mock_deployment_sbc):
        """Should block renaming origin remote."""
        client = TestClient(app_with_temp_data)

        with patch(
            "birdnetpi.web.routers.update_api_routes.GitOperationsService", autospec=True
        ) as mock_service:
            mock_instance = MagicMock(spec=GitOperationsService)
            mock_service.return_value = mock_instance

            response = client.put(
                "/api/update/git/remotes/origin",
                json={"name": "new-origin", "url": "https://github.com/new/repo.git"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert "Cannot rename 'origin'" in data["error"]

    def test_update_remote_docker(self, app_with_temp_data, mock_deployment_docker):
        """Should reject updating remote for Docker deployment."""
        client = TestClient(app_with_temp_data)

        response = client.put(
            "/api/update/git/remotes/origin",
            json={"name": "origin", "url": "https://github.com/new/repo.git"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "not available for Docker" in data["error"]


class TestDeleteGitRemote:
    """Tests for DELETE /api/update/git/remotes/{remote_name}."""

    def test_delete_remote_success(self, app_with_temp_data, mock_deployment_sbc):
        """Should delete non-origin remote."""
        client = TestClient(app_with_temp_data)

        with patch(
            "birdnetpi.web.routers.update_api_routes.GitOperationsService", autospec=True
        ) as mock_service:
            mock_instance = MagicMock(spec=GitOperationsService)
            mock_service.return_value = mock_instance

            response = client.delete("/api/update/git/remotes/upstream")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "deleted successfully" in data["message"].lower()

            mock_instance.delete_remote.assert_called_once_with("upstream")

    def test_delete_origin_blocked(self, app_with_temp_data, mock_deployment_sbc):
        """Should block deleting origin remote."""
        client = TestClient(app_with_temp_data)

        with patch(
            "birdnetpi.web.routers.update_api_routes.GitOperationsService", autospec=True
        ) as mock_service:
            mock_instance = MagicMock(spec=GitOperationsService)
            mock_instance.delete_remote.side_effect = ValueError("Cannot delete 'origin' remote")
            mock_service.return_value = mock_instance

            response = client.delete("/api/update/git/remotes/origin")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert "Cannot delete" in data["error"]

    def test_delete_remote_docker(self, app_with_temp_data, mock_deployment_docker):
        """Should reject deleting remote for Docker deployment."""
        client = TestClient(app_with_temp_data)

        response = client.delete("/api/update/git/remotes/upstream")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "not available for Docker" in data["error"]


class TestListGitBranches:
    """Tests for GET /api/update/git/branches/{remote_name}."""

    def test_list_branches_sbc(self, app_with_temp_data, mock_deployment_sbc):
        """Should list branches for SBC deployment."""
        client = TestClient(app_with_temp_data)

        with patch(
            "birdnetpi.web.routers.update_api_routes.GitOperationsService", autospec=True
        ) as mock_service:
            mock_instance = MagicMock(spec=GitOperationsService)
            mock_instance.list_tags.return_value = ["v2.1.0", "v2.0.0"]
            mock_instance.list_branches.return_value = ["main", "develop"]
            mock_service.return_value = mock_instance

            response = client.get("/api/update/git/branches/origin")

            assert response.status_code == 200
            data = response.json()
            assert data["tags"] == ["v2.1.0", "v2.0.0"]
            assert data["branches"] == ["main", "develop"]

            mock_instance.list_tags.assert_called_once_with("origin")
            mock_instance.list_branches.assert_called_once_with("origin")

    def test_list_branches_docker(self, app_with_temp_data, mock_deployment_docker):
        """Should return empty list for Docker deployment."""
        client = TestClient(app_with_temp_data)

        response = client.get("/api/update/git/branches/origin")

        assert response.status_code == 200
        data = response.json()
        assert data["tags"] == []
        assert data["branches"] == []

    def test_list_branches_error(self, app_with_temp_data, mock_deployment_sbc):
        """Should handle errors when listing branches fails."""
        client = TestClient(app_with_temp_data)

        with patch(
            "birdnetpi.web.routers.update_api_routes.GitOperationsService", autospec=True
        ) as mock_service:
            mock_instance = MagicMock(spec=GitOperationsService)
            mock_instance.list_tags.side_effect = Exception("Git error")
            mock_service.return_value = mock_instance

            response = client.get("/api/update/git/branches/origin")

            assert response.status_code == 500
