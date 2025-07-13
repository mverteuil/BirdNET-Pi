from fastapi import APIRouter

router = APIRouter()


@router.get("/admin")
async def read_admin():
    return {"message": "Admin router is working!"}
