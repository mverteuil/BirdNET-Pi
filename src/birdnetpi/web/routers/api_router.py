from fastapi import APIRouter

router = APIRouter()


@router.get("/api")
async def read_api() -> dict[str, str]:
    """Return a simple message indicating the API router is working."""
    return {"message": "API router is working!"}
