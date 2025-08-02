from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from birdnetpi.services.log_service import LogService

router = APIRouter()


@router.get("/log", response_class=PlainTextResponse)
async def get_log_content() -> PlainTextResponse:
    """Retrieve the BirdNET-Pi service logs."""
    log_service = LogService()
    logs = log_service.get_logs()
    return logs
