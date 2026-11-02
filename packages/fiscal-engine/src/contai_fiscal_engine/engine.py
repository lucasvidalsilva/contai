"""Análise estrutural restrita a NF-e sintética modelo 55."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

from contai_fiscal_engine.models import Alert, AnalysisReport, NcmCatalogSnapshot
from contai_fiscal_engine.schema import NFE_SCHEMA_PACKAGE, validate_nfe_schema

ENGINE_CONTRACT_VERSION = "fiscal-engine-v1"
_MAX_XML_BYTES = 2_000_000
_MAX_ITEMS = 5_000
_NFE_NAMESPACE = "http://www.portalfiscal.inf.br/nfe"
_MONEY_QUANTUM = Decimal("0.01")
_MONEY_TOLERANCE = Decimal("0.01")


class NfeInputError(ValueError):
    """A entrada não pertence ao subconjunto de XML aceito pelo contrato."""


def _tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element if child.tag == f"{{{_NFE_NAMESPACE}}}{name}"]


def _one(element: ET.Element, name: str, context: str, *, required: bool = True) -> ET.Element | None:
    matches = _children(element, name)
    if len(matches) > 1 or (required and len(matches) != 1):
        raise NfeInputError(f"estrutura inválida em {context}/{name}")
    return matches[0] if matches else None


def _text(element: ET.Element, name: str, context: str) -> str:
    child = _one(element, name, context)
    assert child is not None
    value = child.text
    if value is None or not value.strip():
        raise NfeInputError(f"campo obrigatório vazio: {context}/{name}")
    return value.strip()


def _decimal(value: str, context: str, *, max_integer_places: int, max_decimal_places: int) -> Decimal:
    parts = value.split(".")
    if (
        len(parts) > 2
        or not parts[0]
        or not parts[0].isascii()
        or not parts[0].isdigit()
        or len(parts[0]) > max_integer_places
        or (len(parts) == 2 and (not parts[1] or not parts[1].isascii() or not parts[1].isdigit()))
        or (len(parts) == 2 and len(parts[1]) > max_decimal_places)
    ):
        raise NfeInputError(f"valor decimal inválido em {context}")
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise NfeInputError(f"valor decimal inválido em {context}") from error
    if not amount.is_finite() or amount < 0:
        raise NfeInputError(f"valor decimal fora do contrato em {context}")
    return amount


def _money(value: str, context: str) -> Decimal:
    return _decimal(value, context, max_integer_places=11, max_decimal_places=2)


def _optional_money(element: ET.Element, name: str, context: str) -> Decimal:
    if _one(element, name, context, required=False) is None:
        return Decimal("0.00")
    return _money(_text(element, name, context), f"{context}/{name}")


def _calculated_product_value(quantity: Decimal, unit_value: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 50
        return (quantity * unit_value).quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _outside_money_tolerance(declared: Decimal, calculated: Decimal) -> bool:
    return abs(declared - calculated) > _MONEY_TOLERANCE


def _parse_issue_date(ide: ET.Element) -> date:
    if _one(ide, "dhEmi", "ide", required=False) is not None:
        date_text = _text(ide, "dhEmi", "ide")
    else:
        date_text = _text(ide, "dEmi", "ide")
    try:
        if "T" in date_text:
            return datetime.fromisoformat(date_text.replace("Z", "+00:00")).date()
        return date.fromisoformat(date_text)
    except ValueError as error:
        raise NfeInputError("data de emissão fora do formato ISO esperado") from error


def _reject(reason: str, field_path: str | None = None) -> Alert:
    return Alert("XML-INPUT-001", "1.0.0", "error", "document_rejected", reason, field_path, ())


def _schema_reject(error_type: str | None, field_path: str | None) -> Alert:
    return Alert(
        "XML-SCHEMA-001",
        "1.0.0",
        "error",
        "schema_validation_failed",
        "A NF-e não atende ao pacote XSD oficial configurado.",
        field_path,
        (f"schema_package={NFE_SCHEMA_PACKAGE}", f"error_type={error_type or 'xsd_validation'}"),
    )


def analyze_nfe(xml_bytes: bytes, catalog: NcmCatalogSnapshot | None = None) -> AnalysisReport:
    """Analisa XML NF-e em memória; nunca registra nem devolve XML ou identificadores pessoais."""
    if not xml_bytes or len(xml_bytes) > _MAX_XML_BYTES:
        return AnalysisReport(
            ENGINE_CONTRACT_VERSION, "rejected", None, None, None, (_reject("tamanho de XML fora do limite"),)
        )
    try:
        xml_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return AnalysisReport(
            ENGINE_CONTRACT_VERSION, "rejected", None, None, None, (_reject("XML deve estar codificado em UTF-8"),)
        )
    upper_xml = xml_bytes.upper()
    if b"<!DOCTYPE" in upper_xml or b"<!ENTITY" in upper_xml:
        return AnalysisReport(
            ENGINE_CONTRACT_VERSION, "rejected", None, None, None, (_reject("DOCTYPE e entidades XML não são aceitos"),)
        )
    try:
        root = ET.fromstring(xml_bytes)
    except (ET.ParseError, ValueError):
        return AnalysisReport(ENGINE_CONTRACT_VERSION, "rejected", None, None, None, (_reject("XML malformado"),))

    if not isinstance(root.tag, str) or not root.tag.startswith(f"{{{_NFE_NAMESPACE}}}"):
        return AnalysisReport(
            ENGINE_CONTRACT_VERSION, "rejected", None, None, None, (_reject("namespace NF-e ausente ou inesperado"),)
        )
    if _tag(root) == "nfeProc":
        nfe = _one(root, "NFe", "nfeProc")
        assert nfe is not None
    elif _tag(root) == "NFe":
        nfe = root
    else:
        return AnalysisReport(
            ENGINE_CONTRACT_VERSION, "rejected", None, None, None, (_reject("raiz não é NFe nem nfeProc"),)
        )

    schema_result = validate_nfe_schema(xml_bytes)
    if not schema_result.valid:
        return AnalysisReport(
            ENGINE_CONTRACT_VERSION,
            "rejected",
            None,
            None,
            None,
            (_schema_reject(schema_result.error_type, schema_result.field_path),),
        )

    try:
        inf_nfe = _one(nfe, "infNFe", "NFe")
        assert inf_nfe is not None
        if inf_nfe.attrib.get("versao") != "4.00":
            return AnalysisReport(
                ENGINE_CONTRACT_VERSION,
                "rejected",
                None,
                None,
                None,
                (_reject("somente leiaute NF-e 4.00 é aceito", "NFe/infNFe/@versao"),),
            )
        ide = _one(inf_nfe, "ide", "infNFe")
        dets = _children(inf_nfe, "det")
        total = _one(inf_nfe, "total", "infNFe")
        assert ide is not None and total is not None
        model = _text(ide, "mod", "ide")
        if model != "55":
            return AnalysisReport(
                ENGINE_CONTRACT_VERSION,
                "rejected",
                model,
                None,
                None,
                (_reject("somente modelo 55 é aceito", "NFe/infNFe/ide/mod"),),
            )
        invoice_purpose = _text(ide, "finNFe", "ide")
        if invoice_purpose not in {"1", "2", "3", "4"}:
            raise NfeInputError("finNFe fora do domínio esperado em ide/finNFe")
        if not dets or len(dets) > _MAX_ITEMS:
            return AnalysisReport(
                ENGINE_CONTRACT_VERSION,
                "rejected",
                model,
                None,
                None,
                (_reject("quantidade de itens fora do limite", "NFe/infNFe/det"),),
            )
        issue_date = _parse_issue_date(ide)
        total_icms = _one(total, "ICMSTot", "total")
        assert total_icms is not None
        declared_item_totals = {
            field: _money(_text(total_icms, field, "ICMSTot"), f"ICMSTot/{field}")
            for field in ("vProd", "vFrete", "vSeg", "vDesc", "vOutro")
        }
        product_sum = Decimal("0.00")
        item_component_sums = {field: Decimal("0.00") for field in ("vFrete", "vSeg", "vDesc", "vOutro")}
        ncm_codes: list[tuple[str, str]] = []
        item_values: list[tuple[int, Decimal, Decimal, Decimal, Decimal, Decimal]] = []
        for index, det in enumerate(dets, 1):
            prod = _one(det, "prod", f"det[{index}]")
            assert prod is not None
            item_total = _money(_text(prod, "vProd", f"det[{index}]/prod"), f"det[{index}]/prod/vProd")
            commercial_quantity = _decimal(
                _text(prod, "qCom", f"det[{index}]/prod"),
                f"det[{index}]/prod/qCom",
                max_integer_places=11,
                max_decimal_places=4,
            )
            commercial_unit_value = _decimal(
                _text(prod, "vUnCom", f"det[{index}]/prod"),
                f"det[{index}]/prod/vUnCom",
                max_integer_places=11,
                max_decimal_places=10,
            )
            taxable_quantity = _decimal(
                _text(prod, "qTrib", f"det[{index}]/prod"),
                f"det[{index}]/prod/qTrib",
                max_integer_places=11,
                max_decimal_places=4,
            )
            taxable_unit_value = _decimal(
                _text(prod, "vUnTrib", f"det[{index}]/prod"),
                f"det[{index}]/prod/vUnTrib",
                max_integer_places=11,
                max_decimal_places=10,
            )
            total_indicator = _text(prod, "indTot", f"det[{index}]/prod")
            if total_indicator not in {"0", "1"}:
                raise NfeInputError(f"indTot fora do domínio esperado em det[{index}]/prod/indTot")
            if total_indicator == "1":
                product_sum += item_total
            for field in item_component_sums:
                item_component_sums[field] += _optional_money(prod, field, f"det[{index}]/prod")
            item_values.append(
                (
                    index,
                    item_total,
                    commercial_quantity,
                    commercial_unit_value,
                    taxable_quantity,
                    taxable_unit_value,
                )
            )
            code = _text(prod, "NCM", f"det[{index}]/prod")
            if not code.isascii() or not code.isdigit() or len(code) != 8:
                raise NfeInputError(f"NCM fora do padrão de oito dígitos em det[{index}]/prod/NCM")
            ncm_codes.append((code, f"NFe/infNFe/det[{index}]/prod/NCM"))
    except NfeInputError as error:
        return AnalysisReport(ENGINE_CONTRACT_VERSION, "rejected", "55", None, None, (_reject(str(error)),))

    alerts: list[Alert] = []
    if invoice_purpose == "1":
        for (
            index,
            item_total,
            commercial_quantity,
            commercial_unit_value,
            taxable_quantity,
            taxable_unit_value,
        ) in item_values:
            commercial_calculated = _calculated_product_value(commercial_quantity, commercial_unit_value)
            if _outside_money_tolerance(item_total, commercial_calculated):
                alerts.append(
                    Alert(
                        "NFE-ITEM-VPROD-COM-001",
                        "1.0.0",
                        "warning",
                        "commercial_product_value_mismatch",
                        "vProd diverge de qCom multiplicado por vUnCom além da tolerância oficial.",
                        f"NFe/infNFe/det[{index}]/prod/vProd",
                        (
                            f"valor_declarado={item_total:.2f}",
                            f"valor_calculado={commercial_calculated:.2f}",
                            f"tolerancia={_MONEY_TOLERANCE:.2f}",
                        ),
                    )
                )
            taxable_calculated = _calculated_product_value(taxable_quantity, taxable_unit_value)
            if _outside_money_tolerance(item_total, taxable_calculated):
                alerts.append(
                    Alert(
                        "NFE-ITEM-VPROD-TRIB-001",
                        "1.0.0",
                        "warning",
                        "taxable_product_value_mismatch",
                        "vProd diverge de qTrib multiplicado por vUnTrib além da tolerância oficial.",
                        f"NFe/infNFe/det[{index}]/prod/vProd",
                        (
                            f"valor_declarado={item_total:.2f}",
                            f"valor_calculado={taxable_calculated:.2f}",
                            f"tolerancia={_MONEY_TOLERANCE:.2f}",
                        ),
                    )
                )
    if product_sum != declared_item_totals["vProd"]:
        alerts.append(
            Alert(
                "NFE-TOTAL-PROD-001",
                "1.0.0",
                "warning",
                "product_total_mismatch",
                "A soma de vProd dos itens diverge de ICMSTot/vProd.",
                "NFe/infNFe/total/ICMSTot/vProd",
                (f"soma_dos_itens={product_sum:.2f}", f"total_declarado={declared_item_totals['vProd']:.2f}"),
            )
        )

    total_rules = (
        ("vFrete", "NFE-TOTAL-FRETE-001", "freight_total_mismatch", "frete"),
        ("vSeg", "NFE-TOTAL-SEGURO-001", "insurance_total_mismatch", "seguro"),
        ("vDesc", "NFE-TOTAL-DESCONTO-001", "discount_total_mismatch", "desconto"),
        ("vOutro", "NFE-TOTAL-OUTRO-001", "other_total_mismatch", "outras despesas"),
    )
    for field, rule_id, code, label in total_rules:
        item_sum = item_component_sums[field]
        declared_total = declared_item_totals[field]
        if item_sum != declared_total:
            alerts.append(
                Alert(
                    rule_id,
                    "1.0.0",
                    "warning",
                    code,
                    f"A soma de {field} dos itens diverge do total de {label} em ICMSTot.",
                    f"NFe/infNFe/total/ICMSTot/{field}",
                    (f"soma_dos_itens={item_sum:.2f}", f"total_declarado={declared_total:.2f}"),
                )
            )

    if catalog is not None:
        if issue_date != catalog.source_as_of:
            alerts.append(
                Alert(
                    "NCM-COVERAGE-001",
                    "1.0.0",
                    "info",
                    "ncm_coverage_unavailable",
                    "O snapshot NCM cobre somente source_as_of; nenhuma conclusão temporal foi feita.",
                    None,
                    (
                        f"data_emissao={issue_date.isoformat()}",
                        f"catalogo_source_as_of={catalog.source_as_of.isoformat()}",
                        f"catalogo_release_id={catalog.release_id}",
                    ),
                )
            )
        else:
            for code, path in ncm_codes:
                if code not in catalog.code_digits:
                    alerts.append(
                        Alert(
                            "NCM-MEMBERSHIP-001",
                            "1.0.0",
                            "warning",
                            "ncm_not_in_snapshot",
                            "O código NCM não consta no snapshot fornecido; confirme a classificação na fonte oficial.",
                            path,
                            (
                                f"catalogo_release_id={catalog.release_id}",
                                f"catalogo_sha256={catalog.snapshot_sha256}",
                                f"source_as_of={catalog.source_as_of.isoformat()}",
                            ),
                        )
                    )
    return AnalysisReport(
        ENGINE_CONTRACT_VERSION, "analyzed", "55", issue_date, catalog.release_id if catalog else None, tuple(alerts)
    )
