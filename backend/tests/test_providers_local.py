from pathlib import Path
from unittest.mock import patch

import pytest

from app.providers.local import LocalProvider


def test_download_urls_invokes_audiotap_with_correct_args(tmp_path: Path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    with patch("app.providers.local._run_cli") as run:
        p = LocalProvider()
        p.download_urls(["https://youtu.be/a", "https://youtu.be/b"], input_dir)
    name, cmd = run.call_args[0]
    assert name == "audiotap"
    assert cmd[0] == "audiotap"
    assert "--output-dir" in cmd and str(input_dir) in cmd
    assert "--format" in cmd and "mp3" in cmd
    assert "https://youtu.be/a" in cmd and "https://youtu.be/b" in cmd


def test_download_urls_raises_on_non_zero_exit(tmp_path: Path):
    with patch("app.providers.local._run_cli") as run:
        run.side_effect = RuntimeError("audiotap failed (exit 1):\nbad url")
        p = LocalProvider()
        with pytest.raises(RuntimeError, match="audiotap failed"):
            p.download_urls(["bad"], tmp_path)


def test_transcribe_invokes_whisperbatch_with_formats_and_model(tmp_path: Path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir(); output_dir.mkdir()
    with patch("app.providers.local._run_cli") as run:
        p = LocalProvider()
        p.transcribe(input_dir, output_dir, formats=["txt", "srt"], model="medium")
    name, cmd = run.call_args[0]
    assert name == "whisperbatch"
    assert cmd[0] == "whisperbatch"
    assert "-i" in cmd and str(input_dir) in cmd
    assert "-o" in cmd and str(output_dir) in cmd
    flags = [cmd[i + 1] for i, v in enumerate(cmd) if v == "-f"]
    assert set(flags) == {"txt", "srt"}
    assert "-m" in cmd and "medium" in cmd


def test_transcribe_omits_model_when_none(tmp_path: Path):
    with patch("app.providers.local._run_cli") as run:
        p = LocalProvider()
        p.transcribe(tmp_path, tmp_path, formats=["txt"], model=None)
    _, cmd = run.call_args[0]
    assert "-m" not in cmd


def test_run_cli_streams_lines_through_callback():
    """_run_cli should split stdout on \\r and \\n and feed each line to on_output."""
    from app.providers.local import _run_cli
    seen: list[str] = []
    # echo a fake progress line followed by a final newline
    _run_cli("python", [
        "python", "-c",
        "import sys; sys.stdout.write('10%\\r50%\\r100%\\nDone\\n'); sys.stdout.flush()",
    ], on_output=seen.append)
    assert seen == ["10%", "50%", "100%", "Done"]


def test_run_cli_includes_exit_code_and_tail_on_failure():
    from app.providers.local import _run_cli
    with pytest.raises(RuntimeError) as exc:
        _run_cli("python", [
            "python", "-c",
            "import sys; print('boom'); sys.exit(7)",
        ])
    assert "exit 7" in str(exc.value)
    assert "boom" in str(exc.value)
