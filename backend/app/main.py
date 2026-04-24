from fastapi import FastAPI

from app.auth import install_auth, register_oauth_routes
from app.config import get_settings
from app.db import Database
from app.jobs import router as jobs_router
from app.storage import Storage


def create_app() -> FastAPI:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.storage_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="transcribe-cloud")
    install_auth(app, settings)
    app.state.settings = settings

    db = Database(settings.db_path)
    app.state.db = db
    app.state.storage = Storage(settings.storage_dir)

    @app.on_event("startup")
    async def _startup() -> None:
        await db.init()

    register_oauth_routes(app, settings)
    app.include_router(jobs_router)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
