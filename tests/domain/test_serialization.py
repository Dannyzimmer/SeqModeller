from __future__ import annotations

import pytest

from seqmodeller.domain.models import AppState, InsertSpec, RepeatSpec
from seqmodeller.domain.molecules import PROTEIN, RNA
from seqmodeller.domain.serialization import config_to_state, state_to_config
from seqmodeller.domain.validation import has_errors, validate_state
from seqmodeller.errors import ConfigFormatError


def test_state_roundtrip_preserves_batches_and_composition():
    state = AppState()
    batch = state.new_batch("TEST")
    batch.composition = {"A": 0.2, "T": 0.2, "C": 0.3, "G": 0.3}
    batch.repeats.append(
        RepeatSpec(likelihood=0.5, pattern="atcg", pattern_min_reps=2, pattern_max_reps=5)
    )
    batch.inserts.append(
        InsertSpec(total=2, min_split=0, max_split=2, sequence="acgtacgt")
    )
    state.add_batch(batch)

    config = state_to_config(state)
    assert config["molecule"] == "dna"
    assert config["sequences"][0]["repeats"][0]["pattern"] == "ATCG"

    restored, issues = config_to_state(config)
    assert not issues
    restored_batch = restored.batches["TEST"]
    assert restored_batch.composition == batch.composition
    assert restored_batch.repeats[0].pattern == "ATCG"
    assert restored_batch.inserts[0].sequence == "ACGTACGT"


def test_old_config_without_new_fields_is_migrated():
    old_config = {
        "id_padding": 4,
        "seq_wrap": False,
        "seed": False,
        "sequences": [
            {
                "base_id": "OLD",
                "generate": 1,
                "max_len": 10,
                "min_len": 5,
                "proportion": {"A": 0.25, "T": 0.25, "C": 0.25, "G": 0.25},
            }
        ],
    }
    state, issues = config_to_state(old_config)
    assert not issues
    assert state.settings.molecule == "dna"
    assert state.settings.seq_wrap is None
    assert state.settings.seed is None
    assert state.batches["OLD"].repeats == []
    assert state.batches["OLD"].inserts == []


def test_duplicate_base_id_is_rejected():
    config = {
        "sequences": [
            {"base_id": "DUP", "generate": 1, "min_len": 1, "max_len": 2},
            {"base_id": "DUP", "generate": 1, "min_len": 1, "max_len": 2},
        ]
    }
    with pytest.raises(ConfigFormatError):
        config_to_state(config)


def test_validation_matches_engine_rules():
    state = AppState()
    batch = state.new_batch("BAD")
    batch.min_len = 20
    batch.max_len = 10
    batch.composition = {"A": 0, "T": 1, "C": 1, "G": 1}
    batch.inserts.append(
        InsertSpec(total=1, max_split=100, mutation_rate=1.0, sequence="ACGT")
    )
    state.add_batch(batch)
    issues = validate_state(state)
    assert has_errors(issues)
    messages = "\n".join(issue.message for issue in issues)
    assert "greater than zero" in messages
    assert "greater than max_len" in messages
    assert "lower than 1" in messages
    assert "cannot exceed" in messages


def test_rna_and_protein_alphabets_are_supported():
    for molecule in (RNA, PROTEIN):
        state = AppState()
        state.settings.molecule = molecule.key
        batch = state.new_batch("BATCH")
        batch.composition = molecule.default_composition()
        state.add_batch(batch)
        assert not has_errors(validate_state(state))
        config = state_to_config(state)
        assert config["molecule"] == molecule.key


def test_output_path_collisions_are_reported():
    from seqmodeller.domain.validation import validate_output_paths

    issues = validate_output_paths("/tmp/a.fasta", "/tmp/a.fasta", "")
    assert has_errors(issues)
    assert "same file" in issues[0].message
