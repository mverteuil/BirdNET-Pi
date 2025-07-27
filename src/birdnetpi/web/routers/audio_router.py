from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from birdnetpi.managers.data_manager import DataManager
from birdnetpi.services.audio_device_service import AudioDeviceService
from birdnetpi.web.forms import AudioDeviceSelectionForm

router = APIRouter()


# Dependency to get DataManager instance
def get_data_manager(request: Request) -> DataManager:
    """Return a DataManager instance with injected dependencies."""
    config = request.app.state.config
    file_manager = request.app.state.file_manager
    db_service = request.app.state.db_service
    service_manager = request.app.state.service_manager
    return DataManager(config, file_manager, db_service, service_manager)


# Dependency to get AudioDeviceService instance
def get_audio_device_service(request: Request) -> AudioDeviceService:
    """Return an AudioDeviceService instance."""
    return AudioDeviceService()


@router.get("/recordings")
async def get_recordings(
    data_manager: DataManager = Depends(get_data_manager),  # noqa: B008
) -> dict:
    """Retrieve a list of all recorded audio files."""
    recordings = data_manager.get_recordings()
    return {"recordings": recordings}


@router.get("/audio/select_device", response_class=HTMLResponse)
async def select_audio_device(
    request: Request,
    audio_device_service: AudioDeviceService = Depends(get_audio_device_service),  # noqa: B008
) -> HTMLResponse:
    """Render the audio device selection page."""
    templates: Jinja2Templates = request.app.state.templates
    devices = audio_device_service.discover_input_devices()
    form = AudioDeviceSelectionForm(formdata=None, obj=request.app.state.config)
    form.device.choices = [(str(d.index), d.name) for d in devices]
    return templates.TemplateResponse(
        request,
        "audio_device_selection.html",
        {"request": request, "form": form},
    )


@router.post("/audio/select_device", response_class=HTMLResponse)
async def handle_select_audio_device(
    request: Request,
    audio_device_service: AudioDeviceService = Depends(get_audio_device_service),  # noqa: B008
) -> HTMLResponse:
    """Handle the submission of the audio device selection form."""
    templates: Jinja2Templates = request.app.state.templates
    devices = audio_device_service.discover_input_devices()

    # Initialize form and populate choices before processing form data
    form = AudioDeviceSelectionForm()
    form.device.choices = [(str(d.index), d.name) for d in devices]

    form_data = await request.form()
    form = AudioDeviceSelectionForm(form_data)
    form.device.choices = [(str(d.index), d.name) for d in devices]

    if form.validate():
        print("Form validated successfully!")
        selected_device_index = int(form.device.data)
        # Here, you would update the application's config with the selected device
        # For now, we'll just print it and redirect
        print(f"Selected audio device index: {selected_device_index}")
        # Redirect to a success page or back to the same page with a success message
        return RedirectResponse(url="/audio/select_device", status_code=303)

    return templates.TemplateResponse(
        request,
        "audio_device_selection.html",
        {"request": request, "form": form},
    )
