from __future__ import annotations

from pathlib import Path
from typing import Protocol


class TranscriptionProvider(Protocol):
    def download_urls(self, urls: list[str], input_dir: Path) -> None: ...
    def transcribe(
        self,
        input_dir: Path,
        output_dir: Path,
        *,
        formats: list[str],
        model: str | None,
    ) -> None: ...
