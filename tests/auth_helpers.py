"""Authentication helpers for test clients."""

from starlette.testclient import TestClient


def authenticate_sync_client(client: TestClient) -> TestClient:
    """Authenticate a sync TestClient with admin credentials.

    Args:
        client: The TestClient to authenticate

    Returns:
        The same client, now authenticated with a session cookie

    Example:
        client = TestClient(app)
        authenticated = authenticate_sync_client(client)
    """
    login_response = client.post(
        "/admin/login",
        data={"username": "admin", "password": "testpassword"},
        follow_redirects=False,
    )
    assert login_response.status_code == 303  # Successful login redirects
    return client


async def authenticate_async_client(client):
    """Authenticate an async AsyncClient with admin credentials.

    Args:
        client: The AsyncClient to authenticate

    Returns:
        The same client, now authenticated with a session cookie

    Example:
        async with AsyncClient(...) as client:
            await authenticate_async_client(client)
    """
    login_response = await client.post(
        "/admin/login",
        data={"username": "admin", "password": "testpassword"},
        follow_redirects=False,
    )
    assert login_response.status_code == 303  # Successful login redirects
    return client
