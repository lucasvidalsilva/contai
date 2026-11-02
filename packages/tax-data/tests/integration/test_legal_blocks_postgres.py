from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg
import pytest

from contai_tax_data.legal_blocks_postgres import stage_legal_blocks

DATABASE_URL = os.environ.get("CONTAI_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(DATABASE_URL is None, reason="PostgreSQL isolado nao iniciado")
REPOSITORY_ROOT = Path(__file__).parents[4]
DATA_ROOT = REPOSITORY_ROOT / "var" / "tax-data"


def _capture_paths(
    capture_root: Path,
    pointer_path: Path,
    snapshot_pointer_path: Path,
    observation_root: Path | None = None,
) -> tuple[Path, ...]:
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    snapshot_pointer = json.loads(snapshot_pointer_path.read_text(encoding="utf-8"))
    observation_path = (
        (observation_root or capture_root)
        / "artifacts"
        / "observations"
        / pointer["artifact_sha256"]
        / f"{pointer['captured_at'].replace(':', '-')}.json"
    )
    observation = json.loads(observation_path.read_text(encoding="utf-8"))
    artifact_path = capture_root / observation["raw_path"]
    snapshot_path = capture_root / snapshot_pointer["snapshot_path"]
    manifest_path = snapshot_path.with_name("manifest.json")
    return artifact_path, observation_path, manifest_path, snapshot_path, capture_root


def _official_captures() -> list[tuple[Path, ...]]:
    captures: list[tuple[Path, ...]] = []

    confaz_root = DATA_ROOT / "confaz"
    for act_root in sorted((confaz_root / "acts").iterdir()):
        if not act_root.is_dir() or not (act_root / "state" / "latest-capture.json").is_file():
            continue
        captures.append(
            _capture_paths(
                confaz_root,
                act_root / "state" / "latest-capture.json",
                act_root / "state" / "latest-extraction.json",
                act_root,
            )
        )

    law_root = DATA_ROOT / "laws" / "lc214"
    captures.append(
        _capture_paths(
            law_root,
            law_root / "state" / "lc214-latest-capture.json",
            law_root / "state" / "lc214-latest-blocks.json",
        )
    )
    for record_id in ("original", "veto", "promulgation"):
        record_root = law_root / "records" / record_id
        captures.append(
            _capture_paths(
                record_root,
                record_root / "state" / "latest-capture.json",
                record_root / "state" / "latest-blocks.json",
            )
        )
    return captures


def test_official_legal_block_snapshots_stage_privately_and_idempotently() -> None:
    assert DATABASE_URL is not None
    captures = _official_captures()
    assert len(captures) == 28

    with psycopg.connect(DATABASE_URL) as connection:
        connection.prepare_threshold = None
        first_results = [stage_legal_blocks(connection, *capture) for capture in captures]
        second_results = [stage_legal_blocks(connection, *capture) for capture in captures]

        assert all(result.block_set_created for result in first_results)
        assert not any(result.block_set_created for result in second_results)
        assert sum(result.block_count for result in first_results) == 12_966
        assert connection.execute("select count(*) from tax_ingest.legal_block_set").fetchone()[0] == 28
        assert connection.execute("select count(*) from tax_ingest.legal_document_block").fetchone()[0] == 12_966
        assert (
            connection.execute(
                """
                select count(*) from tax_ingest.legal_document_block
                where source_key = 'camara-lc214-current'
                  and marker_kind = 'article' and marker = '10'
                """
            ).fetchone()[0]
            > 0
        )
        assert (
            connection.execute("select count(*) from tax_public.dataset_release where domain = 'cest'").fetchone()[0]
            == 0
        )
        connection.execute("set role anon")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("select * from tax_ingest.legal_document_block").fetchall()


def test_legal_block_stage_rejects_tampered_snapshot_before_insert(tmp_path: Path) -> None:
    assert DATABASE_URL is not None
    artifact, observation, manifest, snapshot, capture_root = _official_captures()[-1]
    copied_snapshot = tmp_path / "tampered.jsonl"
    tampered_snapshot = bytearray(snapshot.read_bytes())
    tampered_snapshot[0] = ord("!")
    copied_snapshot.write_bytes(tampered_snapshot)
    copied_manifest = tmp_path / "manifest.json"
    copied_manifest.write_bytes(manifest.read_bytes())

    with psycopg.connect(DATABASE_URL) as connection:
        connection.prepare_threshold = None
        existing_count = connection.execute("select count(*) from tax_ingest.legal_block_set").fetchone()[0]
        with pytest.raises(ValueError):
            stage_legal_blocks(connection, artifact, observation, copied_manifest, copied_snapshot, capture_root)
        assert connection.execute("select count(*) from tax_ingest.legal_block_set").fetchone()[0] == existing_count
