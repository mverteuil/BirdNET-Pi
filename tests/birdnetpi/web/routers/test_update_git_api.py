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

    @pytest.mark.parametrize(
        "deployment,service_error,expected_status,expected_remotes",
        [
            (
                "sbc",
                None,
                200,
                [
                    {"name": "origin", "url": "https://github.com/user/repo.git"},
                    {"name": "upstream", "url": "https://github.com/original/repo.git"},
                ],
            ),
            ("docker", None, 200, []),
            ("sbc", Exception("Git error"), 500, None),
        ],
        ids=["sbc_lists_remotes", "docker_returns_empty", "error_returns_500"],
    )
    def test_list_remotes(
        self, app_with_temp_data, deployment, service_error, expected_status, expected_remotes
    ):
        """Should handle listing git remotes based on deployment environment."""
        client = TestClient(app_with_temp_data)

        with patch(
            "birdnetpi.web.routers.update_api_routes.SystemUtils", autospec=True
        ) as mock_utils:
            mock_utils.get_deployment_environment.return_value = deployment

            if deployment == "sbc":
                mock_remotes = [
                    GitRemote("origin", "https://github.com/user/repo.git"),
                    GitRemote("upstream", "https://github.com/original/repo.git"),
                ]
                with patch(
                    "birdnetpi.web.routers.update_api_routes.GitOperationsService", autospec=True
                ) as mock_service:
                    mock_instance = MagicMock(spec=GitOperationsService)
                    if service_error:
                        mock_instance.list_remotes.side_effect = service_error
                    else:
                        mock_instance.list_remotes.return_value = mock_remotes
                    mock_service.return_value = mock_instance

                    response = client.get("/api/update/git/remotes")
            else:
                response = client.get("/api/update/git/remotes")

            assert response.status_code == expected_status
            if expected_remotes is not None:
                data = response.json()
                assert data["remotes"] == expected_remotes


class TestAddGitRemote:
    """Tests for POST /api/update/git/remotes."""

    @pytest.mark.parametrize(
        "deployment,service_error,expected_success,expected_message_contains",
        [
            ("sbc", None, True, "added successfully"),
            ("docker", None, False, "not available for Docker"),
            ("sbc", ValueError("Remote 'upstream' already exists"), False, "already exists"),
        ],
        ids=["sbc_adds_remote", "docker_rejects", "duplicate_remote_fails"],
    )
    def test_add_remote(
        self,
        app_with_temp_data,
        deployment,
        service_error,
        expected_success,
        expected_message_contains,
    ):
        """Should handle adding git remotes based on deployment environment."""
        client = TestClient(app_with_temp_data)

        with patch(
            "birdnetpi.web.routers.update_api_routes.SystemUtils", autospec=True
        ) as mock_utils:
            mock_utils.get_deployment_environment.return_value = deployment

            if deployment == "sbc":
                with patch(
                    "birdnetpi.web.routers.update_api_routes.GitOperationsService", autospec=True
                ) as mock_service:
                    mock_instance = MagicMock(spec=GitOperationsService)
                    if service_error:
                        mock_instance.add_remote.side_effect = service_error
                    mock_service.return_value = mock_instance

                    response = client.post(
                        "/api/update/git/remotes",
                        json={"name": "upstream", "url": "https://github.com/original/repo.git"},
                    )

                    if not service_error:
                        mock_instance.add_remote.assert_called_once_with(
                            "upstream", "https://github.com/original/repo.git"
                        )
            else:
                response = client.post(
                    "/api/update/git/remotes",
                    json={"name": "upstream", "url": "https://github.com/original/repo.git"},
                )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is expected_success
            if expected_success:
                assert expected_message_contains in data["message"].lower()
            else:
                assert expected_message_contains in data["error"]


