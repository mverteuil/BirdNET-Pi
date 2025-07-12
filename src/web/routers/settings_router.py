from BirdNET_Pi.src.models.birdnet_config import BirdNETConfig
from BirdNET_Pi.src.utils.config_file_parser import ConfigFileParser
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

templates = Jinja2Templates(directory="src/web/templates")


@router.get("/settings", response_class=HTMLResponse)
async def get_settings(request: Request):
    config_parser = ConfigFileParser("etc/birdnet_pi_config.yaml")
    app_config: BirdNETConfig = config_parser.load_config()
    return templates.TemplateResponse(
        "settings.html", {"request": request, "config": app_config}
    )
