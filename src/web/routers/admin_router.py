from fastapi import APIRouter

router = APIRouter()


@router.get("/admin")
async def read_admin() -> dict[str, str]:
    """Return a simple message indicating the admin router is working."""
    return {"message": "Admin router is working!"}
