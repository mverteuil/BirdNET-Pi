from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from managers.reporting_manager import ReportingManager
from managers.update_manager import UpdateManager
from services.database_manager import DatabaseManager

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


@router.get("/views/weekly-report", response_class=HTMLResponse)
async def get_weekly_report(request: Request):
    db_manager = DatabaseManager()
    reporting_manager = ReportingManager(db_manager)
    report_data = reporting_manager.get_weekly_report_data()
    return templates.TemplateResponse(
        "weekly_report.html", {"request": request, "report": report_data}
    )
