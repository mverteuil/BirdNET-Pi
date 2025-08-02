import logging

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from birdnetpi.services.log_service import LogService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/log", response_class=PlainTextResponse)
async def get_log_content() -> PlainTextResponse:
    """Retrieve the BirdNET-Pi service logs."""
    try:
        log_service = LogService()
        logs = log_service.get_logs()
        return logs
    except Exception as e:
        logger.error(f"Error retrieving logs: {e}")
        return PlainTextResponse(f"Error retrieving logs: {e!s}", status_code=500)
