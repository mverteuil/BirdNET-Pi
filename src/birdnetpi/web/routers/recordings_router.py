from fastapi import APIRouter, Depends, Request

from birdnetpi.managers.data_manager import DataManager

router = APIRouter()


# Dependency to get DataManager instance
def get_data_manager(request: Request) -> DataManager:
    """Return a DataManager instance with injected dependencies."""
    config = request.app.state.config
    file_manager = request.app.state.file_manager
    db_service = request.app.state.db_service
    service_manager = request.app.state.service_manager
    return DataManager(config, file_manager, db_service, service_manager)


@router.get("/recordings")
async def get_recordings(
    data_manager: DataManager = Depends(get_data_manager),  # noqa: B008
) -> dict:
    """Retrieve a list of all recorded audio files."""
    recordings = data_manager.get_recordings()
    return {"recordings": recordings}
