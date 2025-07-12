from fastapi import APIRouter

router = APIRouter()


@router.get("/views")
async def read_views():
    return {"message": "Views router is working!"}
