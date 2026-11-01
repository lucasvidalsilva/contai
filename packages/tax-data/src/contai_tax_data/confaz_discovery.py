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
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import urlsplit

from contai_tax_data.cest_capture import CEST_CAPTURE_CONTRACT, CEST_SOURCE_URL
from contai_tax_data.source import RetrievedArtifact

CONFAZ_SITEMAP_URL = "https://www.confaz.fazenda.gov.br/sitemap.xml.gz"
CONFAZ_SITEMAP_CAPTURE_CONTRACT = "confaz-sitemap-gzip-v1"
CONFAZ_DISCOVERY_CONTRACT = "confaz-act-candidate-v1"
CONFAZ_ACT_CAPTURE_CONTRACT = "confaz-html-act-raw-v1"
_SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_SITEMAP = f"{{{_SITEMAP_NS}}}"
_MAX_GZIP_BYTES = 10 * 1024 * 1024
_MAX_XML_BYTES = 50 * 1024 * 1024
_MAX_ACT_HTML_BYTES = 25 * 1024 * 1024
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


@dataclass(frozen=True, slots=True)
class ConfazActCaptureResult:
    source_url: str
    source_lastmod: str | None
    artifact_sha256: str
    artifact_created: bool
    observation_created: bool
    byte_size: int
    captured_at: str
    raw_path: str


@dataclass(frozen=True, slots=True)
class ConfazAmendmentReference:
    source_artifact_sha256: str
    source_url: str
    reference_index: int
    relation_label: str
    anchor_text: str
    href: str
    catalog_url: str | None
    catalog_lastmod: str | None
    catalog_status: Literal["matched", "relative_unresolved", "not_in_catalog", "non_confaz_url"]


class ConfazActSourceClient(Protocol):
    def fetch(self, url: str) -> RetrievedArtifact: ...


class _AmendmentLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[tuple[str, tuple[tuple[str, str], ...]]] = []
        self._target_paragraph = False
        self._paragraph_text: list[str] = []
        self._links: list[tuple[str, str]] = []
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "p":
            classes = next((value for name, value in attrs if name.lower() == "class"), "") or ""
            if "A2DataPublicacao" in classes.split():
                self._target_paragraph = True
                self._paragraph_text = []
                self._links = []
        elif self._target_paragraph and tag.lower() == "a":
            self._anchor_href = next((value for name, value in attrs if name.lower() == "href"), "") or ""
            self._anchor_text = []

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if self._target_paragraph and lowered == "a" and self._anchor_href is not None:
            self._links.append((self._anchor_href.strip(), " ".join("".join(self._anchor_text).split())))
            self._anchor_href = None
            self._anchor_text = []
        elif self._target_paragraph and lowered == "p":
            paragraph_text = " ".join("".join(self._paragraph_text).split())
            if re.match(r"^Alterado\s+pelo\b", paragraph_text, re.IGNORECASE):
                self.paragraphs.append((paragraph_text, tuple(self._links)))
            self._target_paragraph = False
            self._paragraph_text = []
            self._links = []

    def handle_data(self, data: str) -> None:
        if self._target_paragraph:
            self._paragraph_text.append(data)
            if self._anchor_href is not None:
                self._anchor_text.append(data)


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


