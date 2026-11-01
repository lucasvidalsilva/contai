from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from contai_tax_data.cest_capture import CEST_SOURCE_URL, capture_cest_artifact
from contai_tax_data.confaz_discovery import (
    CONFAZ_SITEMAP_URL,
    ConfazActCandidate,
    ConfazDiscoveryError,
    capture_confaz_act,
    capture_confaz_act_artifact,
    capture_confaz_sitemap_artifact,
    extract_confaz_amendment_references,
    parse_confaz_sitemap,
    write_confaz_discovery,
)
from contai_tax_data.source import RetrievedArtifact

NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def _sitemap(*, bad_url: str | None = None, duplicate: bool = False, bad_lastmod: bool = False) -> bytes:
    entries = [
        f"<url><loc>https://www.confaz.fazenda.gov.br/pagina/{index}</loc><lastmod>2026-10-31</lastmod></url>"
        for index in range(400)
    ]
    entries += [
        f"<url><loc>{bad_url or f'https://www.confaz.fazenda.gov.br/legislacao/{section}/2026/ato-{index}'}</loc>"
        f"<lastmod>{'yesterday' if bad_lastmod else '2026-11-01T12:00:00-03:00'}</lastmod></url>"
        for section, count in (("convenios", 100), ("ajustes", 20), ("protocolos", 30))
        for index in range(count)
    ]
    if duplicate:
        entries.append(entries[-1])
    return f'<urlset xmlns="{NS}">{"".join(entries)}</urlset>'.encode()


def _artifact(
    body: bytes,
    *,
    url: str = CONFAZ_SITEMAP_URL,
    final_url: str | None = None,
    status: int = 200,
    content_type: str = "application/octet-stream",
) -> RetrievedArtifact:
    return RetrievedArtifact(
        requested_url=url,
        final_url=final_url or url,
        status=status,
        headers={"content-type": content_type, "set-cookie": "must-not-be-recorded"},
        body=body,
        captured_at=datetime(2026, 11, 1, 12, tzinfo=UTC),
    )


def test_sitemap_parser_lists_only_official_act_routes_and_keeps_lastmod_literal() -> None:
    candidates = parse_confaz_sitemap(_sitemap())

    assert len(candidates) == 150
    assert {candidate.source_section for candidate in candidates} == {"convenios", "ajustes", "protocolos"}
    assert candidates[0].source_lastmod == "2026-11-01T12:00:00-03:00"
    assert all(
        candidate.source_url.startswith("https://www.confaz.fazenda.gov.br/legislacao/") for candidate in candidates
    )


@pytest.mark.parametrize(
    ("artifact", "message"),
    [
        (_artifact(b"not gzip"), "assinatura GZip"),
        (_artifact(b"\x1f\x8bbroken"), "GZip do sitemap"),
        (_artifact(gzip.compress(_sitemap()), url="https://example.com/sitemap.xml.gz"), "URL solicitada/final"),
        (
            _artifact(gzip.compress(_sitemap()), final_url="https://www.confaz.fazenda.gov.br/other.gz"),
            "URL solicitada/final",
        ),
        (_artifact(gzip.compress(_sitemap()), status=206), "status HTTP"),
        (_artifact(gzip.compress(_sitemap()), content_type="application/gzip"), "Content-Type"),
    ],
)
def test_capture_rejects_unexpected_official_source_response(
    tmp_path: Path, artifact: RetrievedArtifact, message: str
) -> None:
    with pytest.raises(ConfazDiscoveryError, match=message):
        capture_confaz_sitemap_artifact(artifact, tmp_path)


@pytest.mark.parametrize(
    ("xml", "message"),
    [
        (b"<not-xml>", "malformado"),
        (b"<!DOCTYPE urlset [<!ENTITY x 'y'>]><urlset />", "DTD"),
        (_sitemap(bad_url="https://elsewhere.example/legislacao/convenios/2026/1"), "dominio oficial"),
        (_sitemap(bad_url="https://www.confaz.fazenda.gov.br:444/legislacao/convenios/2026/1"), "dominio oficial"),
        (_sitemap(duplicate=True), "duplicada"),
        (_sitemap(bad_lastmod=True), "ISO 8601"),
    ],
)
def test_parser_quarantines_invalid_sitemap_content(xml: bytes, message: str) -> None:
    with pytest.raises(ConfazDiscoveryError, match=message):
        parse_confaz_sitemap(xml)


