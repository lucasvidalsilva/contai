"""Extrai linhas candidatas das tabelas CEST sem classificar vigência jurídica."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path

from contai_tax_data.cest_capture import CEST_SOURCE_URL

CEST_CANDIDATE_CONTRACT = "cest-candidate-v1"
_CEST_CODE = re.compile(r"^\d{2}\.\d{3}\.\d{2}$")
_EXPECTED_HEADER = ("ITEM", "CEST", "NCM/SH", "DESCRICAO")


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
    legal_status: str = "unresolved"


@dataclass(frozen=True, slots=True)
class CestCandidateExtractionResult:
    artifact_sha256: str
    candidate_set_sha256: str
    candidate_count: int
    candidates_path: str
    candidates_created: bool
    manifest_created: bool


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
        self.cells: list[str] = []
        self.headers: set[int] = set()
        self.candidates: list[CestCandidate] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag == "table":
            self.table_counter += 1
            self.table_stack.append(self.table_counter)
        elif tag == "tr":
            if self.in_row or not self.table_stack:
                return
            self.in_row = True
            self.row_table_index = self.table_stack[-1]
            self.row_index += 1
            self.cells = []
        elif tag in {"td", "th"} and self.in_row and self.table_stack[-1] == self.row_table_index:
            self.in_cell = True
            self.cell_table_index = self.row_table_index
            self.cell_parts = []

    def handle_data(self, data: str) -> None:
        if self.in_cell and self.table_stack and self.table_stack[-1] == self.cell_table_index:
            self.cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self.in_cell and self.table_stack and self.table_stack[-1] == self.cell_table_index:
            self.cells.append(_clean_text("".join(self.cell_parts)))
            self.in_cell = False
            self.cell_table_index = None
        elif tag == "tr" and self.in_row and self.table_stack and self.table_stack[-1] == self.row_table_index:
            self._finish_row()
            self.in_row = False
            self.row_table_index = None
        elif tag == "table":
            if self.table_stack:
                self.table_stack.pop()

    def _finish_row(self) -> None:
        normalized = tuple(_header_text(cell) for cell in self.cells)
        if normalized == _EXPECTED_HEADER:
            assert self.row_table_index is not None
            self.headers.add(self.row_table_index)
            return
        if self.row_table_index not in self.headers or len(self.cells) != 4:
            return
        item, cest_code, ncm_sh_raw, description = self.cells
        if not _CEST_CODE.fullmatch(cest_code) or not item or not ncm_sh_raw or not description:
            return
        self.candidates.append(
            CestCandidate(
                source_table_index=self.row_table_index,
                source_row_index=self.row_index,
                item_label=item,
                cest_code=cest_code,
                ncm_sh_raw=ncm_sh_raw,
                description=description,
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
                {"artifact_sha256": artifact_sha256, **asdict(candidate)},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def cest_candidate_ids(candidates_jsonl: bytes) -> str:
    """Hash do conjunto extraído, separado do hash do HTML bruto."""
    return hashlib.sha256(candidates_jsonl).hexdigest()


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
    relative_path = Path("candidates") / artifact_sha / "cest-candidates.jsonl"
    candidates_created = _write_once(root / relative_path, snapshot)
    manifest = {
        "artifact_sha256": artifact_sha,
        "candidate_count": len(candidates),
        "candidate_set_sha256": candidate_set_sha,
        "contract_version": CEST_CANDIDATE_CONTRACT,
        "parser_id": CEST_CANDIDATE_CONTRACT,
        "source_url": CEST_SOURCE_URL,
        "status": "candidates_unresolved",
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    manifest_created = _write_once(root / "candidates" / artifact_sha / "manifest.json", manifest_bytes)
    _write_pointer(root / "state" / "cest-latest-candidates.json", manifest_bytes)
    return CestCandidateExtractionResult(
        artifact_sha256=artifact_sha,
        candidate_set_sha256=candidate_set_sha,
        candidate_count=len(candidates),
        candidates_path=relative_path.as_posix(),
        candidates_created=candidates_created,
        manifest_created=manifest_created,
    )
