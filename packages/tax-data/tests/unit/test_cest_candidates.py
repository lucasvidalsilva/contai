import json
from pathlib import Path

import pytest

from contai_tax_data.cest_candidates import (
    CestCandidateContractError,
    extract_cest_candidate_artifact,
    parse_cest_candidates,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "cest_table_sample.html"


def test_candidate_parser_preserves_source_values_and_unresolved_status() -> None:
    candidates = parse_cest_candidates(FIXTURE.read_bytes())

    assert len(candidates) == 2
    assert candidates[0].cest_code == "01.001.00"
    assert candidates[0].ncm_sh_raw == "3815.12.10 3815.12.90"
    assert candidates[0].legal_status == "unresolved"
    assert candidates[1].cest_code == "01.002.00"
    assert candidates[1].description == "Redação histórica preservada"
    assert candidates[1].legal_status == "unresolved"


def test_candidate_parser_does_not_treat_nested_table_cells_as_columns() -> None:
    body = (
        b"<table><tr><td>ITEM</td><td>CEST</td><td>NCM/SH</td><td>DESCRICAO</td></tr>"
        b"<tr><td>1</td><td>01.001.00</td><td>3815</td><td>texto antes"
        b"<table><tr><td>layout</td></tr></table>texto depois</td></tr></table>"
    )

    candidates = parse_cest_candidates(body)

    assert len(candidates) == 1
    assert candidates[0].description == "texto antestexto depois"


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (b"<html><table><tr><td>other schema</td></tr></table></html>", "cabecalho"),
        (
            b"<html><table><tr><td>ITEM</td><td>CEST</td><td>NCM/SH</td><td>DESCRICAO</td></tr></table></html>",
            "nenhuma linha",
        ),
        (b"\xff", "UTF-8"),
    ],
)
def test_candidate_parser_rejects_schema_drift_or_malformed_input(body: bytes, message: str) -> None:
    with pytest.raises(CestCandidateContractError, match=message):
        parse_cest_candidates(body)


def test_candidate_extraction_is_immutable_and_idempotent(tmp_path: Path) -> None:
    artifact = tmp_path / "source.html"
    artifact.write_bytes(FIXTURE.read_bytes())

    first = extract_cest_candidate_artifact(artifact, tmp_path / "store")
    second = extract_cest_candidate_artifact(artifact, tmp_path / "store")

    assert first.candidate_count == 2
    assert first.candidate_set_sha256 == second.candidate_set_sha256
    assert first.candidates_created and first.manifest_created
    assert not second.candidates_created and not second.manifest_created
    rows = (tmp_path / "store" / first.candidates_path).read_text(encoding="utf-8").splitlines()
    assert all(json.loads(row)["legal_status"] == "unresolved" for row in rows)
