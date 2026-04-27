import logging
import logging.config
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


def _configure_logging(level: str) -> None:
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s %(levelname)-8s %(name)s  %(message)s",
                "datefmt": "%Y-%m-%dT%H:%M:%S",
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
            }
        },
        "root": {"handlers": ["console"], "level": level.upper()},
        # Quieten noisy uvicorn access log so job logs stand out
        "loggers": {
            "uvicorn.access": {"level": "WARNING"},
        },
    })


def create_app() -> FastAPI:
    settings = get_settings()
    _configure_logging(settings.log_level)

    log = logging.getLogger(__name__)
    log.info("Starting transcribe-cloud (env=%s, storage=%s)", settings.env, settings.storage_dir)

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
        log.info("Database ready: %s", settings.db_path)
        app.state.retention_task = start_retention_loop(
            db, app.state.storage, settings.job_retention_days
        )

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        log.info("Shutting down")
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
