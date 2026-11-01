from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from contai_tax_data.confaz_discovery import (
    CONFAZ_SITEMAP_URL,
    ConfazDiscoveryError,
    capture_confaz_sitemap_artifact,
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


def test_discovery_rejects_manifest_for_different_source(tmp_path: Path) -> None:
    raw = gzip.compress(_sitemap(), mtime=0)
    result = capture_confaz_sitemap_artifact(_artifact(raw), tmp_path / "capture")
    observation = tmp_path / "capture" / "artifacts/observations" / result.artifact_sha256 / "wrong.json"
    observation.parent.mkdir(parents=True, exist_ok=True)
    observation.write_text(json.dumps({"artifact_sha256": "wrong"}), encoding="utf-8")

    with pytest.raises(ConfazDiscoveryError, match="diverge"):
        write_confaz_discovery(tmp_path / "capture" / result.raw_path, observation, tmp_path / "discovery")
