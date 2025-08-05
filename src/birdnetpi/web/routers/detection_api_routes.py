"""Detection API routes for CRUD operations and spectrogram generation."""

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.managers.plotting_manager import PlottingManager
from birdnetpi.web.core.container import Container

router = APIRouter()


@router.get("/detections")
@inject
async def get_detections(
    detection_manager: DetectionManager = Depends(Provide[Container.detection_manager]),
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """Get recent detections."""
    detections = detection_manager.get_recent_detections(limit=limit)  # offset not supported yet
    return {"detections": detections, "count": len(detections)}


@router.get("/{detection_id}/spectrogram")
@inject
async def get_detection_spectrogram(
    detection_id: str,
    audio_path: str = Query(..., min_length=1, description="Path to the audio file"),
    plotting_manager: PlottingManager = Depends(Provide[Container.plotting_manager]),
) -> StreamingResponse:
    """Generate and return a spectrogram for a specific detection's audio file."""
    try:
        spectrogram_buffer = plotting_manager.generate_spectrogram(audio_path)
        return StreamingResponse(content=iter([spectrogram_buffer.read()]), media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating spectrogram: {e}") from e