from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Callable

OnOutput = Callable[[str], None]

# Both audiotap and whisperbatch use schollz/progressbar/v3, which emits \r-rewrites.
# yt-dlp does the same. Splitting on either \r or \n lets us see those updates as
# they happen rather than only at end-of-line boundaries.
_LINE_BREAK = re.compile(r"[\r\n]")

log = logging.getLogger(__name__)


def _run_cli(name: str, cmd: list[str], on_output: OnOutput | None = None) -> None:
    log.debug("$ %s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=0,
    )
    assert proc.stdout is not None
    captured: list[str] = []
    buf = ""
    while True:
        chunk = proc.stdout.read(256)
        if not chunk:
            break
        buf += chunk
        while True:
            m = _LINE_BREAK.search(buf)
            if m is None:
                break
            line = buf[: m.start()]
            buf = buf[m.end() :]
            if line:
                captured.append(line)
                log.debug("[%s] %s", name, line)
                if on_output:
                    try:
                        on_output(line)
                    except Exception:  # noqa: BLE001 — never let a callback bug kill the job
                        pass
    if buf:
        captured.append(buf)
        log.debug("[%s] %s", name, buf)
        if on_output:
            try:
                on_output(buf)
            except Exception:  # noqa: BLE001
                pass
    proc.wait()
    if proc.returncode != 0:
        head = captured[:20]
        tail = captured[-80:]
        overlap_start = max(0, len(captured) - 80)
        lines = head + (["..."] if overlap_start > 20 else []) + captured[max(20, overlap_start):]
        full_output = "\n".join(lines)
        log.error("[%s] exited %d:\n%s", name, proc.returncode, full_output)
        raise RuntimeError(f"{name} failed (exit {proc.returncode}):\n{full_output}")


class LocalProvider:
    """Shells out to the user's audiotap + whisperbatch CLIs."""

    def download_urls(
        self,
        urls: list[str],
        input_dir: Path,
        *,
        on_output: OnOutput | None = None,
    ) -> None:
        cmd = [
            "audiotap",
            "--output-dir", str(input_dir),
            "--format", "mp3",
            "--workers", "2",
            *urls,
        ]
        _run_cli("audiotap", cmd, on_output=on_output)

    def transcribe(
        self,
        input_dir: Path,
        output_dir: Path,
        *,
        formats: list[str],
        model: str | None,
        on_output: OnOutput | None = None,
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
        _run_cli("whisperbatch", cmd, on_output=on_output)
