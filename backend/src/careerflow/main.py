from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from careerflow.api.ai import router as ai_router
from careerflow.api.artifacts import router as artifacts_router
from careerflow.api.config import router as config_router
from careerflow.api.duplicates import router as duplicates_router
from careerflow.api.health import router as health_router
from careerflow.api.integrations import router as integrations_router
from careerflow.api.jobs import router as jobs_router
from careerflow.api.profile_items import router as profile_items_router
from careerflow.api.profiles import router as profiles_router
from careerflow.api.request_context import install_request_context
from careerflow.api.resume import router as resume_router
from careerflow.api.searches import router as searches_router
from careerflow.api.sources import router as sources_router
from careerflow.api.tasks import router as tasks_router
from careerflow.api.tracking import router as tracking_router
from careerflow.infrastructure.logging import configure_logging, secrets_from_url
from careerflow.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(
        settings.log_level,
        secrets=[*settings.redact_value_list, *secrets_from_url(settings.database_url)],
    )
    app = FastAPI(title="CareerFlow API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Total-Count"],
    )
    install_request_context(app)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        # Same shape as FastAPI's default, minus the echoed ``input``/``ctx``: a rejected
        # request body may contain a secret that must not be reflected back or logged.
        detail = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in error.errors()]
        return JSONResponse(status_code=422, content={"detail": detail})

    app.include_router(health_router)
    app.include_router(config_router, prefix="/api/v1")
    app.include_router(tasks_router, prefix="/api/v1")
    app.include_router(duplicates_router, prefix="/api/v1")
    app.include_router(sources_router, prefix="/api/v1")
    app.include_router(searches_router, prefix="/api/v1")
    app.include_router(resume_router, prefix="/api/v1")
    app.include_router(integrations_router, prefix="/api/v1")
    app.include_router(artifacts_router, prefix="/api/v1")
    app.include_router(tracking_router, prefix="/api/v1")
    app.include_router(ai_router, prefix="/api/v1")
    app.include_router(profiles_router, prefix="/api/v1")
    app.include_router(profile_items_router, prefix="/api/v1")
    app.include_router(jobs_router, prefix="/api/v1")
    return app


app = create_app()
