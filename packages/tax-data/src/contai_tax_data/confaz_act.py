"""Extração estrutural literal de atos HTML arquivados do CONFAZ."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from contai_tax_data.confaz_discovery import CONFAZ_ACT_CAPTURE_CONTRACT, _load_confaz_candidate

CONFAZ_ACT_BLOCK_CONTRACT = "confaz-act-block-v2"
BlockTag = Literal["p", "td", "th"]


@dataclass(frozen=True, slots=True)
class ConfazActBlock:
    source_block_index: int
    source_class: str | None
    source_tag: BlockTag
    text: str


@dataclass(frozen=True, slots=True)
class ConfazActDocument:
    source_title: str
    description_text: str | None
    act_title: str
    publication_text: str
    summary_text: str
    blocks: tuple[ConfazActBlock, ...]


@dataclass(slots=True)
class _BlockContext:
    tag: BlockTag
    index: int
    source_class: str | None
    parts: list[str]
    contains_nested_block: bool = False
    same_tag_nesting: int = 0


@dataclass(slots=True)
class _MetaContext:
    tag: str
    name: str
    parts: list[str]


class _ConfazActParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[ConfazActBlock] = []
        self.metadata: dict[str, list[str]] = {"source_title": [], "description": []}
        self._block_index = -1
        self._block_contexts: list[_BlockContext] = []
        self._meta_contexts: list[_MetaContext] = []
        self._in_content = False
        self._content_div_depth = 0

    def _finish_block(self, context: _BlockContext) -> None:
        text = " ".join("".join(context.parts).split())
        if text and not context.contains_nested_block:
            self.blocks.append(
                ConfazActBlock(
                    source_block_index=context.index,
                    source_class=context.source_class,
                    source_tag=context.tag,
                    text=text,
                )
            )

    def _finish_meta(self, context: _MetaContext) -> None:
        value = " ".join("".join(context.parts).split())
        if value:
            self.metadata[context.name].append(value)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        attributes = {name.lower(): value or "" for name, value in attrs}
        classes = set(attributes.get("class", "").split())

        if lowered == "h1" and "documentFirstHeading" in classes:
            self._meta_contexts.append(_MetaContext(tag=lowered, name="source_title", parts=[]))
        elif lowered == "div" and {"documentDescription", "description"}.issubset(classes):
            self._meta_contexts.append(_MetaContext(tag=lowered, name="description", parts=[]))

        if lowered == "div" and attributes.get("id") == "parent-fieldname-text":
            self._in_content = True
            self._content_div_depth = 1
            return
        if self._in_content:
            if lowered == "div":
                self._content_div_depth += 1
            if lowered in {"p", "td", "th"}:
                if self._block_contexts:
                    if self._block_contexts[-1].tag == lowered:
                        # O HTML oficial contém parágrafos malformados com <p></p>
                        # interno. Preserve o texto no parágrafo original em vez de
                        # descartá-lo como um bloco pai com filhos.
                        self._block_contexts[-1].same_tag_nesting += 1
                        return
                    self._block_contexts[-1].contains_nested_block = True
                self._block_index += 1
                self._block_contexts.append(
                    _BlockContext(
                        tag=lowered,  # type: ignore[arg-type]
                        index=self._block_index,
                        source_class=attributes.get("class") or None,
                        parts=[],
                    )
                )
            elif self._block_contexts and lowered in {"br", "hr"}:
                self._block_contexts[-1].parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        matching_meta = next(
            (
                index
                for index in range(len(self._meta_contexts) - 1, -1, -1)
                if self._meta_contexts[index].tag == lowered
            ),
            None,
        )
        if matching_meta is not None:
            while len(self._meta_contexts) > matching_meta:
                self._finish_meta(self._meta_contexts.pop())

        if self._in_content:
            if (
                self._block_contexts
                and self._block_contexts[-1].tag == lowered
                and self._block_contexts[-1].same_tag_nesting
            ):
                self._block_contexts[-1].same_tag_nesting -= 1
                return
            matching_block = next(
                (
                    index
                    for index in range(len(self._block_contexts) - 1, -1, -1)
                    if self._block_contexts[index].tag == lowered
                ),
                None,
            )
            if matching_block is not None:
                while len(self._block_contexts) > matching_block:
                    self._finish_block(self._block_contexts.pop())
            if lowered == "div":
                self._content_div_depth -= 1
                if self._content_div_depth <= 0:
                    while self._block_contexts:
                        self._finish_block(self._block_contexts.pop())
                    self._in_content = False
                    self._content_div_depth = 0

    def handle_data(self, data: str) -> None:
        for meta_context in self._meta_contexts:
            meta_context.parts.append(data)
        if self._in_content:
            for block_context in self._block_contexts:
                block_context.parts.append(data)


def parse_confaz_act(raw_html: bytes) -> ConfazActDocument:
    try:
        source = raw_html.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError(f"HTML CONFAZ não é UTF-8 válido: {error}") from None
    if not source.strip() or "<html" not in source[:4096].lower():
        raise ValueError("HTML CONFAZ vazio ou sem raiz HTML reconhecível")

    parser = _ConfazActParser()
    parser.feed(source)
    parser.close()
    while parser._block_contexts:
        parser._finish_block(parser._block_contexts.pop())
    while parser._meta_contexts:
        parser._finish_meta(parser._meta_contexts.pop())

    source_title = next(iter(parser.metadata["source_title"]), "")
    description = next(iter(parser.metadata["description"]), "")
    act_title = next(
        (block.text for block in parser.blocks if block.source_class in {"A1-1TituloAcordo", "TituloAcordo"}),
        "",
    )
    publication_text = "\n".join(block.text for block in parser.blocks if block.source_class == "A2DataPublicacao")
    summary_text = next((block.text for block in parser.blocks if block.source_class in {"A3Ementa", "Ementa"}), "")
    missing = [
        name
        for name, value in (
            ("documentFirstHeading", source_title),
            ("A1-1TituloAcordo/TituloAcordo", act_title),
            ("A2DataPublicacao", publication_text),
            ("A3Ementa/Ementa", summary_text),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"HTML CONFAZ sem campos obrigatórios do contrato: {', '.join(missing)}")
    if len(parser.blocks) < 5:
        raise ValueError(f"volume inesperado de blocos no HTML CONFAZ: {len(parser.blocks)}")
    return ConfazActDocument(
        source_title=source_title,
        description_text=description or None,
        act_title=act_title,
        publication_text=publication_text,
        summary_text=summary_text,
        blocks=tuple(parser.blocks),
    )


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_once(path: Path, content: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(content)
    except FileExistsError:
        if path.read_bytes() != content:
            raise RuntimeError(f"colisão em artefato CONFAZ imutável {path}") from None
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


def extract_confaz_act_artifact(artifact_path: Path, observation_path: Path, output_root: Path) -> dict[str, object]:
    """Reprocessa um ato capturado e salva seus campos literais e blocos estruturais."""
    observation = json.loads(observation_path.read_text(encoding="utf-8"))
    if not isinstance(observation, dict):
        raise ValueError("observação do ato CONFAZ precisa ser objeto JSON")
    raw = artifact_path.read_bytes()
    artifact_digest = hashlib.sha256(raw).hexdigest()
    url = observation.get("requested_url")
    parsed_url = urlsplit(url if isinstance(url, str) else "")
    if (
        observation.get("contract_version") != CONFAZ_ACT_CAPTURE_CONTRACT
        or observation.get("http_status") != 200
        or observation.get("final_url") != url
        or observation.get("artifact_sha256") != artifact_digest
        or observation.get("byte_size") != len(raw)
        or observation.get("source_authority") != "CONFAZ"
        or parsed_url.scheme != "https"
        or parsed_url.netloc != "www.confaz.fazenda.gov.br"
    ):
        raise ValueError("HTML CONFAZ diverge do contrato/proveniência da captura oficial")
    headers = observation.get("response_headers")
    content_type = headers.get("content-type", "") if isinstance(headers, dict) else ""
    if "text/html" not in content_type.lower() or "charset=utf-8" not in content_type.lower().replace(" ", ""):
        raise ValueError("observação CONFAZ não confirma HTML UTF-8")
    try:
        capture_root = observation_path.parents[5]
        expected_observation_parent = capture_root / "acts" / hashlib.sha256(str(url).encode("utf-8")).hexdigest()
        observation_path.resolve().relative_to(expected_observation_parent.resolve())
        raw_relative_path = artifact_path.resolve().relative_to(capture_root.resolve()).as_posix()
    except (IndexError, ValueError):
        raise ValueError("HTML CONFAZ está fora da raiz de captura") from None
    if observation.get("raw_path") != raw_relative_path:
        raise ValueError("caminho do HTML CONFAZ diverge da observação de captura")
    candidate, sitemap_digest, discovery_digest = _load_confaz_candidate(capture_root, str(url))
    if (
        observation.get("sitemap_sha256") != sitemap_digest
        or observation.get("discovery_sha256") != discovery_digest
        or observation.get("source_lastmod") != candidate.source_lastmod
        or observation.get("source_section") != candidate.source_section
    ):
        raise ValueError("proveniência do ato CONFAZ diverge do catálogo oficial verificado")

    document = parse_confaz_act(raw)
    snapshot = (
        "\n".join(
            json.dumps(asdict(block), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            for block in document.blocks
        )
        + "\n"
    ).encode("utf-8")
    snapshot_digest = hashlib.sha256(snapshot).hexdigest()
    url_key = hashlib.sha256(str(url).encode("utf-8")).hexdigest()
    release = output_root.resolve() / "acts" / url_key / "extractions" / artifact_digest / CONFAZ_ACT_BLOCK_CONTRACT
    snapshot_path = release / "confaz-act-blocks.jsonl"
    manifest = {
        "act_title": document.act_title,
        "artifact_sha256": artifact_digest,
        "block_count": len(document.blocks),
        "contract_version": CONFAZ_ACT_BLOCK_CONTRACT,
        "description_text": document.description_text,
        "interpretation_status": "not_performed",
        "lastmod_semantics": "source_metadata_only_not_legal_effective_date",
        "publication_text": document.publication_text,
        "snapshot_sha256": snapshot_digest,
        "source_authority": "CONFAZ",
        "source_lastmod": observation.get("source_lastmod"),
        "source_url": url,
        "summary_text": document.summary_text,
        "sitemap_sha256": sitemap_digest,
        "discovery_sha256": discovery_digest,
    }
    snapshot_created = _write_once(snapshot_path, snapshot)
    manifest_created = _write_once(release / "manifest.json", _json_bytes(manifest))
    result = {
        **manifest,
        "snapshot_path": snapshot_path.relative_to(output_root.resolve()).as_posix(),
        "snapshot_created": snapshot_created,
        "manifest_created": manifest_created,
    }
    pointer = output_root.resolve() / "acts" / url_key / "state" / "latest-extraction.json"
    _write_pointer(pointer, _json_bytes(result))
    return result