def test_capture_and_discovery_are_reprocessable_and_idempotent(tmp_path: Path) -> None:
    raw = gzip.compress(_sitemap(), mtime=0)
    capture_root = tmp_path / "capture"
    first_capture = capture_confaz_sitemap_artifact(_artifact(raw), capture_root)
    second_capture = capture_confaz_sitemap_artifact(_artifact(raw), capture_root)
    observation = (
        capture_root
        / "artifacts"
        / "observations"
        / first_capture.artifact_sha256
        / f"{first_capture.captured_at.replace(':', '-')}.json"
    )
    raw_path = capture_root / first_capture.raw_path
    first_discovery = write_confaz_discovery(raw_path, observation, tmp_path / "discovery")
    second_discovery = write_confaz_discovery(raw_path, observation, tmp_path / "discovery")

    assert first_capture.artifact_created and first_capture.observation_created
    assert not second_capture.artifact_created and not second_capture.observation_created
    assert first_discovery["candidate_count"] == 150
    assert first_discovery["source_url_count"] == 550
    assert first_discovery["source_lastmod_count"] == 550
    assert first_discovery["section_counts"] == {"ajustes": 20, "convenios": 100, "protocolos": 30}
    assert first_discovery["snapshot_sha256"] == second_discovery["snapshot_sha256"]
    assert first_discovery["candidates_created"] and first_discovery["manifest_created"]
    assert not second_discovery["candidates_created"] and not second_discovery["manifest_created"]
    assert first_discovery["interpretation_status"] == "not_performed"
    assert first_discovery["lastmod_semantics"] == "source_metadata_only_not_legal_effective_date"
    snapshot = (tmp_path / "discovery" / first_discovery["candidates_path"]).read_bytes()
    assert hashlib.sha256(snapshot).hexdigest() == first_discovery["snapshot_sha256"]
    assert b"must-not-be-recorded" not in (capture_root / "state/confaz-sitemap-latest-capture.json").read_bytes()


def test_act_capture_requires_catalog_membership_and_preserves_provenance(tmp_path: Path) -> None:
    raw = gzip.compress(_sitemap(), mtime=0)
    catalog_root = tmp_path / "catalog"
    captured = capture_confaz_sitemap_artifact(_artifact(raw), catalog_root)
    observation = (
        catalog_root
        / "artifacts"
        / "observations"
        / captured.artifact_sha256
        / f"{captured.captured_at.replace(':', '-')}.json"
    )
    write_confaz_discovery(catalog_root / captured.raw_path, observation, catalog_root)
    selected_url = "https://www.confaz.fazenda.gov.br/legislacao/convenios/2026/ato-0"
    page = b"<!doctype html><html><body>CONVENIO TESTE</body></html>"

    class Client:
        def __init__(self) -> None:
            self.requested: list[str] = []

        def fetch(self, url: str) -> RetrievedArtifact:
            self.requested.append(url)
            return _artifact(page, url=url, content_type="text/html; charset=utf-8")

    client = Client()
    first = capture_confaz_act(selected_url, catalog_root, tmp_path / "acts", client=client)
    second = capture_confaz_act(selected_url, catalog_root, tmp_path / "acts", client=client)
    raw_path = tmp_path / "acts" / first.raw_path
    url_key = hashlib.sha256(selected_url.encode("utf-8")).hexdigest()
    observation_dir = tmp_path / "acts" / "acts" / url_key / "artifacts" / "observations" / first.artifact_sha256
    observation_path = next(observation_dir.glob("*.json"))
    captured_manifest = json.loads(observation_path.read_text(encoding="utf-8"))

    assert first.artifact_sha256 == second.artifact_sha256 == hashlib.sha256(page).hexdigest()
    assert first.artifact_created and first.observation_created
    assert not second.artifact_created and not second.observation_created
    assert client.requested == [selected_url, selected_url]
    assert raw_path.read_bytes() == page
    assert captured_manifest["requested_url"] == selected_url
    assert captured_manifest["contract_version"] == "confaz-html-act-raw-v1"
    assert captured_manifest["status"] == "captured_raw_uninterpreted"
    assert captured_manifest["source_lastmod"] == "2026-11-01T12:00:00-03:00"

    with pytest.raises(ConfazDiscoveryError, match="nÃ£o consta no catÃ¡logo"):
        capture_confaz_act(
            "https://www.confaz.fazenda.gov.br/legislacao/convenios/2026/nao-listado",
            catalog_root,
            tmp_path / "acts",
            client=client,
        )
    assert len(client.requested) == 2


