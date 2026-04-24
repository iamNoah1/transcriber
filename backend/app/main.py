from fastapi import FastAPI

from app.auth import install_auth, register_oauth_routes
from app.config import get_settings
from app.db import Database


def create_app() -> FastAPI:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.storage_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="transcribe-cloud")
    install_auth(app, settings)

    db = Database(settings.db_path)
    app.state.db = db

    @app.on_event("startup")
    async def _startup() -> None:
        await db.init()

    register_oauth_routes(app, settings)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
