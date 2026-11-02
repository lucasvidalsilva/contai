from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest

from contai_tax_data.ncm import QualityPolicy
from contai_tax_data.postgres import catalog_ncm_capture, publish_ncm_release, stage_ncm_release
from contai_tax_data.source import NCM_SOURCE_URL, RetrievedArtifact
from contai_tax_data.storage import ingest_ncm_artifact

DATABASE_URL = os.environ.get("CONTAI_TEST_DATABASE_URL")
REAL_DATA_DIR = os.environ.get("CONTAI_REAL_DATA_DIR")
pytestmark = pytest.mark.skipif(DATABASE_URL is None, reason="PostgreSQL isolado nao iniciado")

FIXTURES = Path(__file__).parents[1] / "fixtures"
SAMPLE = FIXTURES / "ncm-current-sample.json"
SAMPLE_POLICY = QualityPolicy(min_entries=8, max_entries=20, min_leaf_entries=2, min_chapters=2)
CAPTURED_AT = datetime(2026, 10, 30, 23, 31, 50, tzinfo=UTC)


def _artifact(body: bytes, captured_at: datetime) -> RetrievedArtifact:
    return RetrievedArtifact(
        requested_url=NCM_SOURCE_URL,
        final_url=f"{NCM_SOURCE_URL}?perfil=PUBLICO",
        status=200,
        headers={"content-type": "application/json"},
        body=body,
        captured_at=captured_at,
    )


def test_stage_publish_idempotency_access_and_atomic_rollback(tmp_path: Path) -> None:
    assert DATABASE_URL is not None
    first = ingest_ncm_artifact(_artifact(SAMPLE.read_bytes(), CAPTURED_AT), tmp_path, quality_policy=SAMPLE_POLICY)

    with psycopg.connect(DATABASE_URL) as connection:
        staged = stage_ncm_release(connection, tmp_path, quality_policy=SAMPLE_POLICY)
        repeated_stage = stage_ncm_release(connection, tmp_path, quality_policy=SAMPLE_POLICY)
        assert staged.release_created is True
        assert repeated_stage.release_created is False

        published = publish_ncm_release(connection, first.release_id)
        repeated_publish = publish_ncm_release(connection, first.release_id)
        assert published.published is True
        assert repeated_publish.published is False

        header_only = SAMPLE.read_bytes().replace(b"Vigente em 30/10/2026", b"Vigente em 31/10/2026")
        recapture = ingest_ncm_artifact(
            _artifact(header_only, CAPTURED_AT + timedelta(days=1)), tmp_path, quality_policy=SAMPLE_POLICY
        )
        assert recapture.release_id == first.release_id
        cataloged = catalog_ncm_capture(connection, tmp_path, recapture.artifact_sha256, quality_policy=SAMPLE_POLICY)
        repeated_catalog = catalog_ncm_capture(
            connection, tmp_path, recapture.artifact_sha256, quality_policy=SAMPLE_POLICY
        )
        assert cataloged.artifact_created is True
        assert repeated_catalog.artifact_created is False
        assert connection.execute(
            "select count(*) from tax_ingest.source_artifact where source_key = %s", ("siscomex-ncm",)
        ).fetchone() == (2,)
        assert connection.execute(
            "select byte_size, raw_content from tax_ingest.source_artifact_payload where artifact_sha256 = %s",
            (recapture.artifact_sha256,),
        ).fetchone() == (len(header_only), header_only)
        assert connection.execute(
            "select count(*) from tax_ingest.source_artifact_observation where source_key = %s",
            ("siscomex-ncm",),
        ).fetchone() == (2,)
        assert connection.execute(
            "select count(*) from tax_ingest.ingestion_run where artifact_sha256 = %s",
            (recapture.artifact_sha256,),
        ).fetchone() == (1,)
        assert connection.execute(
            "select artifact_sha256 from tax_ingest.dataset_release where release_id = %s", (first.release_id,)
        ).fetchone() == (first.artifact_sha256,)

        with connection.transaction():
            connection.execute("set local role anon")
            current = connection.execute("select code from tax_public.ncm_current order by code").fetchall()
            assert len(current) == 8
        with pytest.raises(psycopg.errors.InsufficientPrivilege), connection.transaction():
            connection.execute("set local role anon")
            connection.execute("select * from tax_ingest.source_registry").fetchall()
        with pytest.raises(psycopg.errors.InsufficientPrivilege), connection.transaction():
            connection.execute("set local role anon")
            connection.execute("select * from tax_ingest.source_artifact_payload").fetchall()
        with pytest.raises(psycopg.errors.InsufficientPrivilege), connection.transaction():
            connection.execute("set local role anon")
            connection.execute("select * from tax_ingest.source_artifact_observation").fetchall()
        connection.commit()

        changed = SAMPLE.read_text(encoding="utf-8").replace("Animais vivos.", "Animais vivos e descritos.").encode()
        second = ingest_ncm_artifact(
            _artifact(changed, CAPTURED_AT + timedelta(days=1)), tmp_path, quality_policy=SAMPLE_POLICY
        )
        stage_ncm_release(connection, tmp_path, quality_policy=SAMPLE_POLICY)

        connection.execute("""
            create function public.reject_test_pointer() returns trigger
            language plpgsql as $$
            begin
              raise exception 'falha injetada antes da troca do ponteiro';
            end
            $$;
            create trigger reject_test_pointer
            before update on tax_public.dataset_current
            for each row execute function public.reject_test_pointer();
        """)
        connection.commit()

        with pytest.raises(psycopg.DatabaseError, match="falha injetada"):
            publish_ncm_release(connection, second.release_id)

        current_release = connection.execute(
            "select release_id from tax_public.dataset_current where domain = 'ncm'"
        ).fetchone()
        assert current_release == (first.release_id,)
        assert connection.execute(
            "select count(*) from tax_public.dataset_release where release_id = %s", (second.release_id,)
        ).fetchone() == (0,)
        assert connection.execute(
            "select status from tax_ingest.dataset_release where release_id = %s", (second.release_id,)
        ).fetchone() == ("candidate",)

        connection.execute("drop trigger reject_test_pointer on tax_public.dataset_current")
        connection.execute("drop function public.reject_test_pointer()")
        connection.commit()
        assert publish_ncm_release(connection, second.release_id).published is True


@pytest.mark.skipif(REAL_DATA_DIR is None, reason="captura oficial local nao informada")
def test_complete_official_capture_can_be_staged_and_published() -> None:
    assert DATABASE_URL is not None
    assert REAL_DATA_DIR is not None

    with psycopg.connect(DATABASE_URL) as connection:
        staged = stage_ncm_release(connection, Path(REAL_DATA_DIR))
        published = publish_ncm_release(connection, staged.release_id)
        public_count = connection.execute("select count(*) from tax_public.ncm_current").fetchone()

    assert staged.entry_count == 15_157
    assert staged.leaf_count == 10_516
    assert published.published is True
    assert public_count == (15_157,)
