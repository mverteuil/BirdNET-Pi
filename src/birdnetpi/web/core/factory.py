"""Application factory for creating FastAPI application with dependency injection."""

from dependency_injector.wiring import Provide, inject
from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from birdnetpi.models.config import BirdNETConfig
from birdnetpi.web.core.container import Container
from birdnetpi.web.core.lifespan import lifespan
from birdnetpi.web.routers import (
    admin_api_routes,
    admin_router,
    admin_view_routes,
    detection_api_routes,
    detections_router,
    field_api_routes,
    field_mode_router,
    iot_api_routes,
    overview_router,
    reporting_router,
    system_api_routes,
    websocket_router,
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

    # Wire dependencies for all router modules and factory
    container.wire(
        modules=[
            "birdnetpi.web.core.factory",  # Wire factory for root route
            "birdnetpi.web.routers.admin_router",
            "birdnetpi.web.routers.admin_api_routes",
            "birdnetpi.web.routers.admin_view_routes",
            "birdnetpi.web.routers.detection_api_routes",
            "birdnetpi.web.routers.detections_router",
            "birdnetpi.web.routers.field_api_routes",
            "birdnetpi.web.routers.field_mode_router",
            "birdnetpi.web.routers.iot_api_routes",
            "birdnetpi.web.routers.overview_router",
            "birdnetpi.web.routers.reporting_router",
            "birdnetpi.web.routers.system_api_routes",
            "birdnetpi.web.routers.websocket_router",
        ]
    )

    # Include routers with proper prefixes and consistent tagging
    # Admin routes (consolidated under /admin prefix)
    app.include_router(admin_router.router, prefix="/admin", tags=["Admin"])
    app.include_router(admin_view_routes.router, prefix="/admin", tags=["Admin Views"])
    app.include_router(admin_api_routes.router, prefix="/admin", tags=["Admin API"])

    # System API routes (consolidated under /api/system prefix)
    app.include_router(system_api_routes.router, prefix="/api/system", tags=["System API"])
    app.include_router(overview_router.router, prefix="/api", tags=["Overview API"])

    # Reports routes (consolidated under /reports prefix)
    app.include_router(reporting_router.router, prefix="/reports", tags=["Reports"])

    # Field mode routes
    app.include_router(field_mode_router.router, tags=["Field Mode"])
    app.include_router(field_api_routes.router, prefix="/api/field", tags=["Field API"])

    # Core API routes (detections and IoT endpoints)
    app.include_router(detections_router.router, prefix="/api/detections", tags=["Detections API"])
    app.include_router(
        detection_api_routes.router, prefix="/api/detections", tags=["Detection API"]
    )
    app.include_router(iot_api_routes.router, prefix="/api/iot", tags=["IoT API"])

    # Real-time communication
    app.include_router(websocket_router.router, prefix="/ws", tags=["WebSocket"])

    # Root route
    @app.get("/", response_class=HTMLResponse)
    @inject
    async def read_root(
        request: Request,
        templates: Jinja2Templates = Depends(Provide[Container.templates]),
        config: BirdNETConfig = Depends(Provide[Container.config]),
    ) -> HTMLResponse:
        """Render the main index page."""
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "site_name": config.site_name,
                "websocket_url": f"ws://{request.url.hostname}:8000/ws/notifications",
            },
        )

    return app
