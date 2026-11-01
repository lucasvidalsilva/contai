from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from contai_tax_data.cest_candidates import extract_cest_candidate_artifact
from contai_tax_data.cest_capture import capture_cest_artifact
from contai_tax_data.cest_postgres import stage_cest_candidates
from contai_tax_data.source import RetrievedArtifact

DATABASE_URL = os.environ.get("CONTAI_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(DATABASE_URL is None, reason="PostgreSQL isolado nao iniciado")
FIXTURE = Path(__file__).parents[1] / "fixtures" / "cest_table_sample.html"
CAPTURED_AT = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def test_cest_candidate_stage_is_private_immutable_and_idempotent(tmp_path: Path) -> None:
    assert DATABASE_URL is not None
    body = FIXTURE.read_bytes()
    artifact = RetrievedArtifact(
        requested_url="https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18",
        final_url="https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18",
        status=200,
        headers={"content-type": "text/html; charset=utf-8"},
        body=body,
        captured_at=CAPTURED_AT,
    )
    capture = capture_cest_artifact(artifact, tmp_path)
    extraction = extract_cest_candidate_artifact(tmp_path / capture.raw_path, tmp_path)
    candidates_path = tmp_path / extraction.candidates_path
    observation_path = (
        tmp_path
        / "artifacts"
        / "observations"
        / capture.artifact_sha256
        / (f"{CAPTURED_AT.isoformat().replace('+00:00', 'Z').replace(':', '-')}.json")
    )

    with psycopg.connect(DATABASE_URL) as connection:
        first = stage_cest_candidates(connection, candidates_path, observation_path, tmp_path)
        repeated = stage_cest_candidates(connection, candidates_path, observation_path, tmp_path)
        assert first.candidate_set_created is True
        assert repeated.candidate_set_created is False
        assert first.candidate_set_sha256 == extraction.candidate_set_sha256
        assert first.candidate_count == 3
        assert (
            connection.execute(
                "select count(*) from tax_ingest.cest_candidate where candidate_set_sha256 = %s",
                (first.candidate_set_sha256,),
            ).fetchone()[0]
            == 3
        )
        assert (
            connection.execute(
                "select count(*) from tax_ingest.cest_candidate where legal_status <> 'unresolved'"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "select count(*) from tax_ingest.cest_candidate_set where status <> 'candidates_unresolved'"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute("select count(*) from tax_public.dataset_release where domain = 'cest'").fetchone()[0]
            == 0
        )
        connection.execute("set role anon")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("select * from tax_ingest.cest_candidate").fetchall()


def test_cest_candidate_stage_rejects_snapshot_tampering_before_insert(tmp_path: Path) -> None:
    assert DATABASE_URL is not None
    body = FIXTURE.read_bytes()
    artifact = RetrievedArtifact(
        requested_url="https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18",
        final_url="https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18",
        status=200,
        headers={"content-type": "text/html"},
        body=body,
        captured_at=CAPTURED_AT,
    )
    capture = capture_cest_artifact(artifact, tmp_path)
    extraction = extract_cest_candidate_artifact(tmp_path / capture.raw_path, tmp_path)
    candidates_path = tmp_path / extraction.candidates_path
    candidates_path.write_bytes(candidates_path.read_bytes().replace(b"3815.12.10", b"3815.12.11"))
    observation_path = (
        tmp_path
        / "artifacts"
        / "observations"
        / capture.artifact_sha256
        / (f"{CAPTURED_AT.isoformat().replace('+00:00', 'Z').replace(':', '-')}.json")
    )

    with psycopg.connect(DATABASE_URL) as connection, pytest.raises(ValueError, match="hash do snapshot"):
        stage_cest_candidates(connection, candidates_path, observation_path, tmp_path)
