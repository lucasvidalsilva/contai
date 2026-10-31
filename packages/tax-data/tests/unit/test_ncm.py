from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from contai_tax_data.ncm import (
    NcmContractError,
    NcmQualityError,
    QualityPolicy,
    parse_ncm_json,
    validate_ncm,
)

FIXTURES = Path(__file__).parents[1] / "fixtures"
SAMPLE = FIXTURES / "ncm-current-sample.json"
EXPECTED = FIXTURES / "ncm-current-sample.normalized.jsonl"
SAMPLE_POLICY = QualityPolicy(min_entries=8, max_entries=20, min_leaf_entries=2, min_chapters=2)


def sample_object() -> dict[str, object]:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def encoded(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode()


def test_normalizes_official_sample_deterministically() -> None:
    dataset = parse_ncm_json(SAMPLE.read_bytes())
    validate_ncm(dataset, SAMPLE_POLICY)

    assert len(dataset.entries) == 8
    assert dataset.leaf_count == 2
    assert dataset.source_act == "Resolução Gecex nº 926/2026"
    assert dataset.snapshot_jsonl() == EXPECTED.read_bytes().rstrip(b"\n") + b"\n"


def test_preserves_leading_zeroes_and_derives_nearest_existing_parent() -> None:
    dataset = parse_ncm_json(SAMPLE.read_bytes())
    by_code = {entry.code: entry for entry in dataset.entries}

    assert by_code["01"].code_digits == "01"
    assert by_code["0101.21.00"].parent_code == "0101.2"
    assert by_code["3913.90.50"].parent_code == "3913.90"


def test_daily_as_of_header_does_not_create_a_new_release_identity() -> None:
    first = parse_ncm_json(SAMPLE.read_bytes())
    another_day = SAMPLE.read_text(encoding="utf-8").replace("Vigente em 30/10/2026", "Vigente em 31/10/2026")
    second = parse_ncm_json(another_day.encode())

    assert first.source_as_of != second.source_as_of
    assert first.release_id == second.release_id


def test_rejects_malformed_json() -> None:
    with pytest.raises(NcmContractError, match="malformado"):
        parse_ncm_json(b'{"Nomenclaturas": [')


def test_rejects_schema_change() -> None:
    value = sample_object()
    rows = value["Nomenclaturas"]
    assert isinstance(rows, list)
    assert isinstance(rows[0], dict)
    rows[0]["Campo_Novo"] = "nao aceito silenciosamente"

    with pytest.raises(NcmContractError, match="schema mudou"):
        parse_ncm_json(encoded(value))


def test_rejects_duplicate_code() -> None:
    value = sample_object()
    rows = value["Nomenclaturas"]
    assert isinstance(rows, list)
    rows.append(copy.deepcopy(rows[0]))

    with pytest.raises(NcmContractError, match="duplicado"):
        parse_ncm_json(encoded(value))


def test_rejects_inverted_validity_during_quality_checks() -> None:
    value = sample_object()
    rows = value["Nomenclaturas"]
    assert isinstance(rows, list)
    assert isinstance(rows[0], dict)
    rows[0]["Data_Fim"] = "30/09/2026"
    dataset = parse_ncm_json(encoded(value))

    with pytest.raises(NcmQualityError, match="vigencia invertida"):
        validate_ncm(dataset, SAMPLE_POLICY)
