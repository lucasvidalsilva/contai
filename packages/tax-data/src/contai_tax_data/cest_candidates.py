"""Extrai linhas candidatas das tabelas CEST sem classificar vigência jurídica."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path

from contai_tax_data.cest_capture import CEST_SOURCE_URL

CEST_CANDIDATE_CONTRACT = "cest-candidate-v5"
_CEST_CODE = re.compile(r"^\d{2}\.\d{3}\.\d{2}$")
_EXPECTED_HEADER = ("ITEM", "CEST", "NCM/SH", "DESCRICAO")
_SEGMENT_HEADER = ("ITEM", "NOME DO SEGMENTO", "CODIGO DO SEGMENTO")


class CestCandidateContractError(ValueError):
    """HTML sem a tabela esperada ou fora do contrato de candidatos."""


@dataclass(frozen=True, slots=True)
class CestCandidate:
    source_table_index: int
    source_row_index: int
    item_label: str
    cest_code: str
    ncm_sh_raw: str
    description: str
    source_context: tuple[str, ...]
    segment_code: str
    segment_name: str | None
    source_cell_classes: tuple[str, ...]
    source_cell_tags: tuple[tuple[str, ...], ...]
    legal_status: str = "unresolved"


@dataclass(frozen=True, slots=True)
class CestCandidateExtractionResult:
    artifact_sha256: str
    candidate_set_sha256: str
    candidate_count: int
    segment_matched_count: int
    segment_unmatched_count: int
    candidates_path: str
    candidates_created: bool
    manifest_created: bool


@dataclass(frozen=True, slots=True)
class CestCandidateDiff:
    previous_artifact_sha256: str
    current_artifact_sha256: str
    previous_candidate_set_sha256: str
    current_candidate_set_sha256: str
    added_occurrences: int
    removed_occurrences: int
    unchanged_occurrences: int


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.table_counter = -1
        self.table_stack: list[int] = []
        self.row_table_index: int | None = None
        self.row_index = 0
        self.in_row = False
        self.in_cell = False
        self.cell_table_index: int | None = None
        self.cell_parts: list[str] = []
        self.cell_classes: list[str] = []
        self.cell_tags: list[str] = []
        self.cells: list[str] = []
        self.cells_classes: list[str] = []
        self.cells_tags: list[tuple[str, ...]] = []
        self.headers: set[int] = set()
        self.table_kinds: dict[int, str] = {}
        self.candidates: list[CestCandidate] = []
        self.segment_names: dict[str, str] = {}
        self.heading_parts: list[str] = []
        self.heading_active = False
        self.heading_context: list[str] = []
        self.context_by_table: dict[int, tuple[str, ...]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        class_value = next((value for name, value in attrs if name == "class" and value), "")
        if tag == "table":
            self.table_counter += 1
            self.table_stack.append(self.table_counter)
            self.context_by_table[self.table_counter] = tuple(self.heading_context)
        elif tag == "tr":
            if self.in_row or not self.table_stack:
                return
            self.in_row = True
            self.row_table_index = self.table_stack[-1]
            self.row_index += 1
            self.cells = []
            self.cells_classes = []
            self.cells_tags = []
        elif tag in {"td", "th"} and self.in_row and self.table_stack[-1] == self.row_table_index:
            self.in_cell = True
            self.cell_table_index = self.row_table_index
            self.cell_parts = []
            self.cell_classes = []
            self.cell_tags = [tag]
            if class_value:
                self.cell_classes.append(_clean_text(class_value))
        elif self.in_cell and self.table_stack and self.table_stack[-1] == self.cell_table_index:
            self.cell_tags.append(tag)
            if class_value:
                self.cell_classes.append(_clean_text(class_value))
        elif tag == "p" and not self.table_stack and class_value.startswith("A6-1Subtitulo"):
            self.heading_active = True
            self.heading_parts = []

    def handle_data(self, data: str) -> None:
        if self.in_cell and self.table_stack and self.table_stack[-1] == self.cell_table_index:
            self.cell_parts.append(data)
        elif self.heading_active:
            self.heading_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self.in_cell and self.table_stack and self.table_stack[-1] == self.cell_table_index:
            self.cells.append(_clean_text("".join(self.cell_parts)))
            self.cells_classes.append(" ".join(self.cell_classes))
            self.cells_tags.append(tuple(self.cell_tags))
            self.in_cell = False
            self.cell_table_index = None
        elif tag == "tr" and self.in_row and self.table_stack and self.table_stack[-1] == self.row_table_index:
            self._finish_row()
            self.in_row = False
            self.row_table_index = None
        elif tag == "table":
            if self.table_stack:
                self.table_stack.pop()
        elif tag == "p" and self.heading_active:
            heading = _clean_text("".join(self.heading_parts))
            self.heading_active = False
            if heading:
                if "ANEXO " in _header_text(heading):
                    self.heading_context = [heading]
                else:
                    self.heading_context.append(heading)
                    self.heading_context = self.heading_context[-8:]

    def _finish_row(self) -> None:
        row_table_index = self.row_table_index
        if row_table_index is None:
            return
        normalized = tuple(_header_text(cell) for cell in self.cells)
        if normalized == _EXPECTED_HEADER:
            self.headers.add(row_table_index)
            self.table_kinds[row_table_index] = "cest"
            return
        if normalized == _SEGMENT_HEADER:
            self.table_kinds[row_table_index] = "segment"
            return
        table_kind = self.table_kinds.get(row_table_index)
        if table_kind == "segment" and len(self.cells) == 3:
            _, segment_name, segment_code = self.cells
            if re.fullmatch(r"\d{2}", segment_code) and segment_name:
                self.segment_names[segment_code] = segment_name
            return
        if table_kind != "cest" or row_table_index not in self.headers or len(self.cells) != 4:
            return
        item, cest_code, ncm_sh_raw, description = self.cells
        if not _CEST_CODE.fullmatch(cest_code) or not item or not ncm_sh_raw or not description:
            return
        segment_code = cest_code[:2]
        self.candidates.append(
            CestCandidate(
                source_table_index=row_table_index,
                source_row_index=self.row_index,
                item_label=item,
                cest_code=cest_code,
                ncm_sh_raw=ncm_sh_raw,
                description=description,
                source_context=self.context_by_table.get(row_table_index, ()),
                segment_code=segment_code,
                segment_name=self.segment_names.get(segment_code),
                source_cell_classes=tuple(self.cells_classes),
                source_cell_tags=tuple(self.cells_tags),
            )
        )


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _header_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _clean_text(ascii_text).upper()


def parse_cest_candidates(body: bytes) -> tuple[CestCandidate, ...]:
    """Retorna linhas CEST vinculadas à tabela/linha fonte e com status não resolvido."""
    try:
        html = body.decode("utf-8")
    except UnicodeDecodeError:
        raise CestCandidateContractError("HTML CEST nao e UTF-8") from None
    parser = _TableParser()
    parser.feed(html)
    parser.close()
    if not parser.headers:
        raise CestCandidateContractError("cabecalho ITEM/CEST/NCM/SH/DESCRICAO ausente")
    if not parser.candidates:
        raise CestCandidateContractError("nenhuma linha candidata CEST encontrada")
    return tuple(parser.candidates)


def cest_candidates_jsonl(candidates: tuple[CestCandidate, ...], artifact_sha256: str) -> bytes:
    """Serializa candidatos em ordem de origem, sem uma release fiscal/publicável."""
    if not re.fullmatch(r"[0-9a-f]{64}", artifact_sha256):
        raise ValueError("artifact_sha256 invalido")
    lines = []
    for candidate in candidates:
        lines.append(
            json.dumps(
                {"artifact_sha256": artifact_sha256, "parser_id": CEST_CANDIDATE_CONTRACT, **asdict(candidate)},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def cest_candidate_ids(candidates_jsonl: bytes) -> str:
    """Hash do conjunto extraído, separado do hash do HTML bruto."""
    return hashlib.sha256(candidates_jsonl).hexdigest()


def diff_cest_candidate_snapshots(previous: bytes, current: bytes) -> CestCandidateDiff:
    """Compara ocorrências textuais; não classifica inclusão ou revogação legal."""
    signature_fields = (
        "item_label",
        "cest_code",
        "ncm_sh_raw",
        "description",
        "source_context",
        "segment_code",
        "segment_name",
        "source_cell_classes",
        "source_cell_tags",
        "legal_status",
    )

    def read_snapshot(body: bytes) -> tuple[str, Counter[str]]:
        try:
            records = [json.loads(line) for line in body.decode("utf-8").splitlines() if line.strip()]
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("snapshot de candidatos CEST invalido") from None
        if not records or any(not isinstance(record, dict) for record in records):
            raise ValueError("snapshot de candidatos CEST vazio ou fora do contrato")
        artifact_ids = {record.get("artifact_sha256") for record in records}
        if len(artifact_ids) != 1 or not all(
            isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for value in artifact_ids
        ):
            raise ValueError("snapshot precisa conter um unico artifact_sha256 valido")
        for record in records:
            if record.get("parser_id") != CEST_CANDIDATE_CONTRACT or record.get("legal_status") != "unresolved":
                raise ValueError("parser ou estado juridico incompatível no snapshot CEST")
            if any(field not in record for field in signature_fields):
                raise ValueError("campos de comparacao ausentes no snapshot CEST")
        signatures = Counter(
            json.dumps([record[field] for field in signature_fields], ensure_ascii=False, sort_keys=True)
            for record in records
        )
        return next(iter(artifact_ids)), signatures

    previous_artifact, previous_signatures = read_snapshot(previous)
    current_artifact, current_signatures = read_snapshot(current)
    added = current_signatures - previous_signatures
    removed = previous_signatures - current_signatures
    return CestCandidateDiff(
        previous_artifact_sha256=previous_artifact,
        current_artifact_sha256=current_artifact,
        previous_candidate_set_sha256=hashlib.sha256(previous).hexdigest(),
        current_candidate_set_sha256=hashlib.sha256(current).hexdigest(),
        added_occurrences=sum(added.values()),
        removed_occurrences=sum(removed.values()),
        unchanged_occurrences=sum((previous_signatures & current_signatures).values()),
    )


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


def extract_cest_candidate_artifact(artifact_path: Path, output_dir: Path) -> CestCandidateExtractionResult:
    """Extrai candidatos de HTML já capturado; nunca decide estado vigente."""
    body = artifact_path.read_bytes()
    artifact_sha = hashlib.sha256(body).hexdigest()
    candidates = parse_cest_candidates(body)
    snapshot = cest_candidates_jsonl(candidates, artifact_sha)
    candidate_set_sha = cest_candidate_ids(snapshot)
    root = output_dir.resolve()
    relative_path = Path("candidates") / artifact_sha / CEST_CANDIDATE_CONTRACT / "cest-candidates.jsonl"
    candidates_created = _write_once(root / relative_path, snapshot)
    manifest = {
        "artifact_sha256": artifact_sha,
        "candidate_count": len(candidates),
        "candidate_set_sha256": candidate_set_sha,
        "contract_version": CEST_CANDIDATE_CONTRACT,
        "segment_matched_count": sum(candidate.segment_name is not None for candidate in candidates),
        "segment_unmatched_count": sum(candidate.segment_name is None for candidate in candidates),
        "parser_id": CEST_CANDIDATE_CONTRACT,
        "source_url": CEST_SOURCE_URL,
        "status": "candidates_unresolved",
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    manifest_created = _write_once(
        root / "candidates" / artifact_sha / CEST_CANDIDATE_CONTRACT / "manifest.json", manifest_bytes
    )
    _write_pointer(root / "state" / "cest-latest-candidates.json", manifest_bytes)
    return CestCandidateExtractionResult(
        artifact_sha256=artifact_sha,
        candidate_set_sha256=candidate_set_sha,
        candidate_count=len(candidates),
        segment_matched_count=sum(candidate.segment_name is not None for candidate in candidates),
        segment_unmatched_count=sum(candidate.segment_name is None for candidate in candidates),
        candidates_path=relative_path.as_posix(),
        candidates_created=candidates_created,
        manifest_created=manifest_created,
    )
