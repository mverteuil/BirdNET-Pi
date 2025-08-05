"""Admin view routes for administrative UI pages."""

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from birdnetpi.models.config import BirdNETConfig
from birdnetpi.services.audio_device_service import AudioDeviceService
from birdnetpi.web.core.container import Container
from birdnetpi.web.forms import AudioDeviceSelectionForm

router = APIRouter()


@router.get("/audio/select_device", response_class=HTMLResponse)
@inject
async def select_audio_device(
    request: Request,
    config: BirdNETConfig = Depends(Provide[Container.config]),
) -> HTMLResponse:
    """Render the audio device selection page."""
    templates: Jinja2Templates = request.app.extra["templates"]
    audio_device_service = AudioDeviceService()
    devices = audio_device_service.discover_input_devices()
    form = AudioDeviceSelectionForm(formdata=None, obj=config)
    form.device.choices = [(str(d.index), d.name) for d in devices]
    return templates.TemplateResponse(
        request,
        "audio_device_selection.html",
        {"request": request, "form": form},
    )


@router.post("/audio/select_device", response_model=None)
@inject
async def handle_select_audio_device(
    request: Request,
    config: BirdNETConfig = Depends(Provide[Container.config]),
) -> HTMLResponse | RedirectResponse:
    """Handle the submission of the audio device selection form."""
    templates: Jinja2Templates = request.app.extra["templates"]
    audio_device_service = AudioDeviceService()
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
        return RedirectResponse(url="/admin/audio/select_device", status_code=303)

    return templates.TemplateResponse(
        request,
        "audio_device_selection.html",
        {"request": request, "form": form},
    )