class TestUpdateGitRemote:
    """Tests for PUT /api/update/git/remotes/{remote_name}."""

    @pytest.mark.parametrize(
        "deployment,old_name,new_name,url,expected_success,expected_error,expect_update_call,expect_delete_add_calls",
        [
            ("sbc", "origin", "origin", "https://github.com/new/repo.git", True, None, True, False),
            ("sbc", "upstream", "fork", "https://github.com/new/repo.git", True, None, False, True),
            (
                "sbc",
                "origin",
                "new-origin",
                "https://github.com/new/repo.git",
                False,
                "Cannot rename 'origin'",
                False,
                False,
            ),
            (
                "docker",
                "origin",
                "origin",
                "https://github.com/new/repo.git",
                False,
                "not available for Docker",
                False,
                False,
            ),
        ],
        ids=[
            "sbc_updates_url_only",
            "sbc_renames_remote",
            "origin_rename_blocked",
            "docker_rejects",
        ],
    )
    def test_update_remote(
        self,
        app_with_temp_data,
        deployment,
        old_name,
        new_name,
        url,
        expected_success,
        expected_error,
        expect_update_call,
        expect_delete_add_calls,
    ):
        """Should handle updating git remotes based on deployment and parameters."""
        client = TestClient(app_with_temp_data)

        with patch(
            "birdnetpi.web.routers.update_api_routes.SystemUtils", autospec=True
        ) as mock_utils:
            mock_utils.get_deployment_environment.return_value = deployment

            if deployment == "sbc":
                with patch(
                    "birdnetpi.web.routers.update_api_routes.GitOperationsService", autospec=True
                ) as mock_service:
                    mock_instance = MagicMock(spec=GitOperationsService)
                    mock_service.return_value = mock_instance

                    response = client.put(
                        f"/api/update/git/remotes/{old_name}",
                        json={"name": new_name, "url": url},
                    )

                    if expect_update_call:
                        mock_instance.update_remote.assert_called_once_with(old_name, url)
                        mock_instance.delete_remote.assert_not_called()
                    elif expect_delete_add_calls:
                        mock_instance.delete_remote.assert_called_once_with(old_name)
                        mock_instance.add_remote.assert_called_once_with(new_name, url)
            else:
                response = client.put(
                    f"/api/update/git/remotes/{old_name}",
                    json={"name": new_name, "url": url},
                )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is expected_success
            if expected_error:
                assert expected_error in data["error"]


class TestDeleteGitRemote:
    """Tests for DELETE /api/update/git/remotes/{remote_name}."""

    @pytest.mark.parametrize(
        "deployment,remote_name,service_error,expected_success,expected_message_contains",
        [
            ("sbc", "upstream", None, True, "deleted successfully"),
            ("sbc", "origin", ValueError("Cannot delete 'origin' remote"), False, "Cannot delete"),
            ("docker", "upstream", None, False, "not available for Docker"),
        ],
        ids=["sbc_deletes_remote", "origin_delete_blocked", "docker_rejects"],
    )
    def test_delete_remote(
        self,
        app_with_temp_data,
        deployment,
        remote_name,
        service_error,
        expected_success,
        expected_message_contains,
    ):
        """Should handle deleting git remotes based on deployment environment."""
        client = TestClient(app_with_temp_data)

        with patch(
            "birdnetpi.web.routers.update_api_routes.SystemUtils", autospec=True
        ) as mock_utils:
            mock_utils.get_deployment_environment.return_value = deployment

            if deployment == "sbc":
                with patch(
                    "birdnetpi.web.routers.update_api_routes.GitOperationsService", autospec=True
                ) as mock_service:
                    mock_instance = MagicMock(spec=GitOperationsService)
                    if service_error:
                        mock_instance.delete_remote.side_effect = service_error
                    mock_service.return_value = mock_instance

                    response = client.delete(f"/api/update/git/remotes/{remote_name}")

                    if not service_error:
                        mock_instance.delete_remote.assert_called_once_with(remote_name)
            else:
                response = client.delete(f"/api/update/git/remotes/{remote_name}")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is expected_success
            if expected_success:
                assert expected_message_contains in data["message"].lower()
            else:
                assert expected_message_contains in data["error"]


class TestListGitBranches:
    """Tests for GET /api/update/git/branches/{remote_name}."""

    @pytest.mark.parametrize(
        "deployment,service_error,expected_status,expected_tags,expected_branches",
        [
            ("sbc", None, 200, ["v2.1.0", "v2.0.0"], ["main", "develop"]),
            ("docker", None, 200, [], []),
            ("sbc", Exception("Git error"), 500, None, None),
        ],
        ids=["sbc_lists_branches", "docker_returns_empty", "error_returns_500"],
    )
    def test_list_branches(
        self,
        app_with_temp_data,
        deployment,
        service_error,
        expected_status,
        expected_tags,
        expected_branches,
    ):
        """Should handle listing git branches based on deployment environment."""
        client = TestClient(app_with_temp_data)

        with patch(
            "birdnetpi.web.routers.update_api_routes.SystemUtils", autospec=True
        ) as mock_utils:
            mock_utils.get_deployment_environment.return_value = deployment

            if deployment == "sbc":
                with patch(
                    "birdnetpi.web.routers.update_api_routes.GitOperationsService", autospec=True
                ) as mock_service:
                    mock_instance = MagicMock(spec=GitOperationsService)
                    if service_error:
                        mock_instance.list_tags.side_effect = service_error
                    else:
                        mock_instance.list_tags.return_value = expected_tags
                        mock_instance.list_branches.return_value = expected_branches
                    mock_service.return_value = mock_instance

                    response = client.get("/api/update/git/branches/origin")

                    if not service_error:
                        mock_instance.list_tags.assert_called_once_with("origin")
                        mock_instance.list_branches.assert_called_once_with("origin")
            else:
                response = client.get("/api/update/git/branches/origin")

            assert response.status_code == expected_status
            if expected_status == 200:
                data = response.json()
                assert data["tags"] == expected_tags
                assert data["branches"] == expected_branches
