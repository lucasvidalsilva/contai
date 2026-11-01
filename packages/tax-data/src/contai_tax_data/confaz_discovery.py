"""Captura o sitemap publico do CONFAZ e lista candidatos sem interpretar atos."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
import zlib
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from contai_tax_data.source import RetrievedArtifact

CONFAZ_SITEMAP_URL = "https://www.confaz.fazenda.gov.br/sitemap.xml.gz"
CONFAZ_SITEMAP_CAPTURE_CONTRACT = "confaz-sitemap-gzip-v1"
CONFAZ_DISCOVERY_CONTRACT = "confaz-act-candidate-v1"
_SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_SITEMAP = f"{{{_SITEMAP_NS}}}"
_MAX_GZIP_BYTES = 10 * 1024 * 1024
_MAX_XML_BYTES = 50 * 1024 * 1024
_MAX_URLS = 100_000
_CANDIDATE_ROUTE = re.compile(r"^/legislacao/(convenios|ajustes|protocolos)/", re.IGNORECASE)
_SAFE_HEADERS = frozenset({"content-type", "content-length", "etag", "last-modified", "cache-control"})


class ConfazDiscoveryError(ValueError):
    """Resposta de sitemap fora do contrato de captura ou descoberta."""


class ConfazSourceClient(Protocol):
    def fetch(self, url: str) -> RetrievedArtifact: ...


@dataclass(frozen=True, slots=True)
class ConfazSitemapCaptureResult:
    artifact_sha256: str
    artifact_created: bool
    observation_created: bool
    byte_size: int
    captured_at: str
    raw_path: str


@dataclass(frozen=True, slots=True)
class ConfazActCandidate:
    source_url: str
    source_section: str
    source_lastmod: str | None


@dataclass(frozen=True, slots=True)
class ConfazDiscoveryResult:
    artifact_sha256: str
    snapshot_sha256: str
    candidate_count: int
    candidates_path: str
    candidates_created: bool
    manifest_created: bool
    source_url_count: int
    source_lastmod_count: int
    section_counts: dict[str, int]


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_once(path: Path, content: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(content)
    except FileExistsError:
        if path.read_bytes() != content:
            raise RuntimeError(f"colisao no caminho imutavel {path}") from None
        return False
    return True


def _write_pointer(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
            temporary_name = stream.name
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _decompress_sitemap(body: bytes) -> bytes:
    if not body or len(body) > _MAX_GZIP_BYTES or not body.startswith(b"\x1f\x8b"):
        raise ConfazDiscoveryError("sitemap CONFAZ vazio, maior que o limite ou sem assinatura GZip")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(body)) as stream:
            xml = stream.read(_MAX_XML_BYTES + 1)
    except (OSError, EOFError, zlib.error) as error:
        raise ConfazDiscoveryError(f"GZip do sitemap CONFAZ invalido: {error}") from None
    if len(xml) > _MAX_XML_BYTES:
        raise ConfazDiscoveryError("sitemap CONFAZ descompactado excede o limite de 50 MiB")
    return xml


def capture_confaz_sitemap_artifact(artifact: RetrievedArtifact, output_dir: Path) -> ConfazSitemapCaptureResult:
    if artifact.requested_url != CONFAZ_SITEMAP_URL or artifact.final_url != CONFAZ_SITEMAP_URL:
        raise ConfazDiscoveryError("URL solicitada/final diverge do sitemap oficial cadastrado")
    if artifact.status != 200:
        raise ConfazDiscoveryError(f"status HTTP inesperado para sitemap CONFAZ: {artifact.status}")
    content_type = artifact.headers.get("content-type", "").split(";", maxsplit=1)[0].strip().lower()
    if content_type != "application/octet-stream":
        raise ConfazDiscoveryError(f"Content-Type inesperado para sitemap CONFAZ: {content_type or '(ausente)'}")
    xml = _decompress_sitemap(artifact.body)
    parse_confaz_sitemap(xml)
    if artifact.captured_at.tzinfo is None:
        raise ConfazDiscoveryError("captured_at precisa de timezone")

    root = output_dir.resolve()
    digest = hashlib.sha256(artifact.body).hexdigest()
    captured_at = artifact.captured_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    raw_path = root / "artifacts" / "sha256" / digest[:2] / f"{digest}.xml.gz"
    relative_raw_path = raw_path.relative_to(root).as_posix()
    artifact_created = _write_once(raw_path, artifact.body)
    headers = {key.lower(): str(value) for key, value in artifact.headers.items() if key.lower() in _SAFE_HEADERS}
    observation = {
        "artifact_sha256": digest,
        "byte_size": len(artifact.body),
        "captured_at": captured_at,
        "contract_version": CONFAZ_SITEMAP_CAPTURE_CONTRACT,
        "decompressed_byte_size": len(xml),
        "final_url": artifact.final_url,
        "http_status": artifact.status,
        "raw_path": relative_raw_path,
        "requested_url": artifact.requested_url,
        "response_headers": headers,
        "source_authority": "CONFAZ",
        "status": "captured_raw_validated_gzip_xml",
    }
    observation_path = root / "artifacts" / "observations" / digest / f"{captured_at.replace(':', '-')}.json"
    observation_created = _write_once(observation_path, _json_bytes(observation))
    _write_pointer(root / "state" / "confaz-sitemap-latest-capture.json", _json_bytes(observation))
    return ConfazSitemapCaptureResult(
        artifact_sha256=digest,
        artifact_created=artifact_created,
        observation_created=observation_created,
        byte_size=len(artifact.body),
        captured_at=captured_at,
        raw_path=relative_raw_path,
    )


def capture_confaz_sitemap(output_dir: Path, *, client: ConfazSourceClient) -> ConfazSitemapCaptureResult:
    return capture_confaz_sitemap_artifact(client.fetch(CONFAZ_SITEMAP_URL), output_dir)


def parse_confaz_sitemap(xml: bytes) -> tuple[ConfazActCandidate, ...]:
    if not xml or len(xml) > _MAX_XML_BYTES:
        raise ConfazDiscoveryError("XML do sitemap CONFAZ vazio ou maior que o limite")
    if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
        raise ConfazDiscoveryError("DTD e entidades XML nÃ£o sÃ£o aceitos no sitemap")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as error:
        raise ConfazDiscoveryError(f"XML do sitemap CONFAZ malformado: {error}") from None
    if root.tag != f"{_SITEMAP}urlset":
        raise ConfazDiscoveryError("raiz XML inesperada; esperado urlset do protocolo sitemap")
    entries = root.findall(f"{_SITEMAP}url")
    if not 500 <= len(entries) <= _MAX_URLS:
        raise ConfazDiscoveryError(f"volume inesperado no sitemap CONFAZ: {len(entries)} URLs")

    candidates: list[ConfazActCandidate] = []
    seen_urls: set[str] = set()
    for entry in entries:
        if any(child.tag not in {f"{_SITEMAP}loc", f"{_SITEMAP}lastmod"} for child in entry):
            raise ConfazDiscoveryError("elemento XML fora do contrato de url/loc/lastmod")
        locations = entry.findall(f"{_SITEMAP}loc")
        lastmods = entry.findall(f"{_SITEMAP}lastmod")
        if len(locations) != 1 or len(lastmods) > 1:
            raise ConfazDiscoveryError("cada URL deve ter um loc e no maximo um lastmod")
        location = (locations[0].text or "").strip()
        parsed = urlsplit(location)
        if (
            not location
            or parsed.scheme != "https"
            or parsed.hostname != "www.confaz.fazenda.gov.br"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ConfazDiscoveryError("URL fora do dominio oficial CONFAZ no sitemap")
        if location in seen_urls:
            raise ConfazDiscoveryError("URL duplicada no sitemap CONFAZ")
        seen_urls.add(location)

        lastmod_text = (lastmods[0].text or "").strip() if lastmods else ""
        if lastmod_text:
            try:
                datetime.fromisoformat(lastmod_text.replace("Z", "+00:00"))
            except ValueError:
                try:
                    date.fromisoformat(lastmod_text)
                except ValueError:
                    raise ConfazDiscoveryError("lastmod fora do formato de data/hora ISO 8601") from None
        elif lastmods:
            raise ConfazDiscoveryError("lastmod vazio no sitemap CONFAZ")

        match = _CANDIDATE_ROUTE.match(parsed.path)
        if match:
            candidates.append(
                ConfazActCandidate(
                    source_url=location,
                    source_section=match.group(1).lower(),
                    source_lastmod=lastmod_text or None,
                )
            )
    if len(candidates) < 100:
        raise ConfazDiscoveryError(f"poucos candidatos nos roteiros CONFAZ esperados: {len(candidates)}")
    return tuple(sorted(candidates, key=lambda row: (row.source_section, row.source_url)))


def candidates_jsonl(candidates: tuple[ConfazActCandidate, ...]) -> bytes:
    lines = (
        json.dumps(asdict(candidate), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for candidate in candidates
    )
    return ("\n".join(lines) + "\n").encode("utf-8")


def write_confaz_discovery(raw_path: Path, capture_manifest_path: Path, output_dir: Path) -> dict[str, object]:
    try:
        capture = json.loads(capture_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConfazDiscoveryError(f"observacao de captura CONFAZ invalida: {error}") from None
    if not isinstance(capture, dict):
        raise ConfazDiscoveryError("observacao de captura CONFAZ precisa ser objeto JSON")
    raw = raw_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if (
        capture.get("artifact_sha256") != digest
        or capture.get("contract_version") != CONFAZ_SITEMAP_CAPTURE_CONTRACT
        or capture.get("requested_url") != CONFAZ_SITEMAP_URL
        or capture.get("final_url") != CONFAZ_SITEMAP_URL
        or capture.get("source_authority") != "CONFAZ"
        or capture.get("http_status") != 200
    ):
        raise ConfazDiscoveryError("sitemap bruto diverge da observacao oficial de captura")
    try:
        capture_root = capture_manifest_path.parents[3]
        raw_relative_path = raw_path.resolve().relative_to(capture_root.resolve()).as_posix()
    except (IndexError, ValueError):
        raise ConfazDiscoveryError("sitemap bruto esta fora da raiz da captura") from None
    if capture.get("raw_path") != raw_relative_path:
        raise ConfazDiscoveryError("caminho do sitemap diverge da observacao oficial")
    xml = _decompress_sitemap(raw)
    candidates = parse_confaz_sitemap(xml)
    source_root = ET.fromstring(xml)
    source_url_count = len(source_root.findall(f"{_SITEMAP}url"))
    source_lastmod_count = sum(
        entry.find(f"{_SITEMAP}lastmod") is not None for entry in source_root.findall(f"{_SITEMAP}url")
    )
    snapshot = candidates_jsonl(candidates)
    snapshot_hash = hashlib.sha256(snapshot).hexdigest()
    section_counts = {
        section: sum(candidate.source_section == section for candidate in candidates)
        for section in ("convenios", "ajustes", "protocolos")
    }
    output_root = output_dir.resolve()
    release_dir = output_root / "discoveries" / digest / CONFAZ_DISCOVERY_CONTRACT
    snapshot_path = release_dir / "confaz-act-candidates.jsonl"
    manifest_path = release_dir / "manifest.json"
    manifest = {
        "artifact_sha256": digest,
        "candidate_count": len(candidates),
        "contract_version": CONFAZ_DISCOVERY_CONTRACT,
        "interpretation_status": "not_performed",
        "lastmod_semantics": "source_metadata_only_not_legal_effective_date",
        "section_counts": section_counts,
        "snapshot_sha256": snapshot_hash,
        "source_authority": "CONFAZ",
        "source_url": CONFAZ_SITEMAP_URL,
        "source_url_count": source_url_count,
        "source_lastmod_count": source_lastmod_count,
    }
    snapshot_created = _write_once(snapshot_path, snapshot)
    manifest_created = _write_once(manifest_path, _json_bytes(manifest))
    result = {
        **manifest,
        "candidates_created": snapshot_created,
        "candidates_path": snapshot_path.relative_to(output_root).as_posix(),
        "manifest_created": manifest_created,
    }
    _write_pointer(output_root / "state" / "confaz-discovery-latest.json", _json_bytes(result))
    return result
