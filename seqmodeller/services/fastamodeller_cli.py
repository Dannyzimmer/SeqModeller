"""Adapter around the external ``fastamodeller`` command line application."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
from importlib import metadata, util

from ..errors import (
    GenerationCancelled,
    GenerationError,
    GeneratorUnavailable,
    ValidationError,
)
from ..paths import is_frozen
from .files import atomic_write_json, atomic_write_text
from .generator import GenerationOutcome, GenerationRequest

_SEED_PATTERN = re.compile(r"^Seed:\s*(\d+)\s*$", re.MULTILINE)


class FastamodellerCli:
    """Run fastamodeller as a child process.

    The GUI never imports the internal generation modules; it only relies on
    the documented CLI contract.  This keeps the engine replaceable and makes
    the boundary testable.
    """

    def __init__(
        self,
        command: list[str] | None = None,
        timeout: float | None = None,
    ) -> None:
        self._command = command
        self._timeout = timeout
        self._cached_version: str | None = None

    def ensure_available(self) -> None:
        self._resolve_command()
        if self.version() == "unknown":
            raise GeneratorUnavailable(
                "The fastamodeller command line tool could not be executed.\n"
                "Install it with: pip install fastamodeller==1.0.0"
            )

    def version(self) -> str:
        if self._cached_version is not None:
            return self._cached_version
        try:
            result = subprocess.run(
                [*self._resolve_command(), "--version"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            output = (result.stdout or result.stderr).strip()
            if result.returncode == 0 and output:
                self._cached_version = output.rsplit(" ", 1)[-1].lstrip("v")
                return self._cached_version
        except (OSError, subprocess.SubprocessError):
            pass
        try:
            self._cached_version = metadata.version("fastamodeller")
        except metadata.PackageNotFoundError:
            self._cached_version = "unknown"
        return self._cached_version

    def validate(self, config: dict) -> str:
        try:
            result = subprocess.run(
                [*self._resolve_command(), "validate", "-"],
                input=json.dumps(config),
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except OSError as exc:
            raise GeneratorUnavailable(f"Could not run fastamodeller: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise ValidationError("fastamodeller validation timed out") from exc

        if result.returncode != 0:
            message = self._error_text(result)
            raise ValidationError(message)
        return (result.stdout or "").strip()

    def generate(
        self,
        request: GenerationRequest,
        cancel_event: threading.Event | None = None,
    ) -> GenerationOutcome:
        config = json.loads(json.dumps(request.config))
        seed = request.seed
        configured_seed = config.get("seed")
        if seed is None and isinstance(configured_seed, int) and not isinstance(
            configured_seed, bool
        ):
            seed = configured_seed

        if request.config_path is not None and request.fasta_path is None and request.report_path is None:
            if seed is not None:
                config["seed"] = seed
            atomic_write_json(request.config_path, config)
            return GenerationOutcome(seed=seed)

        if not any((request.fasta_path, request.report_path, request.config_path)):
            raise ValueError("At least one output path is required")

        command = [*self._resolve_command(), "generate", "-"]
        if request.fasta_path is not None:
            command.extend(["-o", str(request.fasta_path)])
        if request.report_path is not None and request.fasta_path is not None:
            command.extend(["-r", str(request.report_path)])
        elif request.report_path is not None:
            command.append("--only-report")
        if seed is not None:
            command.extend(["-s", str(seed)])

        outcome = self._run_generation(command, config, cancel_event)
        resolved_seed = self._extract_seed(outcome.stderr, seed)
        if request.report_path is not None and request.fasta_path is None:
            atomic_write_text(request.report_path, outcome.details["stdout"])
        if request.config_path is not None:
            config["seed"] = resolved_seed if resolved_seed is not None else False
            atomic_write_json(request.config_path, config)
        return GenerationOutcome(seed=resolved_seed, stderr=outcome.stderr)

    def _run_generation(
        self,
        command: list[str],
        config: dict,
        cancel_event: threading.Event | None,
    ) -> GenerationOutcome:
        if cancel_event is not None and cancel_event.is_set():
            raise GenerationCancelled("Generation cancelled")

        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except OSError as exc:
            raise GeneratorUnavailable(f"Could not run fastamodeller: {exc}") from exc

        watcher_stop: threading.Event | None = None
        watcher: threading.Thread | None = None
        if cancel_event is not None:
            watcher_stop = threading.Event()

            def watch() -> None:
                while not watcher_stop.wait(0.1):
                    if cancel_event.is_set():
                        process.kill()
                        return

            watcher = threading.Thread(target=watch, daemon=True)
            watcher.start()

        try:
            stdout, stderr = process.communicate(
                input=json.dumps(config), timeout=self._timeout
            )
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.communicate()
            raise GenerationError("fastamodeller generation timed out") from exc
        finally:
            if watcher_stop is not None:
                watcher_stop.set()
            if watcher is not None:
                watcher.join(timeout=1)

        if cancel_event is not None and cancel_event.is_set():
            raise GenerationCancelled("Generation cancelled")
        if process.returncode != 0:
            message = (stderr or stdout or "").strip()
            if not message:
                message = f"fastamodeller exited with code {process.returncode}"
            raise GenerationError(message)

        return GenerationOutcome(
            seed=None,
            stderr=stderr or "",
            details={"stdout": stdout or ""},
        )

    def _resolve_command(self) -> list[str]:
        if self._command:
            return list(self._command)

        configured = os.environ.get("FASTAMODELLER_BIN", "").strip()
        if configured:
            return shlex.split(configured)

        for executable in ("fastamodeller", "fastaModeller"):
            found = shutil.which(executable)
            if found:
                self._command = [found]
                return self._command

        try:
            has_package = util.find_spec("fastamodeller") is not None
        except (ImportError, ValueError):
            has_package = False

        if has_package:
            if is_frozen():
                self._command = [sys.executable, "--fastamodeller"]
            else:
                self._command = [sys.executable, "-m", "fastamodeller"]
            return self._command

        raise GeneratorUnavailable(
            "The fastamodeller command line tool was not found.\n"
            "Install it with: pip install fastamodeller==1.0.0"
        )

    @staticmethod
    def _extract_seed(stderr: str, fallback: int | None) -> int | None:
        match = _SEED_PATTERN.search(stderr or "")
        if match:
            return int(match.group(1))
        return fallback

    @staticmethod
    def _error_text(result: subprocess.CompletedProcess[str]) -> str:
        message = (result.stderr or result.stdout or "").strip()
        if not message:
            message = f"fastamodeller exited with code {result.returncode}"
        return message