def _load_confaz_candidate(catalog_root: Path, source_url: str) -> tuple[ConfazActCandidate, str, str]:
    root = catalog_root.resolve()
    try:
        capture = json.loads((root / "state" / "confaz-sitemap-latest-capture.json").read_text(encoding="utf-8"))
        discovery = json.loads((root / "state" / "confaz-discovery-latest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConfazDiscoveryError(f"catÃ¡logo CONFAZ versionado ausente ou invÃ¡lido: {error}") from None
    if not isinstance(capture, dict) or not isinstance(discovery, dict):
        raise ConfazDiscoveryError("ponteiros do catÃ¡logo CONFAZ precisam ser objetos JSON")
    if (
        capture.get("contract_version") != CONFAZ_SITEMAP_CAPTURE_CONTRACT
        or capture.get("requested_url") != CONFAZ_SITEMAP_URL
        or capture.get("final_url") != CONFAZ_SITEMAP_URL
        or capture.get("http_status") != 200
        or capture.get("source_authority") != "CONFAZ"
        or discovery.get("contract_version") != CONFAZ_DISCOVERY_CONTRACT
        or discovery.get("artifact_sha256") != capture.get("artifact_sha256")
    ):
        raise ConfazDiscoveryError("ponteiros do catÃ¡logo CONFAZ nÃ£o correspondem aos contratos oficiais")
    try:
        raw_path = (root / str(capture.get("raw_path", ""))).resolve()
        raw_path.relative_to(root)
    except ValueError:
        raise ConfazDiscoveryError("caminho do bruto CONFAZ estÃ¡ fora do catÃ¡logo") from None
    raw = raw_path.read_bytes()
    sitemap_hash = hashlib.sha256(raw).hexdigest()
    if sitemap_hash != capture.get("artifact_sha256"):
        raise ConfazDiscoveryError("bruto do sitemap CONFAZ diverge do hash do catÃ¡logo")
    observation_at = str(capture.get("captured_at", "")).replace(":", "-")
    observation_path = root / "artifacts" / "observations" / sitemap_hash / f"{observation_at}.json"
    try:
        archived_observation = json.loads(observation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConfazDiscoveryError(f"observaÃ§Ã£o do sitemap nÃ£o estÃ¡ arquivada: {error}") from None
    if archived_observation != capture:
        raise ConfazDiscoveryError("ponteiro atual do sitemap diverge da observaÃ§Ã£o imutÃ¡vel")
    candidates = parse_confaz_sitemap(_decompress_sitemap(raw))
    relative_snapshot_path = discovery.get("candidates_path")
    if not isinstance(relative_snapshot_path, str):
        raise ConfazDiscoveryError("ponteiro de descoberta sem caminho de snapshot")
    try:
        snapshot_path = (root / relative_snapshot_path).resolve()
        snapshot_path.relative_to(root)
    except ValueError:
        raise ConfazDiscoveryError("caminho do snapshot CONFAZ estÃ¡ fora do catÃ¡logo") from None
    snapshot = snapshot_path.read_bytes()
    snapshot_hash = hashlib.sha256(snapshot).hexdigest()
    if (
        snapshot_hash != discovery.get("snapshot_sha256")
        or snapshot != candidates_jsonl(candidates)
        or discovery.get("candidate_count") != len(candidates)
    ):
        raise ConfazDiscoveryError("snapshot de candidatos CONFAZ nÃ£o reprocessa a partir do sitemap")
    try:
        manifest = json.loads(snapshot_path.with_name("manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConfazDiscoveryError(f"manifesto do catÃ¡logo CONFAZ invÃ¡lido: {error}") from None
    if not isinstance(manifest, dict):
        raise ConfazDiscoveryError("manifesto do catÃ¡logo CONFAZ precisa ser objeto JSON")
    if manifest.get("snapshot_sha256") != snapshot_hash or manifest.get("artifact_sha256") != sitemap_hash:
        raise ConfazDiscoveryError("manifesto do catÃ¡logo CONFAZ diverge dos artefatos")
    candidate = next((row for row in candidates if row.source_url == source_url), None)
    if candidate is None:
        raise ConfazDiscoveryError("URL nÃ£o consta no catÃ¡logo oficial versionado do CONFAZ")
    return candidate, sitemap_hash, snapshot_hash


def extract_confaz_amendment_references(
    artifact_path: Path, observation_path: Path, catalog_root: Path, output_root: Path
) -> dict[str, object]:
    """Extrai links explicitamente marcados como alteradores no HTML CEST, sem resolver vigência."""
    try:
        observation = json.loads(observation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConfazDiscoveryError(f"observação CEST ausente ou inválida: {error}") from None
    if not isinstance(observation, dict):
        raise ConfazDiscoveryError("observação CEST precisa ser objeto JSON")
    raw = artifact_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if (
        observation.get("contract_version") != CEST_CAPTURE_CONTRACT
        or observation.get("requested_url") != CEST_SOURCE_URL
        or observation.get("final_url") != CEST_SOURCE_URL
        or observation.get("source_authority") != "CONFAZ"
        or observation.get("http_status") != 200
        or observation.get("artifact_sha256") != digest
        or observation.get("byte_size") != len(raw)
    ):
        raise ConfazDiscoveryError("HTML CEST diverge da observação oficial de captura")
    try:
        capture_root = observation_path.parents[3]
        relative = artifact_path.resolve().relative_to(capture_root.resolve()).as_posix()
    except (IndexError, ValueError):
        raise ConfazDiscoveryError("HTML CEST está fora da raiz de captura") from None
    if observation.get("raw_path") != relative:
        raise ConfazDiscoveryError("caminho do HTML CEST diverge da observação")
    try:
        html = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise ConfazDiscoveryError("HTML CEST não é UTF-8 válido") from None

    parser = _AmendmentLinkParser()
    parser.feed(html)
    if not parser.paragraphs:
        raise ConfazDiscoveryError("HTML CEST não contém referências 'Alterado pelo' reconhecíveis")

    # Reprocessa uma vez a fonte oficial arquivada e valida os hashes/snapshot antes de
    # usar a lista de URLs como índice de correspondência.
    root = catalog_root.resolve()
    try:
        capture = json.loads((root / "state" / "confaz-sitemap-latest-capture.json").read_text(encoding="utf-8"))
        discovery = json.loads((root / "state" / "confaz-discovery-latest.json").read_text(encoding="utf-8"))
        raw_catalog_path = (root / str(capture["raw_path"])).resolve()
        raw_catalog_path.relative_to(root)
        raw_catalog = raw_catalog_path.read_bytes()
        catalog_digest = hashlib.sha256(raw_catalog).hexdigest()
        if catalog_digest != capture.get("artifact_sha256"):
            raise ConfazDiscoveryError("bruto do sitemap diverge do hash do catálogo")
        observation_at = str(capture.get("captured_at", "")).replace(":", "-")
        catalog_observation = json.loads(
            (root / "artifacts" / "observations" / catalog_digest / f"{observation_at}.json").read_text(
                encoding="utf-8"
            )
        )
        sitemap_candidates = parse_confaz_sitemap(_decompress_sitemap(raw_catalog))
        snapshot_path = (root / str(discovery["candidates_path"])).resolve()
        snapshot_path.relative_to(root)
        snapshot = snapshot_path.read_bytes()
        snapshot_digest = hashlib.sha256(snapshot).hexdigest()
        manifest = json.loads(snapshot_path.with_name("manifest.json").read_text(encoding="utf-8"))
    except (OSError, KeyError, TypeError, json.JSONDecodeError, ValueError) as error:
        if isinstance(error, ConfazDiscoveryError):
            raise
        raise ConfazDiscoveryError(f"catálogo CONFAZ ausente ou inválido: {error}") from None
    if (
        not isinstance(capture, dict)
        or not isinstance(discovery, dict)
        or not isinstance(manifest, dict)
        or capture.get("contract_version") != CONFAZ_SITEMAP_CAPTURE_CONTRACT
        or capture.get("requested_url") != CONFAZ_SITEMAP_URL
        or capture.get("final_url") != CONFAZ_SITEMAP_URL
        or capture.get("http_status") != 200
        or capture.get("source_authority") != "CONFAZ"
        or catalog_observation != capture
        or discovery.get("contract_version") != CONFAZ_DISCOVERY_CONTRACT
        or discovery.get("artifact_sha256") != catalog_digest
        or snapshot != candidates_jsonl(sitemap_candidates)
        or discovery.get("snapshot_sha256") != snapshot_digest
        or discovery.get("candidate_count") != len(sitemap_candidates)
        or manifest.get("snapshot_sha256") != snapshot_digest
        or manifest.get("artifact_sha256") != catalog_digest
    ):
        raise ConfazDiscoveryError("snapshot do catálogo CONFAZ não reprocessa a partir do bruto oficial")
    by_url = {candidate.source_url: candidate for candidate in sitemap_candidates}
    references: list[ConfazAmendmentReference] = []
    for paragraph, links in parser.paragraphs:
        for href, anchor in links:
            parsed = urlsplit(href)
            if not parsed.scheme and not parsed.netloc:
                status: Literal["matched", "relative_unresolved", "not_in_catalog", "non_confaz_url"] = (
                    "relative_unresolved"
                )
                candidate = None
            elif parsed.scheme == "https" and parsed.netloc == "www.confaz.fazenda.gov.br":
                candidate = by_url.get(href)
                status = "matched" if candidate else "not_in_catalog"
            else:
                candidate = None
                status = "non_confaz_url"
            references.append(
                ConfazAmendmentReference(
                    source_artifact_sha256=digest,
                    source_url=CEST_SOURCE_URL,
                    reference_index=len(references) + 1,
                    relation_label=paragraph,
                    anchor_text=anchor,
                    href=href,
                    catalog_url=candidate.source_url if candidate else None,
                    catalog_lastmod=candidate.source_lastmod if candidate else None,
                    catalog_status=status,
                )
            )
    if not references:
        raise ConfazDiscoveryError("parágrafos de alteração não contêm links para atos")
    jsonl = (
        "\n".join(
            json.dumps(asdict(row), ensure_ascii=False, sort_keys=True, separators=(",", ":")) for row in references
        )
        + "\n"
    ).encode("utf-8")
    snapshot_hash = hashlib.sha256(jsonl).hexdigest()
    release = output_root.resolve() / "references" / digest / "confaz-amendment-reference-v1"
    snapshot_path = release / "confaz-amendment-references.jsonl"
    manifest = {
        "artifact_sha256": digest,
        "catalog_snapshot_sha256": snapshot_digest,
        "catalog_sitemap_sha256": catalog_digest,
        "contract_version": "confaz-amendment-reference-v1",
        "interpretation_status": "not_performed",
        "reference_count": len(references),
        "status_counts": {
            status: sum(row.catalog_status == status for row in references)
            for status in ("matched", "relative_unresolved", "not_in_catalog", "non_confaz_url")
        },
        "snapshot_sha256": snapshot_hash,
        "source_url": CEST_SOURCE_URL,
    }
    snapshot_created = _write_once(snapshot_path, jsonl)
    manifest_created = _write_once(release / "manifest.json", _json_bytes(manifest))
    result = {
        **manifest,
        "snapshot_path": snapshot_path.relative_to(output_root.resolve()).as_posix(),
        "snapshot_created": snapshot_created,
        "manifest_created": manifest_created,
    }
    _write_pointer(output_root.resolve() / "state" / "confaz-amendment-references-latest.json", _json_bytes(result))
    return result


def capture_confaz_act_artifact(
    artifact: RetrievedArtifact,
    candidate: ConfazActCandidate,
    output_dir: Path,
    *,
    sitemap_sha256: str,
    discovery_sha256: str,
) -> ConfazActCaptureResult:
    if artifact.requested_url != candidate.source_url or artifact.final_url != candidate.source_url:
        raise ConfazDiscoveryError("URL solicitada/final diverge do candidato oficial selecionado")
    parsed_url = urlsplit(candidate.source_url)
    if parsed_url.scheme != "https" or parsed_url.netloc != "www.confaz.fazenda.gov.br":
        raise ConfazDiscoveryError("candidato nÃ£o pertence ao host oficial CONFAZ")
    if artifact.status != 200:
        raise ConfazDiscoveryError(f"status HTTP inesperado para ato CONFAZ: {artifact.status}")
    content_type = artifact.headers.get("content-type", "").lower().replace(" ", "")
    if "text/html" not in content_type or "charset=utf-8" not in content_type:
        raise ConfazDiscoveryError("ato selecionado deve responder text/html UTF-8")
    if not artifact.body or len(artifact.body) > _MAX_ACT_HTML_BYTES:
        raise ConfazDiscoveryError("HTML do ato CONFAZ vazio ou maior que o limite de 25 MiB")
    try:
        text = artifact.body.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise ConfazDiscoveryError("HTML do ato CONFAZ nÃ£o Ã© UTF-8 vÃ¡lido") from None
    if "<html" not in text[:4096].lower():
        raise ConfazDiscoveryError("resposta HTML do ato CONFAZ sem raiz HTML reconhecÃ­vel")
    if artifact.captured_at.tzinfo is None:
        raise ConfazDiscoveryError("captured_at precisa de timezone")

    root = output_dir.resolve()
    digest = hashlib.sha256(artifact.body).hexdigest()
    captured_at = artifact.captured_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    url_key = hashlib.sha256(candidate.source_url.encode("utf-8")).hexdigest()
    act_root = root / "acts" / url_key
    raw_path = act_root / "artifacts" / "sha256" / digest[:2] / f"{digest}.html"
    relative_raw_path = raw_path.relative_to(root).as_posix()
    artifact_created = _write_once(raw_path, artifact.body)
    headers = {key.lower(): str(value) for key, value in artifact.headers.items() if key.lower() in _SAFE_HEADERS}
    observation = {
        "artifact_sha256": digest,
        "byte_size": len(artifact.body),
        "captured_at": captured_at,
        "contract_version": CONFAZ_ACT_CAPTURE_CONTRACT,
        "final_url": artifact.final_url,
        "http_status": artifact.status,
        "raw_path": relative_raw_path,
        "requested_url": artifact.requested_url,
        "response_headers": headers,
        "sitemap_sha256": sitemap_sha256,
        "discovery_sha256": discovery_sha256,
        "source_authority": "CONFAZ",
        "source_lastmod": candidate.source_lastmod,
        "source_section": candidate.source_section,
        "status": "captured_raw_uninterpreted",
    }
    observation_path = act_root / "artifacts" / "observations" / digest / f"{captured_at.replace(':', '-')}.json"
    observation_created = _write_once(observation_path, _json_bytes(observation))
    _write_pointer(act_root / "state" / "latest-capture.json", _json_bytes(observation))
    return ConfazActCaptureResult(
        source_url=candidate.source_url,
        source_lastmod=candidate.source_lastmod,
        artifact_sha256=digest,
        artifact_created=artifact_created,
        observation_created=observation_created,
        byte_size=len(artifact.body),
        captured_at=captured_at,
        raw_path=relative_raw_path,
    )


def capture_confaz_act(
    source_url: str, catalog_root: Path, output_root: Path, *, client: ConfazActSourceClient
) -> ConfazActCaptureResult:
    candidate, sitemap_hash, discovery_hash = _load_confaz_candidate(catalog_root, source_url)
    artifact = client.fetch(candidate.source_url)
    return capture_confaz_act_artifact(
        artifact,
        candidate,
        output_root,
        sitemap_sha256=sitemap_hash,
        discovery_sha256=discovery_hash,
    )


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
            or parsed.netloc != "www.confaz.fazenda.gov.br"
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
