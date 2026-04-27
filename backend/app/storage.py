from __future__ import annotations

import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class JobPaths:
    root: Path
    input: Path
    output: Path


class Storage:
    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.jobs_dir = storage_dir / "jobs"

    def create_job_dirs(self, job_id: str) -> JobPaths:
        root = self.jobs_dir / job_id
        input_dir = root / "input"
        output_dir = root / "output"
        for d in (root, input_dir, output_dir):
            d.mkdir(parents=True, exist_ok=True)
        return JobPaths(root=root, input=input_dir, output=output_dir)

    def job_paths(self, job_id: str) -> JobPaths:
        root = self.jobs_dir / job_id
        return JobPaths(root=root, input=root / "input", output=root / "output")

    @staticmethod
    def sanitise_filename(name: str) -> str:
        name = name.replace("\x00", "")
        name = Path(name).name.strip()
        name = re.sub(r"\s+", "_", name)
        return name or "upload"

    def single_output_file(self, job_id: str) -> Path | None:
        output = self.job_paths(job_id).output
        if not output.exists():
            return None
        files = [p for p in output.iterdir() if p.is_file()]
        return files[0] if len(files) == 1 else None

    def zip_output(self, job_id: str) -> Path:
        paths = self.job_paths(job_id)
        zip_path = paths.root / "result.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(paths.output.iterdir()):
                if p.is_file():
                    z.write(p, arcname=p.name)
        return zip_path

    def clear_input(self, job_id: str) -> None:
        input_dir = self.job_paths(job_id).input
        if input_dir.exists():
            shutil.rmtree(input_dir)

    def delete_job(self, job_id: str) -> None:
        root = self.job_paths(job_id).root
        if root.exists():
            shutil.rmtree(root)
