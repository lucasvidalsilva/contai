from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from contai_tax_data.ncm import QualityPolicy
from contai_tax_data.postgres import load_local_ncm_release
from contai_tax_data.source import NCM_SOURCE_URL, RetrievedArtifact
from contai_tax_data.storage import ingest_ncm_artifact

FIXTURES = Path(__file__).parents[1] / "fixtures"
SAMPLE = FIXTURES / "ncm-current-sample.json"
SAMPLE_POLICY = QualityPolicy(min_entries=8, max_entries=20, min_leaf_entries=2, min_chapters=2)


def _create_release(root: Path) -> str:
    result = ingest_ncm_artifact(
        RetrievedArtifact(
            requested_url=NCM_SOURCE_URL,
            final_url=f"{NCM_SOURCE_URL}?perfil=PUBLICO",
            status=200,
            headers={"content-type": "application/json"},
            body=SAMPLE.read_bytes(),
            captured_at=datetime(2026, 10, 30, 23, 31, 50, tzinfo=UTC),
        ),
        root,
        quality_policy=SAMPLE_POLICY,
    )
    return result.release_id


def test_load_local_release_reprocesses_original(tmp_path: Path) -> None:
    release_id = _create_release(tmp_path)

    local = load_local_ncm_release(tmp_path)

    assert local.release_id == release_id
    assert len(local.dataset.entries) == 8
    assert local.dataset.leaf_count == 2


def test_load_local_release_rejects_tampered_snapshot(tmp_path: Path) -> None:
    release_id = _create_release(tmp_path)
    snapshot = tmp_path / "releases" / release_id / "ncm.jsonl"
    snapshot.write_bytes(snapshot.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="hash do snapshot"):
        load_local_ncm_release(tmp_path, release_id)
