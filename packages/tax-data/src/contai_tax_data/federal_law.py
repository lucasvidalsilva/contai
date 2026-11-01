"""Extração estrutural e literal de blocos da página oficial da LC 214."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal

LC214_BLOCK_PARSER_ID = "federal-law-block-v3"
MarkerKind = Literal["article", "paragraph", "sole_paragraph", "roman_item", "letter_item", "numbered_item", "text"]
BlockTag = Literal["p", "td", "th"]
_ARTICLE = re.compile(r"^Art\.\s*(\d+(?:º|°|o)?(?:-[A-Z])?)(?:\.)?(?=\s|$)", re.IGNORECASE)
_PARAGRAPH = re.compile(r"^(§{1,2})\s*(\d+)(?:º|°)?(?=\s|$)")
_ROMAN_ITEM = re.compile(r"^([IVXLCDM]+)\s*[-\u2013\u2014](?=\s|$)")
_LETTER_ITEM = re.compile(r"^([a-z])\)\s", re.IGNORECASE)
_NUMBERED_ITEM = re.compile(r"^(\d+)\.\s")


@dataclass(frozen=True, slots=True)
class LawBlock:
    source_block_index: int
    source_class: str | None
    source_tag: BlockTag
    marker_kind: MarkerKind
    marker: str | None
    text: str


@dataclass(slots=True)
class _BlockContext:
    tag: BlockTag
    source_block_index: int
    source_class: str | None
    parts: list[str]
    contains_nested_block: bool = False


class _ParagraphParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[LawBlock] = []
        self._block_index = -1
        self._contexts: list[_BlockContext] = []

    def _finish_block(self, context: _BlockContext) -> None:
        text = " ".join("".join(context.parts).split())
        if text and not context.contains_nested_block:
            marker_kind, marker = _classify_marker(text)
            self.blocks.append(
                LawBlock(
                    source_block_index=context.source_block_index,
                    source_class=context.source_class,
                    source_tag=context.tag,
                    marker_kind=marker_kind,
                    marker=marker,
                    text=text,
                )
            )

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered_tag = tag.lower()
        if lowered_tag in {"p", "td", "th"}:
            if self._contexts:
                self._contexts[-1].contains_nested_block = True
            self._block_index += 1
            self._contexts.append(
                _BlockContext(
                    tag=lowered_tag,  # type: ignore[arg-type]
                    source_block_index=self._block_index,
                    source_class=next((value for name, value in attrs if name.lower() == "class"), None),
                    parts=[],
                )
            )
        elif self._contexts and lowered_tag in {"br", "hr"}:
            self._contexts[-1].parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        lowered_tag = tag.lower()
        matching_index = next(
            (index for index in range(len(self._contexts) - 1, -1, -1) if self._contexts[index].tag == lowered_tag),
            None,
        )
        if matching_index is not None:
            while len(self._contexts) > matching_index:
                self._finish_block(self._contexts.pop())

    def handle_data(self, data: str) -> None:
        for context in self._contexts:
            context.parts.append(data)


def _classify_marker(text: str) -> tuple[MarkerKind, str | None]:
    article = _ARTICLE.match(text)
    if article:
        return "article", article.group(1)
    paragraph = _PARAGRAPH.match(text)
    if paragraph:
        return "paragraph", f"{paragraph.group(1)} {paragraph.group(2)}"
    if text.lower().startswith("parágrafo único"):
        return "sole_paragraph", "Parágrafo único"
    roman = _ROMAN_ITEM.match(text)
    if roman:
        return "roman_item", roman.group(1)
    letter = _LETTER_ITEM.match(text)
    if letter:
        return "letter_item", letter.group(1).lower()
    numbered = _NUMBERED_ITEM.match(text)
    if numbered:
        return "numbered_item", numbered.group(1)
    return "text", None


def parse_lc214_blocks(raw_html: bytes) -> list[LawBlock]:
    """Extrai parágrafos visíveis sem relacionar versões nem inferir efeitos jurídicos."""
    try:
        document = raw_html.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError(f"HTML LC 214 não é UTF-8 válido: {error}") from None
    if not document.strip() or "<html" not in document[:4096].lower():
        raise ValueError("HTML LC 214 vazio ou sem raiz HTML reconhecível")
    parser = _ParagraphParser()
    try:
        parser.feed(document)
        parser.close()
    except Exception as error:
        raise ValueError(f"HTML LC 214 malformado: {error}") from None
    while parser._contexts:
        parser._finish_block(parser._contexts.pop())
    return parser.blocks


def validate_lc214_block_volume(blocks: list[LawBlock]) -> None:
    article_count = sum(block.marker_kind == "article" for block in blocks)
    if not 200 <= article_count <= 1_000:
        raise ValueError(f"contagem inesperada de artigos no HTML LC 214: {article_count}")
    if not 1_000 <= len(blocks) <= 20_000:
        raise ValueError(f"contagem inesperada de blocos no HTML LC 214: {len(blocks)}")


def blocks_jsonl(blocks: list[LawBlock]) -> bytes:
    lines = (json.dumps(asdict(block), ensure_ascii=False, sort_keys=True, separators=(",", ":")) for block in blocks)
    return ("\n".join(lines) + "\n").encode("utf-8")


def write_lc214_blocks(raw_path: Path, capture_manifest_path: Path, output_dir: Path) -> dict[str, object]:
    """Reprocessa captura arquivada e grava snapshot imutável de blocos literais."""
    capture = json.loads(capture_manifest_path.read_text(encoding="utf-8"))
    if not isinstance(capture, dict):
        raise ValueError("observação LC 214 precisa ser um objeto JSON")
    raw = raw_path.read_bytes()
    source_hash = hashlib.sha256(raw).hexdigest()
    if (
        capture.get("artifact_sha256") != source_hash
        or capture.get("contract_version") != "camara-law-current-raw-v1"
        or capture.get("requested_url")
        != "https://www2.camara.leg.br/legin/fed/leicom/2025/leicomplementar-214-16-janeiro-2025-796905-normaatualizada-pl.html"
        or capture.get("final_url") != capture.get("requested_url")
        or capture.get("source_authority") != "Câmara dos Deputados - Legislação Informatizada"
        or capture.get("http_status") != 200
    ):
        raise ValueError("bruto LC 214 diverge da observação oficial de captura")
    headers = capture.get("response_headers")
    content_type = headers.get("content-type", "") if isinstance(headers, dict) else ""
    if "text/html" not in content_type.lower() or "charset=utf-8" not in content_type.lower().replace(" ", ""):
        raise ValueError("Content-Type da observação LC 214 precisa ser HTML UTF-8")
    try:
        capture_root = capture_manifest_path.parents[3]
        raw_relative_path = raw_path.resolve().relative_to(capture_root.resolve()).as_posix()
    except (IndexError, ValueError):
        raise ValueError("bruto LC 214 está fora da raiz da captura") from None
    if capture.get("raw_path") != raw_relative_path:
        raise ValueError("bruto LC 214 diverge da observação oficial de captura")
    blocks = parse_lc214_blocks(raw)
    validate_lc214_block_volume(blocks)
    snapshot = blocks_jsonl(blocks)
    snapshot_hash = hashlib.sha256(snapshot).hexdigest()
    release_dir = output_dir / "blocks" / source_hash / LC214_BLOCK_PARSER_ID
    release_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = release_dir / "lc214-blocks.jsonl"
    manifest_path = release_dir / "manifest.json"
    manifest = {
        "artifact_sha256": source_hash,
        "block_count": len(blocks),
        "contract_version": LC214_BLOCK_PARSER_ID,
        "marker_counts": {
            kind: sum(block.marker_kind == kind for block in blocks)
            for kind in ("article", "paragraph", "sole_paragraph", "roman_item", "letter_item", "numbered_item", "text")
        },
        "interpretation_status": "not_performed",
        "snapshot_sha256": snapshot_hash,
        "source_authority": "Câmara dos Deputados - Legislação Informatizada",
        "source_url": capture["requested_url"],
    }
    for path, content in (
        (snapshot_path, snapshot),
        (manifest_path, (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")),
    ):
        try:
            with path.open("xb") as stream:
                stream.write(content)
        except FileExistsError:
            if path.read_bytes() != content:
                raise RuntimeError(f"colisão no snapshot LC 214 imutável {path}") from None
    pointer = {**manifest, "snapshot_path": snapshot_path.relative_to(output_dir).as_posix()}
    pointer_path = output_dir / "state" / "lc214-latest-blocks.json"
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=pointer_path.parent, prefix=f".{pointer_path.name}.", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write((json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, pointer_path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    return pointer
