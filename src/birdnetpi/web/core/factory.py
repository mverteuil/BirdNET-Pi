"""Application factory for creating FastAPI application with dependency injection."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from birdnetpi.i18n.translation_manager import setup_jinja2_i18n
from birdnetpi.web.core.container import Container
from birdnetpi.web.core.lifespan import lifespan
from birdnetpi.web.middleware.i18n import LanguageMiddleware
from birdnetpi.web.middleware.request_logging import StructuredRequestLoggingMiddleware
from birdnetpi.web.routers import (
    admin_api_routes,
    admin_view_routes,
    analysis_api_routes,
    detections_api_routes,
    health_api_routes,
    multimedia_view_routes,
    reports_view_routes,
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

    # Attach container to app (ignore type error - runtime dynamic attribute)
    app.container = container  # type: ignore[attr-defined]

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

    # Add pyinstrument profiling middleware (only in development)
    # Access any endpoint with ?profile=1 to see profiling output
    from birdnetpi.config.manager import ConfigManager

    if ConfigManager.should_enable_profiling():
        from birdnetpi.web.middleware.pyinstrument_profiling import PyInstrumentProfilerMiddleware

        app.add_middleware(PyInstrumentProfilerMiddleware, html_output=True)

    # Configure Jinja2 templates with i18n support
    templates = container.templates()
    setup_jinja2_i18n(templates)

    # Wire dependencies for all router modules and factory
    container.wire(
        modules=[
            "birdnetpi.web.core.factory",  # Wire factory for root route
            "birdnetpi.web.routers.admin_api_routes",
            "birdnetpi.web.routers.admin_view_routes",
            "birdnetpi.web.routers.analysis_api_routes",
            "birdnetpi.web.routers.detections_api_routes",
            "birdnetpi.web.routers.health_api_routes",
            "birdnetpi.web.routers.multimedia_view_routes",
            "birdnetpi.web.routers.reports_view_routes",
            "birdnetpi.web.routers.sqladmin_view_routes",
            "birdnetpi.web.routers.system_api_routes",
            "birdnetpi.web.routers.websocket_routes",
        ]
    )

    # Include routers with proper prefixes and consistent tagging

    # === API Routes (included in documentation) ===

    # Health check routes (no authentication required)
    # Note: health router already has tags=["health"] defined internally
    app.include_router(health_api_routes.router, prefix="/api/health")

    # Admin API routes
    app.include_router(admin_api_routes.router, prefix="/admin/config", tags=["Admin API"])

    # System API routes
    app.include_router(system_api_routes.router, prefix="/api/system", tags=["System API"])

    # Core API routes (detections endpoints)
    app.include_router(
        detections_api_routes.router, prefix="/api/detections", tags=["Detections API"]
    )

    # Analysis API routes for progressive loading
    app.include_router(analysis_api_routes.router, tags=["Analysis API"])

    # Real-time communication
    app.include_router(websocket_routes.router, prefix="/ws", tags=["WebSocket"])

    # === View Routes (excluded from API documentation) ===

    # Admin view routes (HTML pages)
    app.include_router(
        admin_view_routes.router,
        prefix="/admin",
        tags=["Admin Views"],
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

        return templates.TemplateResponse(
            request,
            "index.html.j2",
            {
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

        return templates.TemplateResponse(
            request,
            "api_docs.html.j2",
            {
                "config": config,
                "openapi_url": app.openapi_url,
                "title": app.title,
            },
        )

    return app
