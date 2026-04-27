from __future__ import annotations

from pathlib import Path
from typing import Callable, Protocol

OnOutput = Callable[[str], None]


class TranscriptionProvider(Protocol):
    def download_urls(
        self, urls: list[str], input_dir: Path, *, on_output: OnOutput | None = None
    ) -> None: ...
    def transcribe(
        self,
        input_dir: Path,
        output_dir: Path,
        *,
        formats: list[str],
        model: str | None,
        on_output: OnOutput | None = None,
    ) -> None: ...
