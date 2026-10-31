"""Testes offline do contrato publico e da captura IBS/CBS."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from contai_tax_data.ibs_cbs import (
    IbsCbsContractError,
    IbsCbsQualityError,
    parse_ibs_cbs_html,
    validate_ibs_cbs,
)
from contai_tax_data.ibs_cbs_storage import ingest_ibs_cbs_artifact
from contai_tax_data.postgres import load_local_ibs_cbs_release
from contai_tax_data.source import RetrievedArtifact

FIXTURE = Path(__file__).parent.parent / "fixtures" / "ibs_cbs_page.html"
_DATA = re.compile(rb"var dadosOriginais = (\[.*?\]);\s*var dadosFiltrados", re.DOTALL)


def _page_data(body: bytes) -> list[dict[str, Any]]:
    match = _DATA.search(body)
    assert match
    return json.loads(match.group(1))


def _page(rows: list[dict[str, Any]]) -> bytes:
    encoded = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return b"<script>var dadosOriginais = " + encoded + b"; var dadosFiltrados = [];</script>"


def _large_page() -> bytes:
    data = _page_data(FIXTURE.read_bytes())
    template = data[0]["ClassificacoesTributarias"][0]
    data[0]["ClassificacoesTributarias"] = []
    for number in range(1, 101):
        classification = json.loads(json.dumps(template, ensure_ascii=False))
        classification["CodClassTrib"] = f"{number:06d}"
        classification["Anexos"][0]["CodIntProdServ"] = number
        data[0]["ClassificacoesTributarias"].append(classification)
    return _page(data)


def _artifact(
    body: bytes,
    *,
    content_type: str = "text/html",
    captured_at: datetime = datetime(2026, 10, 31, 12, 0, tzinfo=UTC),
) -> RetrievedArtifact:
    return RetrievedArtifact(
        requested_url="https://dfe-portal.svrs.rs.gov.br/CFF/ClassificacaoTributaria",
        final_url="https://dfe-portal.svrs.rs.gov.br/CFF/ClassificacaoTributaria",
        status=200,
        headers={"content-type": content_type},
        body=body,
        captured_at=captured_at,
    )


def test_parses_public_cst_classification_and_annex_fixture() -> None:
    dataset = parse_ibs_cbs_html(FIXTURE.read_bytes())

    assert len(dataset.csts) == 1
    assert dataset.classifications[0]["CodClassTrib"] == "000002"
    assert dataset.annex_links[0]["cclasstrib_code"] == "000002"
    assert dataset.annex_links[0]["CodNcmNbs"] == "106042100"
    assert "CtrDthInc" not in dataset.classifications[0]


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (b"<html>sem catalogo</html>", "dadosOriginais.*nao encontrado"),
        (b"<script>var dadosOriginais = [{]; var dadosFiltrados = [];</script>", "JSON.*malformado"),
    ],
)
def test_rejects_missing_or_malformed_source_json(body: bytes, message: str) -> None:
    with pytest.raises(IbsCbsContractError, match=message):
        parse_ibs_cbs_html(body)


def test_rejects_source_schema_changes_and_duplicate_classifications() -> None:
    data = _page_data(FIXTURE.read_bytes())
    data[0]["NovaColuna"] = "surpresa"
    with pytest.raises(IbsCbsContractError, match="schema CST"):
        parse_ibs_cbs_html(_page(data))

    data = _page_data(FIXTURE.read_bytes())
    data[0]["ClassificacoesTributarias"].append(data[0]["ClassificacoesTributarias"][0])
    with pytest.raises(IbsCbsContractError, match="duplicado"):
        parse_ibs_cbs_html(_page(data))


def test_quality_policy_rejects_unexpected_volume() -> None:
    dataset = parse_ibs_cbs_html(FIXTURE.read_bytes())
    with pytest.raises(IbsCbsQualityError, match="cClassTrib"):
        validate_ibs_cbs(dataset)


def test_capture_is_idempotent_and_rejected_schema_keeps_current_release(tmp_path: Path) -> None:
    body = _large_page()
    first = ingest_ibs_cbs_artifact(_artifact(body), tmp_path)
    second = ingest_ibs_cbs_artifact(_artifact(body), tmp_path)

    assert first.release_created is True
    assert first.classification_count == 100
    assert first.annex_link_count == 100
    assert second.release_created is False
    assert second.release_id == first.release_id
    assert (tmp_path / "state" / "ibs-cbs-current.json").read_text(encoding="utf-8").find(first.release_id) >= 0

    malformed = body.replace(b'"Cst":"000"', b'"Cst":"000","NovaColuna":true', 1)
    with pytest.raises(IbsCbsContractError, match="schema CST"):
        ingest_ibs_cbs_artifact(_artifact(malformed), tmp_path)
    assert first.release_id in (tmp_path / "state" / "ibs-cbs-current.json").read_text(encoding="utf-8")
    assert list((tmp_path / "quarantine").glob("*.json"))


def test_release_diff_tracks_changed_classification(tmp_path: Path) -> None:
    data = _page_data(_large_page())
    first = ingest_ibs_cbs_artifact(_artifact(_page(data)), tmp_path)
    data[0]["ClassificacoesTributarias"][0]["NomeClassTrib"] = "descricao alterada"
    second = ingest_ibs_cbs_artifact(_artifact(_page(data)), tmp_path)

    assert first.release_id != second.release_id
    assert second.changed == 1


def test_artifact_format_change_without_semantic_change_keeps_release(tmp_path: Path) -> None:
    body = _large_page()
    first = ingest_ibs_cbs_artifact(_artifact(body), tmp_path)
    second = ingest_ibs_cbs_artifact(
        _artifact(
            body.replace(b"var dadosFiltrados", b"\nvar dadosFiltrados"),
            captured_at=datetime(2026, 10, 31, 13, tzinfo=UTC),
        ),
        tmp_path,
    )

    assert first.artifact_sha256 != second.artifact_sha256
    assert first.release_id == second.release_id
    assert second.artifact_created is True
    assert second.release_created is False


def test_rejects_unexpected_content_type(tmp_path: Path) -> None:
    with pytest.raises(IbsCbsContractError, match="Content-Type inesperado"):
        ingest_ibs_cbs_artifact(_artifact(_large_page(), content_type="application/json"), tmp_path)

    assert not (tmp_path / "state" / "ibs-cbs-current.json").exists()
    assert list((tmp_path / "quarantine").glob("*.json"))


def test_source_unavailable_does_not_create_a_release(tmp_path: Path) -> None:
    class UnavailableSource:
        def fetch(self, url: str) -> RetrievedArtifact:
            raise OSError("source unavailable")

    from contai_tax_data.ibs_cbs_storage import capture_ibs_cbs

    with pytest.raises(OSError, match="source unavailable"):
        capture_ibs_cbs(tmp_path, client=UnavailableSource())

    assert not (tmp_path / "state" / "ibs-cbs-current.json").exists()


def test_local_release_revalidates_source_artifact_and_snapshot(tmp_path: Path) -> None:
    artifact = _artifact(_large_page())
    result = ingest_ibs_cbs_artifact(artifact, tmp_path)
    local = load_local_ibs_cbs_release(tmp_path, result.release_id)
    assert local.release_id == result.release_id
    assert local.byte_size == len(artifact.body)

    raw = tmp_path / local.raw_path
    raw.write_bytes(raw.read_bytes() + b"tampering")
    with pytest.raises(ValueError, match="hash do HTML bruto IBS/CBS diverge"):
        load_local_ibs_cbs_release(tmp_path, result.release_id)
