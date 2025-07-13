from fastapi import APIRouter

router = APIRouter()


@router.get("/api")
async def read_api():
    return {"message": "API router is working!"}
