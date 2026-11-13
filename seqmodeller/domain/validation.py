"""Pure validation rules shared by the GUI and the generation service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .models import AppState, InsertSpec, RepeatSpec, SequenceBatch
from .molecules import MOLECULES, get_molecule

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    message: str
    severity: str = ERROR

    def __str__(self) -> str:
        prefix = "Error" if self.severity == ERROR else "Warning"
        return f"{prefix} in {self.path}: {self.message}"


def has_errors(issues: list[ValidationIssue]) -> bool:
    return any(issue.severity == ERROR for issue in issues)


def format_issues(issues: list[ValidationIssue], limit: int = 12) -> str:
    lines = [str(issue) for issue in issues[:limit]]
    if len(issues) > limit:
        lines.append(f"... and {len(issues) - limit} more issue(s)")
    return "\n".join(lines)


def _validate_composition(
    molecule_key: str, composition: dict[str, float], path: str
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    molecule = get_molecule(molecule_key)
    if not composition:
        return [ValidationIssue(path, "the composition cannot be empty")]
    for symbol, weight in composition.items():
        if symbol not in molecule.allowed:
            issues.append(
                ValidationIssue(
                    f"{path}.{symbol}",
                    f"symbol '{symbol}' is not valid for the {molecule.label} alphabet",
                )
            )
        try:
            numeric_weight = float(weight)
        except (TypeError, ValueError):
            issues.append(
                ValidationIssue(f"{path}.{symbol}", "the weight must be a number")
            )
            continue
        if numeric_weight <= 0:
            issues.append(
                ValidationIssue(
                    f"{path}.{symbol}", "the weight must be greater than zero"
                )
            )
    return issues


def _validate_repeat(
    repeat: RepeatSpec, molecule_key: str, path: str
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    molecule = get_molecule(molecule_key)
    if not 0 <= repeat.likelihood <= 1:
        issues.append(
            ValidationIssue(f"{path}.likelihood", "must be between 0 and 1")
        )
    if repeat.pattern_min_reps < 0:
        issues.append(
            ValidationIssue(f"{path}.pattern_min_reps", "must be zero or greater")
        )
    if repeat.pattern_max_reps < 0:
        issues.append(
            ValidationIssue(f"{path}.pattern_max_reps", "must be zero or greater")
        )
    if repeat.pattern_min_reps > repeat.pattern_max_reps:
        issues.append(
            ValidationIssue(
                f"{path}.pattern_min_reps",
                "cannot be greater than pattern_max_reps",
            )
        )
    pattern = molecule.normalize_sequence(repeat.pattern)
    if repeat.likelihood > 0 and not pattern:
        issues.append(
            ValidationIssue(
                f"{path}.pattern",
                "cannot be empty when likelihood is greater than zero",
            )
        )
    if pattern:
        invalid = molecule.invalid_symbols(pattern)
        if invalid:
            issues.append(
                ValidationIssue(
                    f"{path}.pattern",
                    f"contains symbols outside the {molecule.label} alphabet: "
                    f"{', '.join(invalid)}",
                )
            )
    if repeat.likelihood > 0 and repeat.pattern_max_reps < 1:
        issues.append(
            ValidationIssue(
                f"{path}.pattern_max_reps",
                "should be at least 1 when likelihood is greater than zero",
                WARNING,
            )
        )
    return issues


def _validate_insert(
    insert: InsertSpec, batch: SequenceBatch, molecule_key: str, path: str
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    molecule = get_molecule(molecule_key)
    if insert.total < 0:
        issues.append(ValidationIssue(f"{path}.total", "must be zero or greater"))
    if insert.min_split < 0:
        issues.append(
            ValidationIssue(f"{path}.min_split", "must be zero or greater")
        )
    if insert.max_split < 0:
        issues.append(
            ValidationIssue(f"{path}.max_split", "must be zero or greater")
        )
    if insert.min_split > insert.max_split:
        issues.append(
            ValidationIssue(
                f"{path}.min_split", "cannot be greater than max_split"
            )
        )
    if insert.ave_gap < 0:
        issues.append(ValidationIssue(f"{path}.ave_gap", "must be zero or greater"))
    if insert.sd_gap < 0:
        issues.append(ValidationIssue(f"{path}.sd_gap", "must be zero or greater"))
    if not 0 <= insert.mutation_rate < 1:
        issues.append(
            ValidationIssue(
                f"{path}.mutation_rate", "must be greater than or equal to 0 and lower than 1"
            )
        )

    sequence = molecule.normalize_sequence(insert.sequence)
    if insert.total > 0 and not sequence:
        issues.append(
            ValidationIssue(
                f"{path}.sequence",
                "cannot be empty when total is greater than zero",
            )
        )
    if sequence:
        invalid = molecule.invalid_symbols(sequence)
        if invalid:
            issues.append(
                ValidationIssue(
                    f"{path}.sequence",
                    f"contains symbols outside the {molecule.label} alphabet: "
                    f"{', '.join(invalid)}",
                )
            )
        max_allowed_split = max(0, len(sequence) - 2)
        if insert.max_split > max_allowed_split:
            issues.append(
                ValidationIssue(
                    f"{path}.max_split",
                    f"cannot exceed {max_allowed_split} for an insert of "
                    f"length {len(sequence)}",
                )
            )
    elif insert.max_split > 0:
        issues.append(
            ValidationIssue(
                f"{path}.max_split",
                "must be zero when the insert sequence is empty",
            )
        )

    if insert.mutation_rate > 0 and len(batch.composition) < 2:
        issues.append(
            ValidationIssue(
                f"{path}.mutation_rate",
                "requires a composition with at least two symbols",
            )
        )
    return issues


def validate_batch(batch: SequenceBatch, molecule_key: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    path = f"sequences[{batch.base_id}]"
    if not batch.base_id or any(char.isspace() for char in batch.base_id):
        issues.append(
            ValidationIssue(
                f"{path}.base_id",
                "must be non-empty and cannot contain whitespace",
            )
        )
    if batch.generate < 0:
        issues.append(ValidationIssue(f"{path}.generate", "must be zero or greater"))
    if batch.min_len < 0:
        issues.append(ValidationIssue(f"{path}.min_len", "must be zero or greater"))
    if batch.max_len < 0:
        issues.append(ValidationIssue(f"{path}.max_len", "must be zero or greater"))
    if batch.min_len > batch.max_len:
        issues.append(
            ValidationIssue(
                f"{path}.min_len", "cannot be greater than max_len"
            )
        )
    issues.extend(
        _validate_composition(
            molecule_key, batch.composition, f"{path}.proportion"
        )
    )
    for index, repeat in enumerate(batch.repeats):
        issues.extend(
            _validate_repeat(
                repeat, molecule_key, f"{path}.repeats[{index}]"
            )
        )
    for index, insert in enumerate(batch.inserts):
        issues.extend(
            _validate_insert(
                insert, batch, molecule_key, f"{path}.inserts[{index}]"
            )
        )
    return issues


def validate_state(state: AppState) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    molecule_key = state.settings.molecule
    if molecule_key not in MOLECULES:
        issues.append(
            ValidationIssue(
                "molecule",
                f"unknown molecule '{molecule_key}'. Valid values: "
                f"{', '.join(sorted(MOLECULES))}",
            )
        )
        molecule_key = "dna"
    if state.settings.id_padding < 0:
        issues.append(
            ValidationIssue("id_padding", "must be zero or greater")
        )
    if state.settings.seq_wrap is not None and state.settings.seq_wrap < 1:
        issues.append(
            ValidationIssue("seq_wrap", "must be a positive integer or disabled")
        )
    if state.settings.seed is not None and state.settings.seed < 0:
        issues.append(ValidationIssue("seed", "must be zero or greater"))
    if not state.batches:
        issues.append(ValidationIssue("sequences", "add at least one sequence batch"))
    for batch in state.batches.values():
        issues.extend(validate_batch(batch, molecule_key))
    return issues


def validate_output_paths(
    fasta: str | None, report: str | None, config: str | None
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    provided = [path for path in (fasta, report, config) if path]
    if not provided:
        issues.append(
            ValidationIssue(
                "output", "select at least one output file (FASTA, report or config)"
            )
        )
        return issues

    seen: dict[str, str] = {}
    for label, path in (("FASTA", fasta), ("report", report), ("config", config)):
        if not path:
            continue
        resolved = os.path.normcase(str(Path(path).expanduser().resolve()))
        if resolved in seen:
            issues.append(
                ValidationIssue(
                    "output",
                    f"the {label} and {seen[resolved]} outputs point to the same file",
                )
            )
        else:
            seen[resolved] = label
    return issues
