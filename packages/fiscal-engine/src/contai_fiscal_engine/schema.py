"""Validação estrutural offline contra o pacote oficial da NF-e."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Final, cast

from lxml import etree

NFE_SCHEMA_PACKAGE: Final = "PL_010g_v1.03"
_NFE_NAMESPACE = "http://www.portalfiscal.inf.br/nfe"
_SCHEMA_ROOT = Path(__file__).parent / "schemas" / "pl_010g_v1_03"
_SCHEMA_HASHES: Final = {
    "DFeTiposBasicos_v1.00.xsd": "2da0785a6c70db4f93571187a28514dde715cfd0b0f41e746176fbf3444549f2",
    "leiauteNFe_v4.00.xsd": "e8470f5d85ded3d99010676087907214aef71c9626140b672abbafa72656c0f5",
    "nfe_v4.00.xsd": "adce3646c13ceb54922ec3142fc1dc45bd4fb839ac35ad583e86c733c07d27df",
    "tiposBasico_v4.00.xsd": "772619c85723e598840667ca66e7298a250442df47eeb94b397d2a333ce62047",
    "xmldsig-core-schema_v1.01.xsd": "f56744a5f51c03f027de13f39f869307091781a9ef1d91b1ebe14719ce28e1ac",
}


@dataclass(frozen=True, slots=True)
class SchemaValidationResult:
    valid: bool
    error_type: str | None = None
    field_path: str | None = None


def _secure_parser() -> etree.XMLParser:
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        recover=False,
        huge_tree=False,
        remove_comments=False,
    )


@cache
def _schema() -> etree.XMLSchema:
    for filename, expected_hash in _SCHEMA_HASHES.items():
        path = _SCHEMA_ROOT / filename
        try:
            payload = path.read_bytes()
        except OSError as error:
            raise RuntimeError(f"schema NF-e ausente: {filename}") from error
        if hashlib.sha256(payload).hexdigest() != expected_hash:
            raise RuntimeError(f"integridade do schema NF-e inválida: {filename}")
    try:
        document = etree.parse(_SCHEMA_ROOT / "nfe_v4.00.xsd", parser=_secure_parser())
        return etree.XMLSchema(document)
    except (etree.XMLSchemaError, etree.XMLSyntaxError, OSError) as error:
        raise RuntimeError("pacote XSD NF-e não pode ser compilado") from error


def validate_nfe_schema(xml_bytes: bytes) -> SchemaValidationResult:
    """Valida a raiz NFe; em nfeProc, valida somente o filho NFe deste pacote."""
    try:
        root = etree.fromstring(xml_bytes, parser=_secure_parser())
    except (etree.XMLSyntaxError, ValueError):
        return SchemaValidationResult(False, "xml_syntax", None)

    nfe_tag = f"{{{_NFE_NAMESPACE}}}NFe"
    if root.tag == nfe_tag:
        nfe = root
    elif root.tag == f"{{{_NFE_NAMESPACE}}}nfeProc":
        matches = root.findall(nfe_tag)
        if len(matches) != 1:
            return SchemaValidationResult(False, "nfe_proc_structure", "/nfeProc/NFe")
        nfe = matches[0]
    else:
        return SchemaValidationResult(False, "unsupported_root", None)

    schema = _schema()
    if schema.validate(nfe):
        return SchemaValidationResult(True)
    errors = list(cast(Any, schema.error_log))
    if not errors:
        return SchemaValidationResult(False, "xsd_validation", None)
    error = errors[-1]
    return SchemaValidationResult(False, error.type_name or "xsd_validation", error.path)
