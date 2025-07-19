from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from birdnetpi.managers.log_manager import LogManager

router = APIRouter()


@router.get("/log", response_class=PlainTextResponse)
async def get_log_content() -> PlainTextResponse:
    """Retrieve the BirdNET-Pi service logs."""
    log_manager = LogManager()
    logs = log_manager.get_logs()
    return logs
