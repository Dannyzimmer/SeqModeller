from __future__ import annotations

import json
from pathlib import Path

import pytest

from seqmodeller.errors import GeneratorUnavailable
from seqmodeller.services.fastamodeller_cli import FastamodellerCli
from seqmodeller.services.generator import GenerationRequest


def sample_config(molecule: str = "dna") -> dict:
    symbol = "A"
    return {
        "molecule": molecule,
        "id_padding": 4,
        "seq_wrap": 70,
        "seed": False,
        "sequences": [
            {
                "base_id": "TEST",
                "generate": 2,
                "min_len": 10,
                "max_len": 20,
                "proportion": {symbol: 1.0},
            }
        ],
    }


def test_extract_seed():
    assert FastamodellerCli._extract_seed("Seed: 12345\n", None) == 12345
    assert FastamodellerCli._extract_seed("no seed", 7) == 7


def test_version_and_validation(tmp_path: Path):
    cli = FastamodellerCli()
    assert cli.version()
    cli.ensure_available()
    output = cli.validate(sample_config())
    assert "batches=1" in output


def test_generate_fasta_report_and_config(tmp_path: Path):
    cli = FastamodellerCli()
    fasta = tmp_path / "out.fasta"
    report = tmp_path / "report.txt"
    config_path = tmp_path / "config.json"

    outcome = cli.generate(
        GenerationRequest(
            config=sample_config(),
            fasta_path=fasta,
            report_path=report,
            config_path=config_path,
        )
    )

    assert outcome.seed is not None
    assert fasta.exists() and fasta.read_text(encoding="utf-8").startswith(">TEST")
    assert report.exists() and "SEED" in report.read_text(encoding="utf-8")
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["seed"] == outcome.seed


def test_generate_report_only(tmp_path: Path):
    cli = FastamodellerCli()
    report = tmp_path / "report.txt"
    outcome = cli.generate(
        GenerationRequest(config=sample_config(), report_path=report)
    )
    assert outcome.seed is not None
    assert report.read_text(encoding="utf-8").startswith("SEED")


def test_config_only_skips_generation(tmp_path: Path):
    cli = FastamodellerCli()
    config_path = tmp_path / "config.json"
    outcome = cli.generate(
        GenerationRequest(config=sample_config(), config_path=config_path)
    )
    assert outcome.seed is None
    assert config_path.exists()


def test_missing_command_reports_clear_error(tmp_path: Path):
    cli = FastamodellerCli(command=[str(tmp_path / "missing-fastamodeller")])
    with pytest.raises(GeneratorUnavailable):
        cli.generate(
            GenerationRequest(
                config=sample_config(), fasta_path=tmp_path / "out.fasta"
            )
        )
