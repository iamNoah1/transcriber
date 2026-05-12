import pytest

from app import memory


def test_required_ram_per_model():
    assert memory.required_ram_mb("tiny") == 2000
    assert memory.required_ram_mb("base") == 3000
    assert memory.required_ram_mb("small") == 5000
    assert memory.required_ram_mb("medium") == 7000
    assert memory.required_ram_mb("large") == 10000


def test_required_ram_none_uses_tiny_floor():
    assert memory.required_ram_mb(None) == memory.required_ram_mb("tiny")


def test_required_ram_unknown_model_falls_back_to_auto():
    assert memory.required_ram_mb("xxl-extreme") == memory.required_ram_mb(None)


def test_message_none_when_ample(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(memory, "available_ram_mb", lambda: 64_000)
    assert memory.insufficient_memory_message("tiny") is None
    assert memory.insufficient_memory_message("large") is None
    assert memory.insufficient_memory_message(None) is None


def test_message_describes_shortfall(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(memory, "available_ram_mb", lambda: 500)
    msg = memory.insufficient_memory_message("tiny")
    assert msg is not None
    assert "500 MB" in msg
    assert "2000 MB" in msg
    assert "tiny" in msg


def test_message_uses_auto_label_when_model_none(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(memory, "available_ram_mb", lambda: 100)
    msg = memory.insufficient_memory_message(None)
    assert msg is not None
    assert "auto" in msg


def test_borderline_at_threshold_passes(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(memory, "available_ram_mb", lambda: 2000)
    assert memory.insufficient_memory_message("tiny") is None
