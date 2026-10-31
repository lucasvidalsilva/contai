from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

import psycopg
import pytest
from openpyxl import Workbook

from contai_tax_data.postgres import publish_tipi_release, stage_tipi_release
from contai_tax_data.source import RetrievedArtifact
from contai_tax_data.tipi import TIPI_SOURCE_URL
from contai_tax_data.tipi_storage import ingest_tipi_artifact

DATABASE_URL = os.environ.get("CONTAI_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(DATABASE_URL is None, reason="PostgreSQL isolado nao iniciado")
CAPTURED_AT = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(*, changed: bool = False) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Aprovada pelo Decreto nº 11.158/2022", None, None, None])
    sheet.append(["Atualizações: ADE RFB 001/2026", None, None, None])
    sheet.append(["NCM", "EX", "DESCRIÇÃO", "ALÍQUOTA (%)"])
    sheet.append(["0101.21.00", None, "Reprodutores de raça pura", "NT"])
    sheet.append(["0201.10.00", None, "Carcaças e meias-carcaças", 0])
    sheet.append(["0210.91.00", "Ex 01", "Miudezas; farinhas e pós dessas miudezas", "NT"])
    if changed:
        sheet.append(["9706.10.00", None, "Com mais de 250 anos", "NT"])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _artifact(body: bytes, captured_at: datetime) -> RetrievedArtifact:
    return RetrievedArtifact(
        requested_url=TIPI_SOURCE_URL,
        final_url=TIPI_SOURCE_URL,
        status=200,
        headers={"content-type": CONTENT_TYPE},
        body=body,
        captured_at=captured_at,
    )


def _capture(body: bytes, output: Path, captured_at: datetime):
    return ingest_tipi_artifact(
        _artifact(body, captured_at),
        output,
        minimum_entries=3,
        maximum_entries=4,
        minimum_ex_entries=1,
    )


def _stage(connection: psycopg.Connection, output: Path):
    return stage_tipi_release(
        connection,
        output,
        minimum_entries=3,
        maximum_entries=4,
        minimum_ex_entries=1,
    )


def test_tipi_stage_publish_idempotency_access_and_atomic_rollback(tmp_path: Path) -> None:
    assert DATABASE_URL is not None
    output = tmp_path / "tipi"
    first = _capture(_xlsx(), output, CAPTURED_AT)

    with psycopg.connect(DATABASE_URL) as connection:
        staged = _stage(connection, output)
        repeated_stage = _stage(connection, output)
        assert staged.release_created is True
        assert repeated_stage.release_created is False

        published = publish_tipi_release(connection, first.release_id)
        repeated_publish = publish_tipi_release(connection, first.release_id)
        assert published.published is True
        assert repeated_publish.published is False

        with connection.transaction():
            connection.execute("set local role anon")
            current = connection.execute("select ncm_code, ex_code, ipi_rate from tax_public.tipi_current").fetchall()
            assert len(current) == 3
            assert connection.execute(
                "select source_as_of from tax_public.dataset_release where release_id = %s", (first.release_id,)
            ).fetchone() == (None,)
        with pytest.raises(psycopg.errors.InsufficientPrivilege), connection.transaction():
            connection.execute("set local role anon")
            connection.execute("select * from tax_ingest.source_registry").fetchall()

        second = _capture(_xlsx(changed=True), output, CAPTURED_AT + timedelta(days=1))
        _stage(connection, output)
        connection.execute("""
            create function public.reject_tipi_pointer() returns trigger
            language plpgsql as $$
            begin
              if new.domain = 'tipi' then
                raise exception 'falha injetada antes da troca do ponteiro TIPI';
              end if;
              return new;
            end
            $$;
            create trigger reject_tipi_pointer
            before update on tax_public.dataset_current
            for each row execute function public.reject_tipi_pointer();
        """)
        connection.commit()

        with pytest.raises(psycopg.DatabaseError, match="falha injetada antes da troca do ponteiro TIPI"):
            publish_tipi_release(connection, second.release_id)

        current_release = connection.execute(
            "select release_id from tax_public.dataset_current where domain = 'tipi'"
        ).fetchone()
        assert current_release == (first.release_id,)
        assert connection.execute(
            "select count(*) from tax_public.dataset_release where release_id = %s", (second.release_id,)
        ).fetchone() == (0,)
        assert connection.execute(
            "select status from tax_ingest.dataset_release where release_id = %s", (second.release_id,)
        ).fetchone() == ("candidate",)

        connection.execute("drop trigger reject_tipi_pointer on tax_public.dataset_current")
        connection.execute("drop function public.reject_tipi_pointer()")
        connection.commit()
        assert publish_tipi_release(connection, second.release_id).published is True
