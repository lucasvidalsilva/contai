"""Contratos públicos e imutáveis do motor fiscal local."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

Severity = Literal["info", "warning", "error"]


@dataclass(frozen=True, slots=True)
class Alert:
    rule_id: str
    rule_version: str
    severity: Severity
    code: str
    message: str
    field_path: str | None
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AnalysisReport:
    contract_version: str
    status: Literal["analyzed", "rejected"]
    document_model: str | None
    issue_date: date | None
    ncm_release_id: str | None
    alerts: tuple[Alert, ...]


@dataclass(frozen=True, slots=True)
class NcmCatalogSnapshot:
    """Projeção local de uma release NCM; a cobertura é somente a data indicada."""

    release_id: str
    snapshot_sha256: str
    source_as_of: date
    code_digits: frozenset[str]
    coverage_mode: Literal["single_date"] = "single_date"

    def __post_init__(self) -> None:
        if self.coverage_mode != "single_date":
            raise ValueError("cobertura NCM deve ser declarada como single_date")
        for name, value in (("release_id", self.release_id), ("snapshot_sha256", self.snapshot_sha256)):
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError(f"{name} deve ser SHA-256 hexadecimal minúsculo")
        if any(len(code) != 8 or not code.isascii() or not code.isdigit() for code in self.code_digits):
            raise ValueError("snapshot NCM aceita somente códigos de oito dígitos")
