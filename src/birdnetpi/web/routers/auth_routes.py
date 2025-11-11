"""Authentication routes for admin setup and login."""

from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starsessions import load_session
from starsessions.session import regenerate_session_id

from birdnetpi.config import BirdNETConfig
from birdnetpi.i18n.translation_manager import TranslationManager
from birdnetpi.system.status import SystemInspector
from birdnetpi.utils.auth import AuthService
from birdnetpi.utils.language import get_user_language
from birdnetpi.web.core.container import Container

router = APIRouter()


@router.get("/admin/setup", response_class=HTMLResponse, response_model=None)
@inject
async def setup_page(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(Provide[Container.templates])],
    auth_service: Annotated[AuthService, Depends(Provide[Container.auth_service])],
) -> HTMLResponse | RedirectResponse:
    """Show setup wizard page.

    If admin user already exists, redirects to home page.
    """
    if auth_service.admin_exists():
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(
        "admin/setup.html.j2", {"request": request, "prefill_username": "admin"}
    )


@router.post("/admin/setup")
@inject
async def create_admin(
    request: Request,
    auth_service: Annotated[AuthService, Depends(Provide[Container.auth_service])],
    username: str = Form(...),
    password: str = Form(...),
) -> RedirectResponse:
    """Create admin user and log them in.

    Saves admin user with hashed password, creates session, and redirects to home.
    """
    # Save admin user (password is automatically hashed)
    auth_service.save_admin_user(username, password)

    # Regenerate session ID to prevent session fixation attacks
    regenerate_session_id(request)

    # Store username in session
    request.session["username"] = username

    # Redirect to home page
    return RedirectResponse(url="/", status_code=303)


@router.get("/admin/login", response_class=HTMLResponse, name="login")
@inject
async def login_page(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(Provide[Container.templates])],
    config: Annotated[BirdNETConfig, Depends(Provide[Container.config])],
    translation_manager: Annotated[
        TranslationManager, Depends(Provide[Container.translation_manager])
    ],
) -> HTMLResponse:
    """Show login page."""
    # Get user language
    language = get_user_language(request, config)
    _ = translation_manager.get_translation(language).gettext

    # Create context with all required base template variables
    context = {
        "request": request,
        "error": None,
        "config": config,
        "language": language,
        "system_status": {"device_name": SystemInspector.get_device_name()},
        "page_name": _("Administrator Login"),
        "active_page": "login",
        "model_update_date": None,
    }

    return templates.TemplateResponse("admin/login.html.j2", context)


@router.post("/admin/login", response_model=None)
@inject
async def login(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(Provide[Container.templates])],
    auth_service: Annotated[AuthService, Depends(Provide[Container.auth_service])],
    config: Annotated[BirdNETConfig, Depends(Provide[Container.config])],
    translation_manager: Annotated[
        TranslationManager, Depends(Provide[Container.translation_manager])
    ],
    username: str = Form(...),
    password: str = Form(...),
) -> HTMLResponse | RedirectResponse:
    """Handle login form submission.

    Verifies credentials and creates session on success. Returns to login
    page with error on failure.
    """
    # Load admin user
    admin = auth_service.load_admin_user()
    if not admin or admin.username != username:
        # Get user language for error template
        language = get_user_language(request, config)
        _ = translation_manager.get_translation(language).gettext

        context = {
            "request": request,
            "error": _("Invalid credentials"),
            "config": config,
            "language": language,
            "system_status": {"device_name": SystemInspector.get_device_name()},
            "page_name": _("Administrator Login"),
            "active_page": "login",
            "model_update_date": None,
        }
        return templates.TemplateResponse("admin/login.html.j2", context)

    # Verify password
    if not auth_service.verify_password(password, admin.password_hash):
        # Get user language for error template
        language = get_user_language(request, config)
        _ = translation_manager.get_translation(language).gettext

        context = {
            "request": request,
            "error": _("Invalid credentials"),
            "config": config,
            "language": language,
            "system_status": {"device_name": SystemInspector.get_device_name()},
            "page_name": _("Administrator Login"),
            "active_page": "login",
            "model_update_date": None,
        }
        return templates.TemplateResponse("admin/login.html.j2", context)

    # Regenerate session ID
    regenerate_session_id(request)

    # Store username in session
    request.session["username"] = username

    # Redirect to original URL if specified, otherwise home
    next_url = request.query_params.get("next", "/")

    # Security: Only allow relative URLs to prevent open redirects
    # Our custom @require_admin decorator always uses relative URLs
    if next_url.startswith(("http://", "https://", "//")):
        # External or protocol-relative URL - ignore and go to home
        next_url = "/"

    return RedirectResponse(url=next_url, status_code=303)


@router.get("/admin/logout")
async def logout(request: Request) -> RedirectResponse:
    """Handle logout.

    Clears session and redirects to login page.
    """
    # Load session before accessing it
    await load_session(request)
    request.session.clear()
    return RedirectResponse(url="/admin/login", status_code=303)


# SQLAdmin login/logout redirects
@router.get("/admin/database/login", include_in_schema=False)
async def database_login_redirect() -> RedirectResponse:
    """Redirect SQLAdmin login to BirdNET-Pi login page."""
    return RedirectResponse(url="/admin/login?next=/admin/database", status_code=303)


@router.post("/admin/database/login", include_in_schema=False)
async def database_login_submit_redirect() -> RedirectResponse:
    """Redirect SQLAdmin login form submission to BirdNET-Pi login page."""
    return RedirectResponse(url="/admin/login?next=/admin/database", status_code=303)


@router.get("/admin/database/logout", include_in_schema=False)
async def database_logout_redirect() -> RedirectResponse:
    """Redirect SQLAdmin logout to BirdNET-Pi logout."""
    return RedirectResponse(url="/admin/logout", status_code=303)


# API endpoints for authentication status
@router.get("/api/auth/status")
async def auth_status(request: Request) -> dict[str, bool | str | None]:
    """Check authentication status.

    Returns:
        Dict with authenticated boolean and username if authenticated
    """
    return {
        "authenticated": request.user.is_authenticated,
        "username": request.user.display_name if request.user.is_authenticated else None,
    }
