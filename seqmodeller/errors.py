"""Application exception hierarchy."""

from __future__ import annotations


class SeqModellerError(Exception):
    """Base class for expected application errors."""


class ConfigFormatError(SeqModellerError):
    """The JSON configuration is structurally invalid."""


class ValidationError(SeqModellerError):
    """The configuration does not satisfy the engine rules."""


class GeneratorUnavailable(SeqModellerError):
    """The fastamodeller command line tool is not available."""


class OutputError(SeqModellerError):
    """An input or output file could not be read or written."""


class GenerationError(SeqModellerError):
    """The external generator failed."""


class GenerationCancelled(GenerationError):
    """The user cancelled a running generation."""
