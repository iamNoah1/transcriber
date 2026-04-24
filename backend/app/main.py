from fastapi import FastAPI

from app.auth import install_auth, register_oauth_routes
from app.config import get_settings
from app.db import Database
from app.jobs import router as jobs_router
from app.providers.local import LocalProvider
from app.storage import Storage
from app.workers import JobRunner, Worker


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

    provider = LocalProvider()
    runner = JobRunner(db=db, storage=app.state.storage, provider=provider)
    worker = Worker(runner)
    app.state.worker = worker
    app.state.submit_job = worker.submit

    @app.on_event("startup")
    async def _startup() -> None:
        await db.init()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        worker.shutdown()

    register_oauth_routes(app, settings)
    app.include_router(jobs_router)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
