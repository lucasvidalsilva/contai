from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
import pytest

from contai_tax_data.ibs_cbs import IBS_CBS_SOURCE_URL
from contai_tax_data.ibs_cbs_storage import ingest_ibs_cbs_artifact
from contai_tax_data.postgres import publish_ibs_cbs_release, stage_ibs_cbs_release
from contai_tax_data.source import RetrievedArtifact

DATABASE_URL = os.environ.get("CONTAI_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(DATABASE_URL is None, reason="PostgreSQL isolado nao iniciado")
CAPTURED_AT = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
FIXTURE = Path(__file__).parent.parent / "fixtures" / "ibs_cbs_page.html"
_DATA = re.compile(rb"var dadosOriginais = (\[.*?\]);\s*var dadosFiltrados", re.DOTALL)


def _page(*, changed: bool = False) -> bytes:
    match = _DATA.search(FIXTURE.read_bytes())
    assert match
    data: list[dict[str, Any]] = json.loads(match.group(1))
    template = data[0]["ClassificacoesTributarias"][0]
    data[0]["ClassificacoesTributarias"] = []
    for number in range(1, 101):
        classification = json.loads(json.dumps(template, ensure_ascii=False))
        classification["CodClassTrib"] = f"{number:06d}"
        classification["Anexos"][0]["CodIntProdServ"] = number
        if changed and number == 1:
            classification["NomeClassTrib"] = "Descrição atualizada"
        data[0]["ClassificacoesTributarias"].append(classification)
    return (
        b"<html><script>var dadosOriginais = "
        + json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        + b"; var dadosFiltrados = [];</script></html>"
    )


def _capture(body: bytes, output: Path, captured_at: datetime):
    return ingest_ibs_cbs_artifact(
        RetrievedArtifact(
            requested_url=IBS_CBS_SOURCE_URL,
            final_url=IBS_CBS_SOURCE_URL,
            status=200,
            headers={"content-type": "text/html; charset=utf-8"},
            body=body,
            captured_at=captured_at,
        ),
        output,
    )


def test_ibs_cbs_stage_publish_idempotency_access_and_atomic_rollback(tmp_path: Path) -> None:
    assert DATABASE_URL is not None
    output = tmp_path / "ibs-cbs"
    first = _capture(_page(), output, CAPTURED_AT)

    with psycopg.connect(DATABASE_URL) as connection:
        staged = stage_ibs_cbs_release(connection, output)
        repeated_stage = stage_ibs_cbs_release(connection, output)
        assert staged.release_created is True
        assert repeated_stage.release_created is False
        assert staged.entry_count == 100

        published = publish_ibs_cbs_release(connection, first.release_id)
        repeated_publish = publish_ibs_cbs_release(connection, first.release_id)
        assert published.published is True
        assert repeated_publish.published is False

        with connection.transaction():
            connection.execute("set local role anon")
            classes = connection.execute("select count(*) from tax_public.ibs_cbs_classification_current").fetchone()
            annexes = connection.execute("select count(*) from tax_public.ibs_cbs_annex_current").fetchone()
            assert classes == (100,)
            assert annexes == (100,)
        with pytest.raises(psycopg.errors.InsufficientPrivilege), connection.transaction():
            connection.execute("set local role anon")
            connection.execute("select * from tax_ingest.source_registry").fetchall()

        second = _capture(_page(changed=True), output, CAPTURED_AT + timedelta(days=1))
        stage_ibs_cbs_release(connection, output)
        connection.execute(
            """
            create function public.reject_ibs_cbs_pointer() returns trigger
            language plpgsql as $$
            begin
              if new.domain = 'ibs_cbs' then
                raise exception 'falha injetada antes da troca do ponteiro IBS/CBS';
              end if;
              return new;
            end
            $$;
            create trigger reject_ibs_cbs_pointer
            before update on tax_public.dataset_current
            for each row execute function public.reject_ibs_cbs_pointer();
            """
        )
        connection.commit()

        with pytest.raises(psycopg.DatabaseError, match="falha injetada antes da troca do ponteiro IBS/CBS"):
            publish_ibs_cbs_release(connection, second.release_id)

        current_release = connection.execute(
            "select release_id from tax_public.dataset_current where domain = 'ibs_cbs'"
        ).fetchone()
        assert current_release == (first.release_id,)
        assert connection.execute(
            "select count(*) from tax_public.dataset_release where release_id = %s", (second.release_id,)
        ).fetchone() == (0,)
        assert connection.execute(
            "select status from tax_ingest.dataset_release where release_id = %s", (second.release_id,)
        ).fetchone() == ("candidate",)

        connection.execute("drop trigger reject_ibs_cbs_pointer on tax_public.dataset_current")
        connection.execute("drop function public.reject_ibs_cbs_pointer()")
        connection.commit()
        assert publish_ibs_cbs_release(connection, second.release_id).published is True
