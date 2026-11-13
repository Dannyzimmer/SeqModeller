"""Conversion between the GUI state and the fastamodeller JSON schema."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..errors import ConfigFormatError
from .models import (
    AppState,
    GeneralSettings,
    InsertSpec,
    RepeatSpec,
    SequenceBatch,
)
from .molecules import MOLECULES, get_molecule
from .validation import ValidationIssue


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigFormatError(f"'{field}' must be a JSON object")
    return value


def _sequence(value: Any, field: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ConfigFormatError(f"'{field}' must be a JSON array")
    return value


def _to_int(
    value: Any,
    field: str,
    default: int,
    issues: list[ValidationIssue],
    *,
    minimum: int | None = None,
) -> int:
    if isinstance(value, bool):
        issues.append(ValidationIssue(field, "must be an integer, not a boolean"))
        return default
    try:
        result = int(value)
    except (TypeError, ValueError):
        issues.append(ValidationIssue(field, f"must be an integer, got {value!r}"))
        return default
    if minimum is not None and result < minimum:
        issues.append(
            ValidationIssue(field, f"must be greater than or equal to {minimum}")
        )
        return default
    return result


def _to_float(
    value: Any,
    field: str,
    default: float,
    issues: list[ValidationIssue],
    *,
    minimum: float | None = None,
) -> float:
    if isinstance(value, bool):
        issues.append(ValidationIssue(field, "must be a number, not a boolean"))
        return default
    try:
        result = float(value)
    except (TypeError, ValueError):
        issues.append(ValidationIssue(field, f"must be a number, got {value!r}"))
        return default
    if minimum is not None and result < minimum:
        issues.append(
            ValidationIssue(field, f"must be greater than or equal to {minimum}")
        )
        return default
    return result


def _parse_seed(value: Any, issues: list[ValidationIssue]) -> int | None:
    if value is None or value is False:
        return None
    if value is True:
        issues.append(ValidationIssue("seed", "must be an integer, not a boolean"))
        return None
    if isinstance(value, int):
        if value < 0:
            issues.append(ValidationIssue("seed", "must be zero or greater"))
            return None
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = int(text)
        except ValueError:
            issues.append(ValidationIssue("seed", f"must be an integer, got {value!r}"))
            return None
        if parsed < 0:
            issues.append(ValidationIssue("seed", "must be zero or greater"))
            return None
        return parsed
    issues.append(ValidationIssue("seed", f"must be an integer, got {value!r}"))
    return None


def _parse_seq_wrap(value: Any, issues: list[ValidationIssue]) -> int | None:
    if value is None or value is False or value == 0:
        return None
    if value is True:
        issues.append(ValidationIssue("seq_wrap", "must be a positive integer or false"))
        return None
    result = _to_int(value, "seq_wrap", 70, issues, minimum=1)
    return result


def _parse_composition(
    value: Any, molecule_key: str, issues: list[ValidationIssue], path: str
) -> dict[str, float]:
    molecule = get_molecule(molecule_key)
    if value is None:
        return molecule.default_composition()
    if not isinstance(value, Mapping):
        issues.append(
            ValidationIssue(path, "must be an object with one weight per symbol")
        )
        return molecule.default_composition()

    composition: dict[str, float] = {}
    for raw_symbol, raw_weight in value.items():
        symbol = str(raw_symbol).strip().upper()
        weight = _to_float(raw_weight, f"{path}.{symbol}", 1.0, issues, minimum=0.0)
        composition[symbol] = weight
    if not composition:
        issues.append(ValidationIssue(path, "cannot be empty"))
        return molecule.default_composition()
    return composition


def _parse_repeat(
    value: Any, issues: list[ValidationIssue], path: str
) -> RepeatSpec | None:
    if not isinstance(value, Mapping):
        issues.append(ValidationIssue(path, "must be an object"))
        return None
    return RepeatSpec(
        likelihood=_to_float(value.get("likelihood", 0.0), f"{path}.likelihood", 0.0, issues),
        pattern=str(value.get("pattern", "")),
        pattern_min_reps=_to_int(
            value.get("pattern_min_reps", 0), f"{path}.pattern_min_reps", 0, issues
        ),
        pattern_max_reps=_to_int(
            value.get("pattern_max_reps", 0), f"{path}.pattern_max_reps", 0, issues
        ),
    )


def _parse_insert(
    value: Any, issues: list[ValidationIssue], path: str
) -> InsertSpec | None:
    if not isinstance(value, Mapping):
        issues.append(ValidationIssue(path, "must be an object"))
        return None
    return InsertSpec(
        total=_to_int(value.get("total", 0), f"{path}.total", 0, issues),
        min_split=_to_int(value.get("min_split", 0), f"{path}.min_split", 0, issues),
        max_split=_to_int(value.get("max_split", 0), f"{path}.max_split", 0, issues),
        ave_gap=_to_float(value.get("ave_gap", 0.0), f"{path}.ave_gap", 0.0, issues),
        sd_gap=_to_float(value.get("sd_gap", 0.0), f"{path}.sd_gap", 0.0, issues),
        mutation_rate=_to_float(
            value.get("mutation_rate", 0.0),
            f"{path}.mutation_rate",
            0.0,
            issues,
        ),
        sequence=str(value.get("sequence", "")),
    )


def config_to_state(
    raw: Mapping[str, Any] | Any,
) -> tuple[AppState, list[ValidationIssue]]:
    """Parse a configuration mapping, migrating old SeqModeller files."""
    data = _mapping(raw, "configuration")
    issues: list[ValidationIssue] = []

    molecule_value = str(data.get("molecule", "dna")).strip().lower()
    if molecule_value not in MOLECULES:
        issues.append(
            ValidationIssue(
                "molecule",
                f"unknown molecule '{molecule_value}'. Valid values: "
                f"{', '.join(sorted(MOLECULES))}",
            )
        )
        molecule_value = "dna"

    settings = GeneralSettings(
        molecule=molecule_value,
        id_padding=_to_int(data.get("id_padding", 4), "id_padding", 4, issues),
        seq_wrap=_parse_seq_wrap(data.get("seq_wrap", 70), issues),
        seed=_parse_seed(data.get("seed", False), issues),
    )

    sequences_raw = _sequence(data.get("sequences"), "sequences")
    if not sequences_raw:
        raise ConfigFormatError("'sequences' must contain at least one batch")

    batches: dict[str, SequenceBatch] = {}
    for index, item in enumerate(sequences_raw):
        if not isinstance(item, Mapping):
            raise ConfigFormatError(f"'sequences[{index}]' must be an object")
        base_id = str(item.get("base_id", "")).strip()
        if not base_id:
            raise ConfigFormatError(f"'sequences[{index}].base_id' cannot be empty")
        if base_id in batches:
            raise ConfigFormatError(f"Duplicate base_id '{base_id}' in 'sequences'")
        path = f"sequences[{index}]"

        repeats_raw = item.get("repeats", [])
        if repeats_raw is None:
            repeats_raw = []
        repeats: list[RepeatSpec] = []
        for position, repeat_raw in enumerate(
            _sequence(repeats_raw, f"{path}.repeats")
        ):
            repeat = _parse_repeat(
                repeat_raw, issues, f"{path}.repeats[{position}]"
            )
            if repeat is not None:
                repeats.append(repeat)

        inserts_raw = item.get("inserts", [])
        if inserts_raw is None:
            inserts_raw = []
        inserts: list[InsertSpec] = []
        for position, insert_raw in enumerate(
            _sequence(inserts_raw, f"{path}.inserts")
        ):
            insert = _parse_insert(
                insert_raw, issues, f"{path}.inserts[{position}]"
            )
            if insert is not None:
                inserts.append(insert)

        batches[base_id] = SequenceBatch(
            base_id=base_id,
            generate=_to_int(item.get("generate", 1), f"{path}.generate", 1, issues),
            min_len=_to_int(item.get("min_len", 0), f"{path}.min_len", 0, issues),
            max_len=_to_int(item.get("max_len", 0), f"{path}.max_len", 0, issues),
            composition=_parse_composition(
                item.get("proportion"), molecule_value, issues, f"{path}.proportion"
            ),
            repeats=repeats,
            inserts=inserts,
        )

    state = AppState(settings=settings, batches=batches)
    return state, issues


def state_to_config(state: AppState) -> dict[str, Any]:
    """Serialize the application state to the fastamodeller schema."""
    molecule = state.settings.molecule_info
    return {
        "molecule": molecule.key,
        "id_padding": state.settings.id_padding,
        "seq_wrap": state.settings.seq_wrap if state.settings.seq_wrap is not None else False,
        "seed": state.settings.seed if state.settings.seed is not None else False,
        "sequences": [
            {
                "base_id": batch.base_id,
                "generate": batch.generate,
                "min_len": batch.min_len,
                "max_len": batch.max_len,
                "proportion": {
                    symbol: float(weight)
                    for symbol, weight in batch.composition.items()
                },
                "repeats": [
                    {
                        "likelihood": repeat.likelihood,
                        "pattern": molecule.normalize_sequence(repeat.pattern),
                        "pattern_min_reps": repeat.pattern_min_reps,
                        "pattern_max_reps": repeat.pattern_max_reps,
                    }
                    for repeat in batch.repeats
                ],
                "inserts": [
                    {
                        "total": insert.total,
                        "min_split": insert.min_split,
                        "max_split": insert.max_split,
                        "ave_gap": insert.ave_gap,
                        "sd_gap": insert.sd_gap,
                        "mutation_rate": insert.mutation_rate,
                        "sequence": molecule.normalize_sequence(insert.sequence),
                    }
                    for insert in batch.inserts
                ],
            }
            for batch in state.batches.values()
        ],
    }
