from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import Workbook

from contai_tax_data.postgres import load_local_tipi_release
from contai_tax_data.source import RetrievedArtifact
from contai_tax_data.tipi import TIPI_SOURCE_URL, TipiContractError
from contai_tax_data.tipi_storage import ingest_tipi_artifact

CAPTURED_AT = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def workbook_bytes(*, changed: bool = False, bad_header: bool = False) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Atualizações: Ato Declaratório Executivo RFB nº 1/2026", None, None, None])
    sheet.append(["NCM", "EX" if not bad_header else "Exceção", "DESCRIÇÃO", "ALÍQUOTA (%)"])
    sheet.append(["0101.21.00", None, "-- Reprodutores de raça pura", "NT"])
    sheet.append(["0201.10.00", None, "- Carcaças e meias-carcaças", 0])
    sheet.append(["0210.91.00", "Ex 01", "Miudezas; farinhas e pós dessas miudezas", "NT"])
    if changed:
        sheet.append(["9706.10.00", None, "- Com mais de 250 anos", "NT"])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def artifact(body: bytes, *, captured_at: datetime = CAPTURED_AT) -> RetrievedArtifact:
    return RetrievedArtifact(
        requested_url=TIPI_SOURCE_URL,
        final_url=TIPI_SOURCE_URL,
        status=200,
        headers={"content-type": CONTENT_TYPE},
        body=body,
        captured_at=captured_at,
    )


def ingest(body: bytes, output: Path, *, captured_at: datetime = CAPTURED_AT):
    return ingest_tipi_artifact(
        artifact(body, captured_at=captured_at),
        output,
        minimum_entries=3,
        maximum_entries=4,
        minimum_ex_entries=1,
    )


def test_identical_artifact_is_idempotent(tmp_path: Path) -> None:
    body = workbook_bytes()
    first = ingest(body, tmp_path)
    second = ingest(body, tmp_path, captured_at=CAPTURED_AT + timedelta(minutes=5))

    assert first.release_created is True
    assert first.diff.added == 3
    assert second.artifact_created is False
    assert second.release_created is False
    assert second.release_id == first.release_id
    assert second.diff == type(second.diff)(added=0, changed=0, removed=0)
    assert len(list((tmp_path / "releases").iterdir())) == 1


def test_changed_xlsx_creates_diff_and_release(tmp_path: Path) -> None:
    first = ingest(workbook_bytes(), tmp_path)
    second = ingest(workbook_bytes(changed=True), tmp_path, captured_at=CAPTURED_AT + timedelta(days=1))

    assert second.release_id != first.release_id
    assert second.release_created is True
    assert second.diff.added == 1
    assert second.diff.changed == second.diff.removed == 0
    pointer = json.loads((tmp_path / "state" / "tipi-current.json").read_text(encoding="utf-8"))
    assert pointer["release_id"] == second.release_id


def test_schema_failure_is_quarantined_and_keeps_previous_release(tmp_path: Path) -> None:
    valid = ingest(workbook_bytes(), tmp_path)

    with pytest.raises(TipiContractError, match="cabeçalho"):
        ingest(workbook_bytes(bad_header=True), tmp_path, captured_at=CAPTURED_AT + timedelta(days=1))

    pointer = json.loads((tmp_path / "state" / "tipi-current.json").read_text(encoding="utf-8"))
    assert pointer["release_id"] == valid.release_id
    assert len(list((tmp_path / "releases").iterdir())) == 1
    assert len(list((tmp_path / "quarantine").glob("*.json"))) == 1


def test_local_release_is_reverified_before_database_staging(tmp_path: Path) -> None:
    result = ingest(workbook_bytes(), tmp_path)
    loaded = load_local_tipi_release(
        tmp_path,
        result.release_id,
        minimum_entries=3,
        maximum_entries=4,
        minimum_ex_entries=1,
    )

    assert loaded.release_id == result.release_id
    assert loaded.snapshot_sha256
    assert len(loaded.dataset.entries) == 3

    raw_path = tmp_path / "artifacts" / "sha256" / f"{result.artifact_sha256}.xlsx"
    raw_path.write_bytes(raw_path.read_bytes() + b"tampering")
    with pytest.raises(ValueError, match="hash do XLSX bruto diverge"):
        load_local_tipi_release(
            tmp_path,
            result.release_id,
            minimum_entries=3,
            maximum_entries=4,
            minimum_ex_entries=1,
        )
