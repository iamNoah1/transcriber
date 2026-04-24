from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.auth import install_auth, register_oauth_routes
from app.config import get_settings
from app.db import Database
from app.jobs import router as jobs_router
from app.providers.local import LocalProvider
from app.storage import Storage
from app.workers import JobRunner, Worker, start_retention_loop


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
        app.state.retention_task = start_retention_loop(
            db, app.state.storage, settings.job_retention_days
        )

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        task = getattr(app.state, "retention_task", None)
        if task:
            task.cancel()
        worker.shutdown()

    register_oauth_routes(app, settings)
    app.include_router(jobs_router)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    static_dir = Path(__file__).parent / "static"
    if static_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404)
            return FileResponse(static_dir / "index.html")

    return app


app = create_app()
