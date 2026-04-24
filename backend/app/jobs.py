from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from app.auth import current_user
from app.db import Database
from app.storage import Storage

VALID_FORMATS = {"txt", "json", "srt", "vtt", "tsv"}
VALID_MODELS = {"tiny", "base", "medium", "large"}


class Options(BaseModel):
    formats: list[str] = Field(default_factory=lambda: ["txt"])
    model: str | None = None

    @field_validator("formats")
    @classmethod
    def _fmts(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("formats cannot be empty")
        bad = set(v) - VALID_FORMATS
        if bad:
            raise ValueError(f"unknown formats: {sorted(bad)}")
        return v

    @field_validator("model")
    @classmethod
    def _model(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in VALID_MODELS:
            raise ValueError(f"unknown model: {v}")
        return v


class UrlJobRequest(BaseModel):
    urls: list[str] = Field(min_length=1)
    options: Options = Field(default_factory=Options)


class JobResponse(BaseModel):
    id: str
    status: Literal["queued", "running", "done", "failed"]
    input_kind: Literal["urls", "files"]
    inputs: list[str]
    options: Options
    message: str | None = None
    file_count: int | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None


def _row_to_response(row: dict) -> JobResponse:
    return JobResponse(
        id=row["id"],
        status=row["status"],
        input_kind=row["input_kind"],
        inputs=json.loads(row["inputs_json"]),
        options=Options(**json.loads(row["options_json"])),
        message=row["message"],
        file_count=row["file_count"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )


router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", status_code=201, response_model=JobResponse)
async def create_url_job(
    request: Request,
    payload: UrlJobRequest,
    user: dict = Depends(current_user),
):
    db: Database = request.app.state.db
    storage: Storage = request.app.state.storage
    await db.upsert_user(open_id=user["open_id"], name=user.get("name"), email=None)
    job_id = await db.insert_job(
        user_id=user["open_id"],
        input_kind="urls",
        inputs_json=json.dumps(payload.urls),
        options_json=payload.options.model_dump_json(),
    )
    storage.create_job_dirs(job_id)
    submit = getattr(request.app.state, "submit_job", None)
    if submit:
        submit(job_id)
    row = await db.get_job(job_id)
    return _row_to_response(row)


@router.post("/files", status_code=201, response_model=JobResponse)
async def create_file_job(
    request: Request,
    files: Annotated[list[UploadFile], File()],
    options_json: Annotated[str, Form()],
    user: dict = Depends(current_user),
):
    if not files:
        raise HTTPException(status_code=422, detail="no files uploaded")
    try:
        options = Options.model_validate_json(options_json)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"invalid options: {e}") from e

    db: Database = request.app.state.db
    storage: Storage = request.app.state.storage
    await db.upsert_user(open_id=user["open_id"], name=user.get("name"), email=None)

    job_id = await db.insert_job(
        user_id=user["open_id"],
        input_kind="files",
        inputs_json=json.dumps([storage.sanitise_filename(f.filename or "upload") for f in files]),
        options_json=options.model_dump_json(),
    )
    paths = storage.create_job_dirs(job_id)

    total = 0
    per_limit = request.app.state.settings.max_upload_mb * 1024 * 1024
    total_limit = request.app.state.settings.max_total_upload_mb * 1024 * 1024
    for f in files:
        name = storage.sanitise_filename(f.filename or "upload")
        dest = paths.input / name
        written = 0
        with dest.open("wb") as out:
            while chunk := await f.read(1 << 20):
                written += len(chunk)
                total += len(chunk)
                if written > per_limit:
                    raise HTTPException(status_code=413, detail=f"file '{name}' exceeds per-file limit")
                if total > total_limit:
                    raise HTTPException(status_code=413, detail="total upload exceeds limit")
                out.write(chunk)

    submit = getattr(request.app.state, "submit_job", None)
    if submit:
        submit(job_id)
    row = await db.get_job(job_id)
    return _row_to_response(row)


@router.get("", response_model=list[JobResponse])
async def list_jobs(request: Request, user: dict = Depends(current_user)):
    db: Database = request.app.state.db
    rows = await db.list_jobs(user["open_id"])
    return [_row_to_response(r) for r in rows]


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, request: Request, user: dict = Depends(current_user)):
    db: Database = request.app.state.db
    row = await db.get_job(job_id)
    if not row or row["user_id"] != user["open_id"]:
        raise HTTPException(status_code=404, detail="not found")
    return _row_to_response(row)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: str, request: Request, user: dict = Depends(current_user)):
    db: Database = request.app.state.db
    storage: Storage = request.app.state.storage
    row = await db.get_job(job_id)
    if not row or row["user_id"] != user["open_id"]:
        raise HTTPException(status_code=404, detail="not found")
    storage.delete_job(job_id)
    await db.delete_job(job_id)


@router.get("/{job_id}/download")
async def download_job(job_id: str, request: Request, user: dict = Depends(current_user)):
    db: Database = request.app.state.db
    row = await db.get_job(job_id)
    if not row or row["user_id"] != user["open_id"]:
        raise HTTPException(status_code=404, detail="not found")
    if row["status"] != "done" or not row["result_path"]:
        raise HTTPException(status_code=409, detail="job not complete")
    path = Path(row["result_path"])
    if not path.is_file():
        raise HTTPException(status_code=410, detail="result missing")
    return FileResponse(path, filename=path.name)
