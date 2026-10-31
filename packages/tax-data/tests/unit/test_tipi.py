from __future__ import annotations

from io import BytesIO

import pytest
from openpyxl import Workbook

from contai_tax_data.tipi import TipiContractError, TipiQualityError, parse_tipi_xlsx, tipi_release_id, validate_tipi


def workbook_bytes(
    *,
    changed: bool = False,
    bad_header: bool = False,
    source_act: str = "Atualizações: Ato Declaratório Executivo RFB nº 1/2026",
) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Aprovada pelo Decreto nº 11.158/2022", None, None, None])
    sheet.append([source_act, None, None, None])
    sheet.append(["NCM", "EX" if not bad_header else "Exceção", "DESCRIÇÃO", "ALÍQUOTA (%)"])
    sheet.append(["0101.21.00", None, "-- Reprodutores de raça pura", "NT"])
    sheet.append(["0201.10.00", None, "- Carcaças e meias-carcaças", 0])
    sheet.append(["0210.91.00", "Ex 01", "Miudezas; farinhas e pós dessas miudezas", "NT"])
    if changed:
        sheet.append(["9706.10.00", None, "- Com mais de 250 anos", "NT"])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_parses_official_xlsx_fields_and_exceptions() -> None:
    dataset = parse_tipi_xlsx(workbook_bytes())

    assert len(dataset.entries) == 3
    assert dataset.source_act == (
        "Aprovada pelo Decreto nº 11.158/2022\n\nAtualizações: Ato Declaratório Executivo RFB nº 1/2026"
    )
    assert dataset.entries[0].ncm_code == "0101.21.00"
    assert dataset.entries[0].ipi_rate == "NT"
    assert next(entry for entry in dataset.entries if entry.ncm_code == "0201.10.00").ipi_rate == "0"
    assert next(entry for entry in dataset.entries if entry.ncm_code == "0210.91.00").ex_code == "01"


def test_schema_change_is_rejected() -> None:
    with pytest.raises(TipiContractError, match="cabeçalho"):
        parse_tipi_xlsx(workbook_bytes(bad_header=True))


def test_invalid_xlsx_is_rejected() -> None:
    with pytest.raises(TipiContractError, match="XLSX inválido"):
        parse_tipi_xlsx(b"not an xlsx file")


def test_quality_thresholds_are_explicit() -> None:
    dataset = parse_tipi_xlsx(workbook_bytes())

    with pytest.raises(TipiQualityError, match="volume TIPI"):
        validate_tipi(dataset, minimum_entries=4, maximum_entries=8, minimum_ex_entries=1)
    validate_tipi(dataset, minimum_entries=3, maximum_entries=3, minimum_ex_entries=1)


def test_semantic_release_identity_includes_source_act() -> None:
    original = parse_tipi_xlsx(workbook_bytes())
    changed = parse_tipi_xlsx(workbook_bytes(source_act="Atualizações: ADE RFB 1/2026"))

    assert tipi_release_id(original) != tipi_release_id(changed)
