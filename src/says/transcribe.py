"""Pluggable speech-to-text backends.

The core never imports a speech-to-text library at module load. Backends are
looked up by name and imported only when selected, so a plain ``uv sync``
installs nothing heavy and the test suite runs without any model.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from says.models import Segment


class TranscriberUnavailable(RuntimeError):
    """Raised when a selected backend's optional dependency is not installed."""


class Transcriber(Protocol):
    name: str

    def transcribe(self, audio_path: Path) -> list[Segment]:
        """Return timed segments for a local audio file."""
        ...


class FasterWhisperTranscriber:
    """Local transcription with faster-whisper (install with ``uv sync --extra whisper``)."""

    name = "faster-whisper"

    def __init__(
        self, model_size: str = "small", device: str = "auto", compute_type: str = "default"
    ) -> None:
        try:
            from faster_whisper import WhisperModel  # type: ignore[import-not-found]
        except ImportError as exc:
            raise TranscriberUnavailable(
                "faster-whisper is not installed; run `uv sync --extra whisper`"
            ) from exc
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, audio_path: Path) -> list[Segment]:
        segments, _info = self._model.transcribe(str(audio_path), vad_filter=True)
        return [
            Segment(start=float(s.start), end=float(s.end), text=s.text.strip())
            for s in segments
            if s.text.strip()
        ]


_REGISTRY: dict[str, Callable[[], Transcriber]] = {
    "faster-whisper": FasterWhisperTranscriber,
}


# Modules each built-in backend needs, checked by ``says doctor`` without
# constructing the backend (which may load a model).
_REQUIRED_MODULES: dict[str, tuple[str, str]] = {
    "faster-whisper": ("faster_whisper", "uv sync --extra whisper"),
}


def register(name: str, factory: Callable[[], Transcriber]) -> None:
    """Register a backend factory. Used by tests and by third-party backends."""
    _REGISTRY[name] = factory


def check_backend(name: str) -> str:
    """Check that a backend is known and its dependency imports, without loading a model.

    Returns a short description. Raises ``ValueError`` for an unknown name and
    ``ImportError`` when the backend's optional dependency is missing.
    """
    if name not in _REGISTRY:
        raise ValueError(f"unknown transcriber {name!r}; available: {available()}")
    required = _REQUIRED_MODULES.get(name)
    if required is None:
        return f"{name} (registered)"
    module, install = required
    try:
        importlib.import_module(module)
    except ImportError as exc:
        raise ImportError(f"cannot import {module} ({exc}); run `{install}`") from exc
    return f"{name} ({module} importable)"


def available() -> list[str]:
    return sorted(_REGISTRY)


def get_transcriber(name: str | None) -> Transcriber | None:
    """Return a backend instance, or ``None`` when transcription is disabled."""
    if not name or name == "none":
        return None
    try:
        factory = _REGISTRY[name]
    except KeyError as exc:
        raise ValueError(f"unknown transcriber {name!r}; available: {available()}") from exc
    return factory()
