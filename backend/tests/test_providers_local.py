from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.providers.local import LocalProvider


def test_download_urls_invokes_audiotap_with_correct_args(tmp_path: Path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    with patch("app.providers.local.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        p = LocalProvider()
        p.download_urls(["https://youtu.be/a", "https://youtu.be/b"], input_dir)
    args = run.call_args[0][0]
    assert args[0] == "audiotap"
    assert "--output-dir" in args and str(input_dir) in args
    assert "--format" in args and "opus" in args
    assert "https://youtu.be/a" in args and "https://youtu.be/b" in args


def test_download_urls_raises_on_non_zero_exit(tmp_path: Path):
    with patch("app.providers.local.subprocess.run") as run:
        run.return_value = MagicMock(returncode=1, stdout="", stderr="bad url")
        p = LocalProvider()
        with pytest.raises(RuntimeError, match="audiotap failed"):
            p.download_urls(["bad"], tmp_path)


def test_transcribe_invokes_whisperbatch_with_formats_and_model(tmp_path: Path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir(); output_dir.mkdir()
    with patch("app.providers.local.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        p = LocalProvider()
        p.transcribe(input_dir, output_dir, formats=["txt", "srt"], model="medium")
    args = run.call_args[0][0]
    assert args[0] == "whisperbatch"
    assert "-i" in args and str(input_dir) in args
    assert "-o" in args and str(output_dir) in args
    flags = [args[i + 1] for i, v in enumerate(args) if v == "-f"]
    assert set(flags) == {"txt", "srt"}
    assert "-m" in args and "medium" in args


def test_transcribe_omits_model_when_none(tmp_path: Path):
    with patch("app.providers.local.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        p = LocalProvider()
        p.transcribe(tmp_path, tmp_path, formats=["txt"], model=None)
    args = run.call_args[0][0]
    assert "-m" not in args
