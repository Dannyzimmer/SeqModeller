"""Application state models.

The GUI keeps a single :class:`AppState` instance.  All widgets read from and
write to these plain Python objects, which keeps the presentation layer free of
business rules and makes the state easy to test.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .molecules import DEFAULT_MOLECULE, Molecule, get_molecule


@dataclass
class InsertSpec:
    total: int = 0
    min_split: int = 0
    max_split: int = 0
    ave_gap: float = 0.0
    sd_gap: float = 0.0
    mutation_rate: float = 0.0
    sequence: str = ""

    def copy(self) -> InsertSpec:
        return InsertSpec(
            total=self.total,
            min_split=self.min_split,
            max_split=self.max_split,
            ave_gap=self.ave_gap,
            sd_gap=self.sd_gap,
            mutation_rate=self.mutation_rate,
            sequence=self.sequence,
        )


@dataclass
class RepeatSpec:
    likelihood: float = 0.0
    pattern: str = ""
    pattern_min_reps: int = 1
    pattern_max_reps: int = 1

    def copy(self) -> RepeatSpec:
        return RepeatSpec(
            likelihood=self.likelihood,
            pattern=self.pattern,
            pattern_min_reps=self.pattern_min_reps,
            pattern_max_reps=self.pattern_max_reps,
        )


@dataclass
class SequenceBatch:
    base_id: str
    generate: int = 1
    min_len: int = 500
    max_len: int = 1000
    composition: dict[str, float] = field(default_factory=dict)
    repeats: list[RepeatSpec] = field(default_factory=list)
    inserts: list[InsertSpec] = field(default_factory=list)

    def copy(self) -> SequenceBatch:
        return SequenceBatch(
            base_id=self.base_id,
            generate=self.generate,
            min_len=self.min_len,
            max_len=self.max_len,
            composition=dict(self.composition),
            repeats=[repeat.copy() for repeat in self.repeats],
            inserts=[insert.copy() for insert in self.inserts],
        )


@dataclass
class GeneralSettings:
    molecule: str = DEFAULT_MOLECULE.key
    id_padding: int = 4
    seq_wrap: int | None = 70
    seed: int | None = None

    @property
    def molecule_info(self) -> Molecule:
        return get_molecule(self.molecule)


@dataclass
class OutputPaths:
    fasta: str = ""
    report: str = ""
    config: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "fasta_path": self.fasta,
            "report_path": self.report,
            "config_json_path": self.config,
        }


@dataclass
class AppState:
    settings: GeneralSettings = field(default_factory=GeneralSettings)
    batches: dict[str, SequenceBatch] = field(default_factory=dict)
    output: OutputPaths = field(default_factory=OutputPaths)
    current_config_path: str | None = None
    dirty: bool = False

    def new_batch(self, base_id: str) -> SequenceBatch:
        molecule = self.settings.molecule_info
        return SequenceBatch(
            base_id=base_id,
            composition=molecule.default_composition(),
        )

    def add_batch(self, batch: SequenceBatch) -> None:
        if batch.base_id in self.batches:
            raise ValueError(f"Duplicate base_id: {batch.base_id}")
        self.batches[batch.base_id] = batch

    def remove_batch(self, base_id: str) -> SequenceBatch | None:
        return self.batches.pop(base_id, None)

    def rename_batch(self, old_id: str, new_id: str) -> None:
        if old_id not in self.batches:
            raise KeyError(old_id)
        if new_id in self.batches:
            raise ValueError(f"Duplicate base_id: {new_id}")
        items = list(self.batches.items())
        self.batches.clear()
        for key, batch in items:
            if key == old_id:
                batch.base_id = new_id
                self.batches[new_id] = batch
            else:
                self.batches[key] = batch

    def replace_with(self, other: AppState) -> None:
        self.settings = other.settings
        self.batches = other.batches
        self.output = other.output
        self.current_config_path = other.current_config_path
        self.dirty = other.dirty
