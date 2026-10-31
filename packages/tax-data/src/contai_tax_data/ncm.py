"""Contrato, normalizacao e qualidade da NCM vigente do Siscomex."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Any, Final, Literal

NCM_CONTRACT_VERSION: Final = "ncm-v1"
NCM_SOURCE_SCHEMA_VERSION: Final = "siscomex-ncm-json-v1"

NcmLevel = Literal["chapter", "position", "subposition_1", "subposition_2", "item", "subitem"]

_TOP_LEVEL_KEYS = frozenset({"Data_Ultima_Atualizacao_NCM", "Ato", "Nomenclaturas"})
_ENTRY_KEYS = frozenset(
    {"Codigo", "Descricao", "Data_Inicio", "Data_Fim", "Tipo_Ato_Ini", "Numero_Ato_Ini", "Ano_Ato_Ini"}
)
_CODE_PATTERNS: tuple[tuple[re.Pattern[str], NcmLevel], ...] = (
    (re.compile(r"^\d{2}$"), "chapter"),
    (re.compile(r"^\d{2}\.\d{2}$"), "position"),
    (re.compile(r"^\d{4}\.\d$"), "subposition_1"),
    (re.compile(r"^\d{4}\.\d{2}$"), "subposition_2"),
    (re.compile(r"^\d{4}\.\d{2}\.\d$"), "item"),
    (re.compile(r"^\d{4}\.\d{2}\.\d{2}$"), "subitem"),
)
_AS_OF_PATTERN = re.compile(r"^Vigente em (\d{2}/\d{2}/\d{4})$")


class NcmContractError(ValueError):
    """O artefato nao cumpre o schema oficial confirmado."""


class NcmQualityError(ValueError):
    """O artefato cumpre o schema, mas falha em controles de qualidade."""


@dataclass(frozen=True, slots=True)
class NcmEntry:
    code: str
    code_digits: str
    description: str
    level: NcmLevel
    parent_code: str | None
    valid_from: date
    valid_to: date | None
    initial_act_type: str
    initial_act_number: str
    initial_act_year: str
    source_row_id: str

    def as_dict(self) -> dict[str, str | None]:
        return {
            "code": self.code,
            "code_digits": self.code_digits,
            "description": self.description,
            "initial_act_number": self.initial_act_number,
            "initial_act_type": self.initial_act_type,
            "initial_act_year": self.initial_act_year,
            "level": self.level,
            "parent_code": self.parent_code,
            "source_row_id": self.source_row_id,
            "valid_from": self.valid_from.isoformat(),
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
        }


@dataclass(frozen=True, slots=True)
class NcmDataset:
    source_act: str
    source_as_of: date
    entries: tuple[NcmEntry, ...]

    @property
    def leaf_count(self) -> int:
        return sum(entry.level == "subitem" for entry in self.entries)

    def snapshot_jsonl(self) -> bytes:
        lines = (
            json.dumps(entry.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            for entry in self.entries
        )
        return ("\n".join(lines) + "\n").encode()

    def release_identity(self) -> bytes:
        """Identidade sem data de captura nem o cabecalho diario `Vigente em`."""
        payload = {
            "contract_version": NCM_CONTRACT_VERSION,
            "entries": [entry.as_dict() for entry in self.entries],
            "source_act": self.source_act,
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()

    @property
    def release_id(self) -> str:
        return hashlib.sha256(self.release_identity()).hexdigest()


@dataclass(frozen=True, slots=True)
class QualityPolicy:
    min_entries: int = 14_000
    max_entries: int = 25_000
    min_leaf_entries: int = 9_000
    min_chapters: int = 90


DEFAULT_QUALITY_POLICY: Final = QualityPolicy()


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _string(mapping: dict[str, Any], key: str, context: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise NcmContractError(f"{context}.{key} deve ser texto nao vazio")
    return _clean_text(value)


def _date(value: str, context: str, *, open_end: bool = False) -> date | None:
    if open_end and value == "31/12/9999":
        return None
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError as error:
        raise NcmContractError(f"{context} deve usar DD/MM/AAAA: {value!r}") from error


def _level(code: str, context: str) -> NcmLevel:
    for pattern, level in _CODE_PATTERNS:
        if pattern.fullmatch(code):
            return level
    raise NcmContractError(f"{context}.Codigo tem formato NCM desconhecido: {code!r}")


def _object(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise NcmContractError(f"{context} deve ser objeto JSON")
    return value


def _check_keys(mapping: dict[str, Any], expected: frozenset[str], context: str) -> None:
    actual = frozenset(mapping)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise NcmContractError(f"schema mudou em {context}: ausentes={missing}, inesperados={unexpected}")


def parse_ncm_json(raw: bytes) -> NcmDataset:
    """Decodifica UTF-8/BOM e aplica o contrato estrito observado em 30/10/2026."""
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise NcmContractError("artefato NCM nao esta em UTF-8") from error
    try:
        root = _object(json.loads(decoded), "raiz")
    except json.JSONDecodeError as error:
        raise NcmContractError(f"JSON NCM malformado na linha {error.lineno}, coluna {error.colno}") from error

    _check_keys(root, _TOP_LEVEL_KEYS, "raiz")
    source_act = _string(root, "Ato", "raiz")
    as_of_text = _string(root, "Data_Ultima_Atualizacao_NCM", "raiz")
    as_of_match = _AS_OF_PATTERN.fullmatch(as_of_text)
    if not as_of_match:
        raise NcmContractError("raiz.Data_Ultima_Atualizacao_NCM mudou de formato")
    parsed_as_of = _date(as_of_match.group(1), "raiz.Data_Ultima_Atualizacao_NCM")
    if parsed_as_of is None:
        raise AssertionError("data de referencia nao pode ser aberta")

    items = root["Nomenclaturas"]
    if not isinstance(items, list) or not items:
        raise NcmContractError("raiz.Nomenclaturas deve ser lista nao vazia")

    provisional: list[NcmEntry] = []
    seen_codes: set[str] = set()
    seen_digits: set[str] = set()
    for index, item in enumerate(items, start=1):
        context = f"Nomenclaturas[{index}]"
        row = _object(item, context)
        _check_keys(row, _ENTRY_KEYS, context)
        code = _string(row, "Codigo", context)
        code_digits = code.replace(".", "")
        if code in seen_codes or code_digits in seen_digits:
            raise NcmContractError(f"codigo NCM duplicado em {context}: {code}")
        seen_codes.add(code)
        seen_digits.add(code_digits)

        valid_from = _date(_string(row, "Data_Inicio", context), f"{context}.Data_Inicio")
        valid_to = _date(_string(row, "Data_Fim", context), f"{context}.Data_Fim", open_end=True)
        if valid_from is None:
            raise AssertionError("inicio de vigencia nao pode ser aberto")

        act_number = _string(row, "Numero_Ato_Ini", context)
        act_year = _string(row, "Ano_Ato_Ini", context)
        if not act_number.isdigit():
            raise NcmContractError(f"{context}.Numero_Ato_Ini deve conter somente digitos")
        if not re.fullmatch(r"\d{4}", act_year):
            raise NcmContractError(f"{context}.Ano_Ato_Ini deve ter quatro digitos")

        provisional.append(
            NcmEntry(
                code=code,
                code_digits=code_digits,
                description=_string(row, "Descricao", context),
                level=_level(code, context),
                parent_code=None,
                valid_from=valid_from,
                valid_to=valid_to,
                initial_act_type=_string(row, "Tipo_Ato_Ini", context),
                initial_act_number=act_number,
                initial_act_year=act_year,
                source_row_id=f"Codigo:{code}",
            )
        )

    by_digits = {entry.code_digits: entry.code for entry in provisional}
    entries: list[NcmEntry] = []
    for entry in provisional:
        parents = [
            digits
            for digits in by_digits
            if len(digits) < len(entry.code_digits) and entry.code_digits.startswith(digits)
        ]
        parent = by_digits[max(parents, key=len)] if parents else None
        entries.append(replace(entry, parent_code=parent))
    entries.sort(key=lambda entry: (entry.code_digits, entry.code))
    return NcmDataset(source_act=source_act, source_as_of=parsed_as_of, entries=tuple(entries))


def validate_ncm(dataset: NcmDataset, policy: QualityPolicy = DEFAULT_QUALITY_POLICY) -> None:
    """Controles que impedem publicar uma captura estruturalmente plausivel, mas suspeita."""
    count = len(dataset.entries)
    errors: list[str] = []
    if not policy.min_entries <= count <= policy.max_entries:
        errors.append(f"quantidade total {count} fora de [{policy.min_entries}, {policy.max_entries}]")
    if dataset.leaf_count < policy.min_leaf_entries:
        errors.append(f"subitens de 8 digitos {dataset.leaf_count} abaixo de {policy.min_leaf_entries}")
    chapters = sum(entry.level == "chapter" for entry in dataset.entries)
    if chapters < policy.min_chapters:
        errors.append(f"capitulos {chapters} abaixo de {policy.min_chapters}")

    codes = {entry.code for entry in dataset.entries}
    for entry in dataset.entries:
        if entry.valid_to is not None and entry.valid_to < entry.valid_from:
            errors.append(f"vigencia invertida em {entry.code}")
        if entry.level == "chapter" and entry.parent_code is not None:
            errors.append(f"capitulo {entry.code} nao pode ter pai")
        if entry.level != "chapter" and (entry.parent_code is None or entry.parent_code not in codes):
            errors.append(f"hierarquia sem pai para {entry.code}")
        if len(errors) >= 20:
            break
    if errors:
        raise NcmQualityError("; ".join(errors))