@pytest.mark.parametrize(
    ("artifact", "message"),
    [
        (_artifact(b"<html>x</html>", final_url="https://www.confaz.fazenda.gov.br/outro"), "URL solicitada/final"),
        (_artifact(b"<html>x</html>", status=404), "status HTTP"),
        (_artifact(b"<html>x</html>", content_type="application/pdf"), "text/html UTF-8"),
        (_artifact(b"<html>\xff</html>"), "UTF-8"),
    ],
)
def test_act_capture_rejects_unexpected_page_response(
    tmp_path: Path, artifact: RetrievedArtifact, message: str
) -> None:
    candidate = ConfazActCandidate(
        source_url=CONFAZ_SITEMAP_URL.replace("sitemap.xml.gz", "legislacao/convenios/2026/teste"),
        source_section="convenios",
        source_lastmod=None,
    )
    mismatched = RetrievedArtifact(
        requested_url=candidate.source_url,
        final_url=artifact.final_url if artifact.final_url != CONFAZ_SITEMAP_URL else candidate.source_url,
        status=artifact.status,
        headers=artifact.headers,
        body=artifact.body,
        captured_at=artifact.captured_at,
    )
    with pytest.raises(ConfazDiscoveryError, match=message):
        capture_confaz_act_artifact(
            mismatched,
            candidate,
            tmp_path,
            sitemap_sha256="0" * 64,
            discovery_sha256="1" * 64,
        )


def test_discovery_rejects_manifest_for_different_source(tmp_path: Path) -> None:
    raw = gzip.compress(_sitemap(), mtime=0)
    result = capture_confaz_sitemap_artifact(_artifact(raw), tmp_path / "capture")
    observation = tmp_path / "capture" / "artifacts/observations" / result.artifact_sha256 / "wrong.json"
    observation.parent.mkdir(parents=True, exist_ok=True)
    observation.write_text(json.dumps({"artifact_sha256": "wrong"}), encoding="utf-8")

    with pytest.raises(ConfazDiscoveryError, match="diverge"):
        write_confaz_discovery(tmp_path / "capture" / result.raw_path, observation, tmp_path / "discovery")


def test_amendment_references_match_only_catalog_urls_and_leave_relative_unresolved(tmp_path: Path) -> None:
    catalog_root = tmp_path / "catalog"
    raw = gzip.compress(_sitemap(), mtime=0)
    captured = capture_confaz_sitemap_artifact(_artifact(raw), catalog_root)
    observation = (
        catalog_root
        / "artifacts"
        / "observations"
        / captured.artifact_sha256
        / f"{captured.captured_at.replace(':', '-')}.json"
    )
    write_confaz_discovery(catalog_root / captured.raw_path, observation, catalog_root)

    amendment_url = "https://www.confaz.fazenda.gov.br/legislacao/convenios/2026/ato-0"
    html = (
        '<html><body><p class="A2DataPublicacao">Alterado pelo Conv. ICMS '
        f'<a href="{amendment_url}">107/26</a> e <a href="resolveuid/abc123">178/24</a></p>'
        "</body></html>"
    ).encode()
    capture_root = tmp_path / "cest"
    from contai_tax_data.source import RetrievedArtifact

    cest_capture = capture_cest_artifact(
        RetrievedArtifact(
            requested_url=CEST_SOURCE_URL,
            final_url=CEST_SOURCE_URL,
            status=200,
            headers={"content-type": "text/html"},
            body=html,
            captured_at=datetime(2026, 11, 1, 12, tzinfo=UTC),
        ),
        capture_root,
    )
    cest_observation = (
        capture_root
        / "artifacts"
        / "observations"
        / cest_capture.artifact_sha256
        / f"{cest_capture.captured_at.replace(':', '-')}.json"
    )

    first = extract_confaz_amendment_references(
        capture_root / cest_capture.raw_path, cest_observation, catalog_root, tmp_path / "references"
    )
    second = extract_confaz_amendment_references(
        capture_root / cest_capture.raw_path, cest_observation, catalog_root, tmp_path / "references"
    )
    rows = [
        json.loads(line)
        for line in (tmp_path / "references" / first["snapshot_path"]).read_text(encoding="utf-8").splitlines()
    ]

    assert first["reference_count"] == 2
    assert first["status_counts"] == {"matched": 1, "relative_unresolved": 1, "not_in_catalog": 0, "non_confaz_url": 0}
    assert first["snapshot_sha256"] == second["snapshot_sha256"]
    assert first["snapshot_created"] and first["manifest_created"]
    assert not second["snapshot_created"] and not second["manifest_created"]
    assert rows[0]["catalog_status"] == "matched"
    assert rows[0]["catalog_url"] == amendment_url
    assert rows[1]["catalog_status"] == "relative_unresolved"
    assert rows[1]["catalog_url"] is None
    assert rows[1]["href"] == "resolveuid/abc123"
    assert first["interpretation_status"] == "not_performed"


def test_amendment_reference_extraction_rejects_unarchived_or_unrecognized_source(tmp_path: Path) -> None:
    artifact = tmp_path / "page.html"
    artifact.write_bytes(b"<html><body>no amendment references</body></html>")
    observation = tmp_path / "observation.json"
    observation.write_text("{}", encoding="utf-8")

    with pytest.raises(ConfazDiscoveryError, match="diverge"):
        extract_confaz_amendment_references(artifact, observation, tmp_path / "catalog", tmp_path / "out")
