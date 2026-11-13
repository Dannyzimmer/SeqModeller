"""Generation service contract and data transfer objects."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class GenerationRequest:
    config: dict
    fasta_path: Path | None = None
    report_path: Path | None = None
    config_path: Path | None = None
    seed: int | None = None


@dataclass(frozen=True)
class GenerationOutcome:
    seed: int | None
    stderr: str = ""
    details: dict = field(default_factory=dict)


class Generator(Protocol):
    """Minimal interface the GUI depends on."""

    def ensure_available(self) -> None: ...

    def version(self) -> str: ...

    def validate(self, config: dict) -> str: ...

    def generate(
        self,
        request: GenerationRequest,
        cancel_event: threading.Event | None = None,
    ) -> GenerationOutcome: ...
