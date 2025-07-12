from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

templates = Jinja2Templates(directory="src/web/templates")


@router.get("/views", response_class=HTMLResponse)
async def read_views(request: Request):
    return templates.TemplateResponse("views.html", {"request": request})
