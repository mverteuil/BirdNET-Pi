import pytest
from fastapi.testclient import TestClient

from birdnetpi.web.routers.admin_router import router


@pytest.fixture
def client():
    """Create a test client for the admin router."""
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestAdminRouter:
    """Test the admin router endpoints."""

    def test_read_admin_endpoint(self, client):
        """Should return admin working message."""
        response = client.get("/admin")

        assert response.status_code == 200
        assert response.json() == {"message": "Admin router is working!"}

    def test_admin_endpoint_returns_json(self, client):
        """Should return JSON content type."""
        response = client.get("/admin")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

    def test_admin_router_exists(self):
        """Should have a router object."""
        from birdnetpi.web.routers.admin_router import router

        assert router is not None
        assert hasattr(router, "routes")
        assert len(router.routes) > 0
