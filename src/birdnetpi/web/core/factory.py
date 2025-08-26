"""Application factory for creating FastAPI application with dependency injection."""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from birdnetpi.i18n.translation_manager import setup_jinja2_i18n
from birdnetpi.web.core.container import Container
from birdnetpi.web.core.lifespan import lifespan
from birdnetpi.web.middleware.i18n import LanguageMiddleware
from birdnetpi.web.middleware.request_logging import StructuredRequestLoggingMiddleware
from birdnetpi.web.routers import (
    admin_api_routes,
    admin_view_routes,
    detections_api_routes,
    health_api_routes,
    multimedia_view_routes,
    overview_api_routes,
    sqladmin_view_routes,
    system_api_routes,
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

    # Create app with lifespan
    app = FastAPI(lifespan=lifespan)

    # Attach container to app (ignore type error - runtime dynamic attribute)
    app.container = container  # type: ignore[attr-defined]

    # Set up translation manager in app state for middleware access
    app.state.translation_manager = container.translation_manager()

    # Add LanguageMiddleware
    app.add_middleware(LanguageMiddleware)

    # Add structured request logging middleware
    app.add_middleware(StructuredRequestLoggingMiddleware)

    # Configure Jinja2 templates with i18n support
    templates = container.templates()
    setup_jinja2_i18n(templates)

    # Wire dependencies for all router modules and factory
    container.wire(
        modules=[
            "birdnetpi.web.core.factory",  # Wire factory for root route
            "birdnetpi.web.routers.admin_api_routes",
            "birdnetpi.web.routers.admin_view_routes",
            "birdnetpi.web.routers.detections_api_routes",
            "birdnetpi.web.routers.health_api_routes",
            "birdnetpi.web.routers.multimedia_view_routes",
            "birdnetpi.web.routers.overview_api_routes",
            "birdnetpi.web.routers.sqladmin_view_routes",
            "birdnetpi.web.routers.system_api_routes",
            "birdnetpi.web.routers.websocket_routes",
        ]
    )

    # Include routers with proper prefixes and consistent tagging
    # Health check routes (no authentication required)
    app.include_router(health_api_routes.router, prefix="/api/health", tags=["Health"])

    # Admin routes (consolidated under /admin prefix)
    app.include_router(admin_view_routes.router, prefix="/admin", tags=["Admin Views"])
    app.include_router(admin_api_routes.router, prefix="/admin/config", tags=["Admin API"])

    # System API routes (consolidated under /api/system prefix)
    app.include_router(system_api_routes.router, prefix="/api/system", tags=["System API"])
    app.include_router(overview_api_routes.router, prefix="/api", tags=["Overview API"])

    # Multimedia view routes (livestream, spectrogram)
    app.include_router(multimedia_view_routes.router, tags=["Multimedia Views"])

    # Core API routes (detections endpoints)
    app.include_router(
        detections_api_routes.router, prefix="/api/detections", tags=["Detections API"]
    )

    # Real-time communication
    app.include_router(websocket_routes.router, prefix="/ws", tags=["WebSocket"])

    # Database administration interface
    sqladmin_view_routes.setup_sqladmin(app)

    # Root route
    @app.get("/", response_class=HTMLResponse)
    async def read_root(request: Request) -> HTMLResponse:
        """Render the main index page."""
        # Get instances directly from the container to avoid DI issues
        config = container.config()
        templates = container.templates()
        presentation_manager = container.presentation_manager()

        # Get landing page data
        landing_data = await presentation_manager.get_landing_page_data_safe()

        return templates.TemplateResponse(
            request,
            "index.html.j2",
            {
                "site_name": config.site_name,
                "location": f"{config.latitude:.4f}, {config.longitude:.4f}",
                "websocket_url": f"ws://{request.url.hostname}:8000/ws/notifications",
                **landing_data.model_dump(),
            },
        )

    return app
