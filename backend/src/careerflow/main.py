from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from careerflow.api.health import router as health_router
from careerflow.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="CareerFlow API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    return app


app = create_app()
