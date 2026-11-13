"""Sequence alphabets supported by fastamodeller."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Molecule:
    key: str
    label: str
    canonical: tuple[str, ...]
    ambiguous: tuple[str, ...] = ()
    extra: tuple[str, ...] = ()
    nucleic: bool = False

    @property
    def allowed(self) -> frozenset[str]:
        return frozenset(self.canonical + self.ambiguous + self.extra)

    def sorted_symbols(self) -> list[str]:
        return [*self.canonical, *self.ambiguous, *self.extra]

    def default_composition(self) -> dict[str, float]:
        return {symbol: 1.0 for symbol in self.canonical}

    def normalize_sequence(self, sequence: str) -> str:
        return "".join(str(sequence).split()).upper()

    def invalid_symbols(self, sequence: str) -> list[str]:
        normalized = self.normalize_sequence(sequence)
        return sorted({symbol for symbol in normalized if symbol not in self.allowed})


DNA = Molecule(
    key="dna",
    label="DNA",
    canonical=("A", "C", "G", "T"),
    ambiguous=("R", "Y", "S", "W", "K", "M", "B", "D", "H", "V", "N"),
    nucleic=True,
)

RNA = Molecule(
    key="rna",
    label="RNA",
    canonical=("A", "C", "G", "U"),
    ambiguous=("R", "Y", "S", "W", "K", "M", "B", "D", "H", "V", "N"),
    nucleic=True,
)

PROTEIN = Molecule(
    key="protein",
    label="Protein",
    canonical=(
        "A",
        "C",
        "D",
        "E",
        "F",
        "G",
        "H",
        "I",
        "K",
        "L",
        "M",
        "N",
        "P",
        "Q",
        "R",
        "S",
        "T",
        "V",
        "W",
        "Y",
    ),
    ambiguous=("B", "Z", "X", "J"),
    extra=("U", "O"),
    nucleic=False,
)

MOLECULES: dict[str, Molecule] = {
    molecule.key: molecule for molecule in (DNA, RNA, PROTEIN)
}
DEFAULT_MOLECULE = DNA


def get_molecule(key: str | None) -> Molecule:
    if not key:
        return DEFAULT_MOLECULE
    return MOLECULES.get(str(key).strip().lower(), DEFAULT_MOLECULE)
