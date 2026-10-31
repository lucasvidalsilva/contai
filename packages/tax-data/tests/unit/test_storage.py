from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from contai_tax_data.ncm import NcmContractError, QualityPolicy
from contai_tax_data.source import NCM_SOURCE_URL, RetrievedArtifact
from contai_tax_data.storage import ingest_ncm_artifact

FIXTURES = Path(__file__).parents[1] / "fixtures"
SAMPLE = FIXTURES / "ncm-current-sample.json"
SAMPLE_POLICY = QualityPolicy(min_entries=8, max_entries=20, min_leaf_entries=2, min_chapters=2)
CAPTURED_AT = datetime(2026, 10, 30, 23, 31, 50, tzinfo=UTC)


def artifact(body: bytes, *, captured_at: datetime = CAPTURED_AT) -> RetrievedArtifact:
    return RetrievedArtifact(
        requested_url=NCM_SOURCE_URL,
        final_url=f"{NCM_SOURCE_URL}?perfil=PUBLICO",
        status=200,
        headers={
            "content-type": "application/json",
            "content-disposition": "attachment;filename=Tabela_NCM_Vigente_20261030.json",
            "cache-control": "public, max-age=3600",
        },
        body=body,
        captured_at=captured_at,
    )


def test_identical_rerun_creates_neither_artifact_nor_release(tmp_path: Path) -> None:
    first = ingest_ncm_artifact(artifact(SAMPLE.read_bytes()), tmp_path, quality_policy=SAMPLE_POLICY)
    second = ingest_ncm_artifact(
        artifact(SAMPLE.read_bytes(), captured_at=CAPTURED_AT + timedelta(minutes=5)),
        tmp_path,
        quality_policy=SAMPLE_POLICY,
    )

    assert first.artifact_created is True
    assert first.release_created is True
    assert first.diff.added == 8
    assert second.artifact_created is False
    assert second.release_created is False
    assert second.release_id == first.release_id
    assert second.diff.added == second.diff.changed == second.diff.removed == 0
    assert len(list((tmp_path / "releases").iterdir())) == 1


def test_daily_header_change_archives_new_raw_without_new_release(tmp_path: Path) -> None:
    first = ingest_ncm_artifact(artifact(SAMPLE.read_bytes()), tmp_path, quality_policy=SAMPLE_POLICY)
    next_day = SAMPLE.read_text(encoding="utf-8").replace("Vigente em 30/10/2026", "Vigente em 31/10/2026").encode()
    second = ingest_ncm_artifact(
        artifact(next_day, captured_at=CAPTURED_AT + timedelta(days=1)),
        tmp_path,
        quality_policy=SAMPLE_POLICY,
    )

    assert second.artifact_created is True
    assert second.release_created is False
    assert second.release_id == first.release_id
    assert len(list((tmp_path / "artifacts" / "manifests").glob("*.json"))) == 2


def test_real_change_creates_release_and_diff(tmp_path: Path) -> None:
    first = ingest_ncm_artifact(artifact(SAMPLE.read_bytes()), tmp_path, quality_policy=SAMPLE_POLICY)
    changed = SAMPLE.read_text(encoding="utf-8").replace("Animais vivos.", "Animais vivos e descritos.").encode()
    second = ingest_ncm_artifact(
        artifact(changed, captured_at=CAPTURED_AT + timedelta(days=1)),
        tmp_path,
        quality_policy=SAMPLE_POLICY,
    )

    assert second.release_created is True
    assert second.release_id != first.release_id
    assert second.diff.changed == 1
    assert second.diff.added == second.diff.removed == 0
    pointer = json.loads((tmp_path / "state" / "ncm-current.json").read_text(encoding="utf-8"))
    assert pointer["release_id"] == second.release_id


def test_schema_change_is_archived_and_quarantined_without_release(tmp_path: Path) -> None:
    value = json.loads(SAMPLE.read_text(encoding="utf-8"))
    value["Nomenclaturas"][0]["Campo_Novo"] = "mudanca"
    changed_schema = json.dumps(value, ensure_ascii=False).encode()

    with pytest.raises(NcmContractError, match="schema mudou"):
        ingest_ncm_artifact(artifact(changed_schema), tmp_path, quality_policy=SAMPLE_POLICY)

    assert len(list((tmp_path / "artifacts" / "sha256").rglob("*.json"))) == 1
    assert len(list((tmp_path / "quarantine").glob("*.json"))) == 1
    assert not (tmp_path / "state" / "ncm-current.json").exists()
