from unittest.mock import MagicMock

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from birdnetpi.managers.data_preparation_manager import DataPreparationManager
from birdnetpi.managers.plotting_manager import PlottingManager

router = APIRouter()


def get_plotting_manager(request: Request) -> PlottingManager:
    """Return a PlottingManager instance with injected dependencies."""
    # TODO: Properly inject PlottingManager dependencies
    # Using mock for DataPreparationManager since it has complex dependencies
    mock_data_preparation_manager = MagicMock(spec=DataPreparationManager)
    return PlottingManager(mock_data_preparation_manager)


@router.get("/livestream")
async def get_spectrogram(
    audio_path: str = Query(..., min_length=1, description="Path to the audio file"),
    plotting_manager: PlottingManager = Depends(get_plotting_manager),  # noqa: B008
) -> StreamingResponse:
    """Generate and return a spectrogram for a given audio file."""
    try:
        spectrogram_buffer = plotting_manager.generate_spectrogram(audio_path)
        return StreamingResponse(content=iter([spectrogram_buffer.read()]), media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating spectrogram: {e}") from e
