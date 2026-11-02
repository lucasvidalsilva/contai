"""Serialização verificável da projeção NCM consumida pelo motor."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any, Final

from contai_fiscal_engine.models import NcmCatalogSnapshot

NCM_CATALOG_CONTRACT_VERSION: Final = "contai-ncm-catalog-v1"
_MAX_CATALOG_BYTES = 1_000_000
_MIN_NCM_CODES = 9_000
_MAX_NCM_CODES = 20_000
_PAYLOAD_KEYS = frozenset(
    {
        "code_count",
        "code_digits",
        "contract_version",
        "projection_sha256",
        "release_id",
        "snapshot_sha256",
        "source_as_of",
    }
)


def _projection_bytes(codes: list[str]) -> bytes:
    return ("\n".join(codes) + "\n").encode()


def _sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{field} deve ser SHA-256 hexadecimal minúsculo")
    return value


def dump_ncm_catalog(snapshot: NcmCatalogSnapshot) -> bytes:
    """Produz um manifesto canônico sem descrições ou outros campos da fonte."""
    codes = sorted(snapshot.code_digits)
    if not _MIN_NCM_CODES <= len(codes) <= _MAX_NCM_CODES:
        raise ValueError("quantidade de códigos NCM fora do limite")
    projection_sha256 = hashlib.sha256(_projection_bytes(codes)).hexdigest()
    payload = {
        "code_count": len(codes),
        "code_digits": codes,
        "contract_version": NCM_CATALOG_CONTRACT_VERSION,
        "projection_sha256": projection_sha256,
        "release_id": snapshot.release_id,
        "snapshot_sha256": snapshot.snapshot_sha256,
        "source_as_of": snapshot.source_as_of.isoformat(),
    }
    return (json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode()


def load_ncm_catalog(payload_bytes: bytes) -> NcmCatalogSnapshot:
    """Valida e carrega um manifesto NCM previamente sincronizado para o dispositivo."""
    if not payload_bytes or len(payload_bytes) > _MAX_CATALOG_BYTES:
        raise ValueError("tamanho do catálogo NCM fora do limite")
    try:
        payload = json.loads(payload_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("catálogo NCM deve ser JSON UTF-8 válido") from error
    if not isinstance(payload, dict) or set(payload) != _PAYLOAD_KEYS:
        raise ValueError("schema do catálogo NCM inesperado")
    if payload["contract_version"] != NCM_CATALOG_CONTRACT_VERSION:
        raise ValueError("versão do catálogo NCM não suportada")

    codes_value = payload["code_digits"]
    code_count = payload["code_count"]
    if (
        not isinstance(codes_value, list)
        or isinstance(code_count, bool)
        or not isinstance(code_count, int)
        or code_count != len(codes_value)
        or not _MIN_NCM_CODES <= code_count <= _MAX_NCM_CODES
        or any(not isinstance(code, str) for code in codes_value)
    ):
        raise ValueError("contagem ou lista de códigos NCM inválida")
    codes: list[str] = codes_value
    if codes != sorted(codes) or len(set(codes)) != len(codes):
        raise ValueError("códigos NCM devem ser únicos e ordenados")

    expected_projection_hash = _sha256(payload["projection_sha256"], "projection_sha256")
    observed_projection_hash = hashlib.sha256(_projection_bytes(codes)).hexdigest()
    if observed_projection_hash != expected_projection_hash:
        raise ValueError("hash da projeção NCM diverge do conteúdo")
    try:
        source_as_of = date.fromisoformat(payload["source_as_of"])
    except (TypeError, ValueError) as error:
        raise ValueError("source_as_of do catálogo NCM deve usar AAAA-MM-DD") from error

    return NcmCatalogSnapshot(
        release_id=_sha256(payload["release_id"], "release_id"),
        snapshot_sha256=_sha256(payload["snapshot_sha256"], "snapshot_sha256"),
        source_as_of=source_as_of,
        code_digits=frozenset(codes),
    )
