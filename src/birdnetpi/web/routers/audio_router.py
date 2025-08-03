from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from birdnetpi.managers.file_manager import FileManager
from birdnetpi.services.audio_device_service import AudioDeviceService
from birdnetpi.utils.file_path_resolver import FilePathResolver
from birdnetpi.web.forms import AudioDeviceSelectionForm

router = APIRouter()


# Dependency to get FileManager instance
def get_file_manager(request: Request) -> FileManager:
    """Return a FileManager instance with injected dependencies."""
    file_resolver: FilePathResolver = request.app.state.file_resolver
    return FileManager(file_resolver.get_recordings_dir())


# Dependency to get AudioDeviceService instance
def get_audio_device_service(request: Request) -> AudioDeviceService:
    """Return an AudioDeviceService instance."""
    return AudioDeviceService()


@router.get("/recordings")
async def get_recordings(
    file_manager: FileManager = Depends(get_file_manager),  # noqa: B008
) -> dict:
    """Retrieve a list of all recorded audio files."""
    file_resolver = FilePathResolver()
    recordings_dir = file_resolver.get_recordings_dir()
    recordings = file_manager.list_directory_contents(recordings_dir)
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
