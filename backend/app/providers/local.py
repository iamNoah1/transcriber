from __future__ import annotations

import subprocess
from pathlib import Path


class LocalProvider:
    """Shells out to the user's audiotap + whisperbatch CLIs."""

    def download_urls(self, urls: list[str], input_dir: Path) -> None:
        cmd = [
            "audiotap",
            "--output-dir", str(input_dir),
            "--format", "opus",
            "--workers", "2",
            *urls,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if r.returncode != 0:
            tail = (r.stderr or r.stdout or "").strip().splitlines()[-5:]
            raise RuntimeError("audiotap failed: " + " | ".join(tail))

    def transcribe(
        self,
        input_dir: Path,
        output_dir: Path,
        *,
        formats: list[str],
        model: str | None,
    ) -> None:
        cmd = [
            "whisperbatch",
            "-i", str(input_dir),
            "-o", str(output_dir),
        ]
        for f in formats:
            cmd.extend(["-f", f])
        if model:
            cmd.extend(["-m", model])
        r = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if r.returncode != 0:
            tail = (r.stderr or r.stdout or "").strip().splitlines()[-5:]
            raise RuntimeError("whisperbatch failed: " + " | ".join(tail))
