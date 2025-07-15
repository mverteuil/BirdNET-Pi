from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.status import HTTP_303_SEE_OTHER

from birdnetpi.models.birdnet_config import BirdNETConfig
from birdnetpi.utils.config_file_parser import ConfigFileParser
from birdnetpi.utils.file_path_resolver import FilePathResolver

router = APIRouter()

templates = Jinja2Templates(directory="src/web/templates")
file_path_resolver = FilePathResolver()


@router.get("/settings", response_class=HTMLResponse)
async def get_settings(request: Request) -> Response:
    """Render the settings page with the current configuration."""
    config_parser = ConfigFileParser(file_path_resolver.get_birdnet_pi_config_path())
    app_config: BirdNETConfig = config_parser.load_config()
    return templates.TemplateResponse(
        "settings.html", {"request": request, "config": app_config}
    )


@router.post("/settings", response_class=HTMLResponse)
async def post_settings(
    request: Request,
    site_name: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    model: str = Form(...),
    sf_thresh: float = Form(...),
    birdweather_id: str = Form(""),
    apprise_input: str = Form(""),
    apprise_notification_title: str = Form(""),
    apprise_notification_body: str = Form(""),
    apprise_notify_each_detection: bool = Form(False),
    apprise_notify_new_species: bool = Form(False),
    apprise_notify_new_species_each_day: bool = Form(False),
    apprise_weekly_report: bool = Form(False),
    minimum_time_limit: int = Form(0),
    flickr_api_key: str = Form(""),
    flickr_filter_email: str = Form(""),
    database_lang: str = Form("en"),
    timezone: str = Form("UTC"),
    caddy_pwd: str = Form(""),
    silence_update_indicator: bool = Form(False),
    birdnetpi_url: str = Form(""),
    apprise_only_notify_species_names: str = Form(""),
    apprise_only_notify_species_names_2: str = Form(""),
) -> RedirectResponse:
    """Process the submitted settings form and save the updated configuration."""
    config_parser = ConfigFileParser(file_path_resolver.get_birdnet_pi_config_path())
    updated_config = BirdNETConfig(
        site_name=site_name,
        latitude=latitude,
        longitude=longitude,
        model=model,
        sf_thresh=sf_thresh,
        birdweather_id=birdweather_id,
        apprise_input=apprise_input,
        apprise_notification_title=apprise_notification_title,
        apprise_notification_body=apprise_notification_body,
        apprise_notify_each_detection=apprise_notify_each_detection,
        apprise_notify_new_species=apprise_notify_new_species,
        apprise_notify_new_species_each_day=apprise_notify_new_species_each_day,
        apprise_weekly_report=apprise_weekly_report,
        minimum_time_limit=minimum_time_limit,
        flickr_api_key=flickr_api_key,
        flickr_filter_email=flickr_filter_email,
        database_lang=database_lang,
        timezone=timezone,
        caddy_pwd=caddy_pwd,
        silence_update_indicator=silence_update_indicator,
        birdnetpi_url=birdnetpi_url,
        apprise_only_notify_species_names=apprise_only_notify_species_names,
        apprise_only_notify_species_names_2=apprise_only_notify_species_names_2,
    )
    config_parser.save_config(updated_config)
    return RedirectResponse(url="/settings", status_code=HTTP_303_SEE_OTHER)
