"""Application factory for creating FastAPI application with dependency injection."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from birdnetpi.config.manager import ConfigManager
from birdnetpi.i18n.translation_manager import setup_jinja2_i18n
from birdnetpi.system.status import SystemInspector
from birdnetpi.utils.language import get_user_language
from birdnetpi.web.core.container import Container
from birdnetpi.web.core.lifespan import lifespan
from birdnetpi.web.middleware.i18n import LanguageMiddleware
from birdnetpi.web.middleware.request_logging import StructuredRequestLoggingMiddleware
from birdnetpi.web.middleware.update_banner import add_update_status_to_templates
from birdnetpi.web.routers import (
    analysis_api_routes,
    detections_api_routes,
    health_api_routes,
    i18n_api_routes,
    logs_api_routes,
    logs_view_routes,
    multimedia_api_routes,
    multimedia_view_routes,
    reports_view_routes,
    services_view_routes,
    settings_api_routes,
    settings_view_routes,
    sqladmin_view_routes,
    system_api_routes,
    update_api_routes,
    update_view_routes,
    websocket_routes,
)


def create_app() -> FastAPI:
    """Create FastAPI application with dependency injection.

    This factory function creates a fully configured FastAPI application with:
    - Dependency injection container setup
    - All routers properly configured with prefixes and tags
    - Lifespan management for service startup and shutdown
    - Proper dependency wiring for all modules

    Returns:
        FastAPI: The configured application instance.
    """
    # Create container
    container = Container()

    # Create app with lifespan and documentation configuration
    # Note: We disable the default /docs endpoint as we'll provide a custom one
    app = FastAPI(
        lifespan=lifespan,
        title="BirdNET-Pi API",
        description="API for BirdNET-Pi bird detection and analysis system",
        version="1.0.0",
        docs_url=None,  # Disable default docs - we'll provide custom
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Set up translation manager in app state for middleware access
    app.state.translation_manager = container.translation_manager()

    # Add CORS middleware for proper headers (including AudioWorklet support)
    # Wildcard CORS needed for local network access to BirdNET-Pi device
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # nosemgrep
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],  # Expose all headers including Content-Type
    )

    # Add LanguageMiddleware
    app.add_middleware(LanguageMiddleware)

    # Add structured request logging middleware
    app.add_middleware(StructuredRequestLoggingMiddleware)

    # Add pyinstrument profiling middleware (only when enabled)
    # Access any endpoint with ?profile=1 to see profiling output
    if ConfigManager.should_enable_profiling():
        # Import only when needed to avoid dependency on pyinstrument in production
        from birdnetpi.web.middleware.pyinstrument_profiling import PyInstrumentProfilerMiddleware

        app.add_middleware(PyInstrumentProfilerMiddleware, html_output=True)

    # Configure Jinja2 templates with i18n support
    templates = container.templates()
    setup_jinja2_i18n(templates)

    # Add update status to template context

    add_update_status_to_templates(templates, container)

    # Wire dependencies for all router modules and factory
    container.wire(
        modules=[
            "birdnetpi.web.core.factory",  # Wire factory for root route
            "birdnetpi.web.routers.analysis_api_routes",
            "birdnetpi.web.routers.detections_api_routes",
            "birdnetpi.web.routers.health_api_routes",
            "birdnetpi.web.routers.i18n_api_routes",  # Wire i18n API routes
            "birdnetpi.web.routers.logs_api_routes",
            "birdnetpi.web.routers.logs_view_routes",
            "birdnetpi.web.routers.multimedia_api_routes",
            "birdnetpi.web.routers.multimedia_view_routes",
            "birdnetpi.web.routers.reports_view_routes",
            "birdnetpi.web.routers.services_view_routes",
            "birdnetpi.web.routers.settings_api_routes",
            "birdnetpi.web.routers.settings_view_routes",
            "birdnetpi.web.routers.sqladmin_view_routes",
            "birdnetpi.web.routers.system_api_routes",
            "birdnetpi.web.routers.update_api_routes",
            "birdnetpi.web.routers.update_view_routes",
            "birdnetpi.web.routers.websocket_routes",
        ]
    )

    # Include routers with proper prefixes and consistent tagging

    # === API Routes (included in documentation) ===

    # Analysis API routes for progressive loading
    app.include_router(analysis_api_routes.router, prefix="/api", tags=["Analysis API"])

    # Settings API routes
    app.include_router(settings_api_routes.router, prefix="/api", tags=["Settings API"])

    # Core API routes (detections endpoints, including cleanup)
    app.include_router(detections_api_routes.router, prefix="/api", tags=["Detections API"])

    # Health check routes (no authentication required)
    app.include_router(health_api_routes.router, prefix="/api", tags=["Health Check API"])

    # i18n API routes (translation support for JavaScript)
    app.include_router(i18n_api_routes.router, prefix="/api", tags=["i18n API"])

    # Logs API routes (historical and streaming)
    app.include_router(logs_api_routes.router, prefix="/api", tags=["Logs API"])

    # Multimedia API routes (audio/image serving)
    app.include_router(multimedia_api_routes.router, prefix="/api", tags=["Multimedia API"])

    # System API routes
    app.include_router(system_api_routes.router, prefix="/api", tags=["System API"])

    # Update API routes (includes region pack status)
    app.include_router(update_api_routes.router, prefix="/api", tags=["Update API"])

    # Real-time communication
    app.include_router(websocket_routes.router, prefix="/ws", tags=["WebSocket"])

    # === View Routes (excluded from API documentation) ===

    # Settings view routes (HTML pages)
    app.include_router(
        settings_view_routes.router,
        prefix="/admin",
        tags=["Settings Views"],
        include_in_schema=False,  # Exclude from API docs
    )

    # Logs view routes (HTML page for log viewer)
    app.include_router(
        logs_view_routes.router,
        prefix="/admin",
        tags=["Logs Views"],
        include_in_schema=False,  # Exclude from API docs
    )

    # Services view routes (HTML page for service status)
    app.include_router(
        services_view_routes.router,
        tags=["Services Views"],
        include_in_schema=False,  # Exclude from API docs
    )

    # Update view routes (HTML page for system updates)
    app.include_router(
        update_view_routes.router,
        prefix="/admin/update",
        tags=["Update Views"],
        include_in_schema=False,  # Exclude from API docs
    )

    # Multimedia view routes (livestream, spectrogram HTML pages)
    app.include_router(
        multimedia_view_routes.router,
        tags=["Multimedia Views"],
        include_in_schema=False,  # Exclude from API docs
    )

    # Reports view routes (detection displays, analytics HTML pages)
    app.include_router(
        reports_view_routes.router,
        tags=["Reports Views"],
        include_in_schema=False,  # Exclude from API docs
    )

    # Database administration interface
    sqladmin_view_routes.setup_sqladmin(app)

    # Root route (excluded from API documentation)
    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def read_root(request: Request) -> HTMLResponse:
        """Render the main index page."""
        # Get instances directly from the container to avoid DI issues
        config = container.config()
        templates = container.templates()
        presentation_manager = container.presentation_manager()

        # Get landing page data
        landing_data = await presentation_manager.get_landing_page_data_safe()

        # Get system status and language for base template
        language = get_user_language(request, config)

        return templates.TemplateResponse(
            request,
            "index.html.j2",
            {
                # Base template context requirements
                "config": config,
                "system_status": {"device_name": SystemInspector.get_device_name()},
                "language": language,
                "page_name": None,  # Dashboard doesn't need a page name
                "active_page": "dashboard",
                # Page-specific context
                "site_name": config.site_name,
                "location": f"{config.latitude:.4f}, {config.longitude:.4f}",
                # Safe: Using request hostname for WebSocket URL in same-origin context
                "websocket_url": f"ws://{request.url.hostname}:8000/ws/notifications",  # nosemgrep
                **landing_data.model_dump(),
            },
        )

    # Custom API documentation route with site styling
    @app.get("/docs", response_class=HTMLResponse, include_in_schema=False)
    async def custom_api_docs(request: Request) -> HTMLResponse:
        """Render custom API documentation page with site styling."""
        config = container.config()
        templates = container.templates()
        translation_manager = container.translation_manager()

        # Get system status and language for base template
        language = get_user_language(request, config)
        _ = translation_manager.get_translation(language).gettext

        return templates.TemplateResponse(
            request,
            "api_docs.html.j2",
            {
                # Base template context requirements
                "config": config,
                "system_status": {"device_name": SystemInspector.get_device_name()},
                "language": language,
                "page_name": _("API Documentation"),
                "active_page": "api",
                "model_update_date": None,
                # Page-specific context
                "openapi_url": app.openapi_url,
                "title": app.title,
            },
        )

    return app
