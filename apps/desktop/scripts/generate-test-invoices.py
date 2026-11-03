"""Gera uma matriz local de NF-e totalmente sintéticas para validar o desktop."""

from __future__ import annotations

import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DESKTOP_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPOSITORY_ROOT / "packages" / "fiscal-engine" / "tests" / "fixtures" / "nfe-synthetic-55.xml"
OUTPUT = DESKTOP_ROOT / "var" / "test-invoices"


def replace_once(payload: bytes, original: bytes, replacement: bytes) -> bytes:
    if payload.count(original) != 1:
        raise ValueError(f"trecho sintético não é único: {original!r}")
    return payload.replace(original, replacement, 1)


def case(
    file_name: str,
    payload: bytes,
    status: str,
    alert_codes: list[str],
    purpose: str,
    desktop_boundary: str | None = None,
) -> dict[str, object]:
    (OUTPUT / file_name).write_bytes(payload)
    return {
        "file": file_name,
        "status": status,
        "alert_codes": alert_codes,
        "purpose": purpose,
        "desktop_boundary": desktop_boundary,
    }


def main() -> None:
    base = SOURCE.read_bytes()
    OUTPUT.mkdir(parents=True, exist_ok=True)

    product_total = replace_once(
        base,
        b"<vProd>10.00</vProd>\n        <vFrete>0.00</vFrete>",
        b"<vProd>11.00</vProd>\n        <vFrete>0.00</vFrete>",
    )
    component_totals = base
    for field in ("vFrete", "vSeg", "vDesc", "vOutro"):
        component_totals = replace_once(
            component_totals,
            f"<{field}>0.00</{field}>".encode(),
            f"<{field}>1.00</{field}>".encode(),
        )
    item_value = replace_once(base, b"<qCom>2.0000</qCom>", b"<qCom>3.0000</qCom>")
    invalid_schema = replace_once(base, b"      <natOp>VENDA SINTETICA PARA TESTES</natOp>\n", b"")
    unsupported_model = replace_once(base, b"<mod>55</mod>", b"<mod>65</mod>")
    missing_namespace = replace_once(base, b' xmlns="http://www.portalfiscal.inf.br/nfe"', b"")
    utf16 = base.decode("utf-8").encode("utf-16")
    over_limit = base + b" " * (2_000_001 - len(base))

    cases = [
        case(
            "01-nfe-valida.xml",
            base,
            "analyzed",
            [],
            "Fluxo nominal sem alertas para as regras habilitadas.",
        ),
        case(
            "02-total-produtos-divergente.xml",
            product_total,
            "analyzed",
            ["product_total_mismatch"],
            "Alerta de divergência entre itens incluídos e total de produtos.",
        ),
        case(
            "03-componentes-total-divergentes.xml",
            component_totals,
            "analyzed",
            [
                "discount_total_mismatch",
                "freight_total_mismatch",
                "insurance_total_mismatch",
                "other_total_mismatch",
            ],
            "Múltiplos alertas determinísticos no mesmo documento.",
        ),
        case(
            "04-valor-item-divergente.xml",
            item_value,
            "analyzed",
            ["commercial_product_value_mismatch"],
            "Alerta no cálculo de quantidade por valor unitário.",
        ),
        case(
            "05-schema-invalido.xml",
            invalid_schema,
            "rejected",
            ["schema_validation_failed"],
            "Rejeição por campo obrigatório ausente.",
        ),
        case(
            "06-modelo-65-nao-suportado.xml",
            unsupported_model,
            "rejected",
            ["document_rejected"],
            "Rejeição de NFC-e modelo 65 fora do escopo.",
        ),
        case(
            "07-xml-malformado.xml",
            b"<NFe>",
            "rejected",
            ["document_rejected"],
            "Rejeição de XML truncado.",
        ),
        case(
            "08-doctype-bloqueado.xml",
            b'<!DOCTYPE NFe [<!ENTITY x "boom">]><NFe>&x;</NFe>',
            "rejected",
            ["document_rejected"],
            "Bloqueio de DTD e entidade externa.",
        ),
        case(
            "09-sem-namespace.xml",
            missing_namespace,
            "rejected",
            ["document_rejected"],
            "Rejeição de documento fora do namespace oficial.",
        ),
        case(
            "10-codificacao-utf16.xml",
            utf16,
            "rejected",
            ["document_rejected"],
            "Rejeição de codificação não aceita pelo contrato local.",
        ),
        case(
            "11-vazio.xml",
            b"",
            "rejected",
            ["document_rejected"],
            "Arquivo vazio bloqueado antes da execução do motor.",
            "invalid_invoice_size",
        ),
        case(
            "12-acima-de-2mb.xml",
            over_limit,
            "rejected",
            ["document_rejected"],
            "Arquivo acima do limite de 2 MB bloqueado pelo desktop.",
            "invalid_invoice_size",
        ),
    ]

    manifest = {
        "contract_version": "contai-desktop-testdata-v1",
        "synthetic_only": True,
        "source": str(SOURCE.relative_to(REPOSITORY_ROOT)).replace("\\", "/"),
        "cases": cases,
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"{len(cases)} NF-e sintéticas geradas em {OUTPUT}")


if __name__ == "__main__":
    main()
