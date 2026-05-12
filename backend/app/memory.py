from __future__ import annotations

import psutil

# Per-model minimum *available* RAM in MB. Below this, jobs are rejected
# rather than allowed to silently OOM-kill the whisper subprocess (which
# dies with no Python traceback and produces a confusing failure mode).
# Numbers are conservative; whisperbatch itself uses 4 GB as its tiny
# threshold but tiny actually fits in less, so we let small hosts run it.
_MIN_AVAILABLE_MB: dict[str, int] = {
    "tiny": 2000,
    "base": 3000,
    "small": 5000,
    "medium": 7000,
    "large": 10000,
}

# When model is None, whisperbatch auto-picks the largest that fits and
# degrades to tiny on memory-constrained hosts, so the auto floor matches
# tiny's threshold.
_AUTO_MIN_MB = _MIN_AVAILABLE_MB["tiny"]


def available_ram_mb() -> int:
    return psutil.virtual_memory().available // (1024 * 1024)


def required_ram_mb(model: str | None) -> int:
    if model is None:
        return _AUTO_MIN_MB
    return _MIN_AVAILABLE_MB.get(model, _AUTO_MIN_MB)


def insufficient_memory_message(model: str | None) -> str | None:
    """Return a user-facing error if RAM is below the model's threshold, else None."""
    available = available_ram_mb()
    required = required_ram_mb(model)
    if available >= required:
        return None
    label = model or "auto"
    return (
        f"Not enough memory to run the '{label}' model: "
        f"{available} MB available, {required} MB required. "
        "Increase the container's memory allocation and try again."
    )
