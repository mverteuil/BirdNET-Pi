from BirdNET_Pi.src.managers.update_manager import UpdateManager
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

templates = Jinja2Templates(directory="src/web/templates")


@router.get("/views", response_class=HTMLResponse)
async def read_views(request: Request):
    update_manager = UpdateManager(
        repo_path="./"
    )  # Assuming repo_path is current directory for now
    commits_behind = update_manager.get_commits_behind()
    return templates.TemplateResponse(
        "views.html", {"request": request, "commits_behind": commits_behind}
    )
