from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from birdnetpi.managers.plotting_manager import PlottingManager

router = APIRouter()


def get_plotting_manager(request: Request) -> PlottingManager:
    """Return a PlottingManager instance with injected dependencies."""
    # TODO: Properly inject PlottingManager dependencies if any
    return PlottingManager()


@router.get("/spectrogram")
async def get_spectrogram(
    audio_path: str,
    plotting_manager: PlottingManager = Depends(get_plotting_manager),  # noqa: B008
) -> StreamingResponse:
    """Generate and return a spectrogram for a given audio file."""
    # TODO: Add validation for audio_path to ensure it's a valid and safe path
    spectrogram_bytes = plotting_manager.generate_spectrogram(audio_path)
    return StreamingResponse(content=spectrogram_bytes, media_type="image/png")
