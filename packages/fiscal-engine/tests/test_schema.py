from __future__ import annotations

from pathlib import Path

from contai_fiscal_engine import analyze_nfe
from contai_fiscal_engine.schema import NFE_SCHEMA_PACKAGE, validate_nfe_schema

FIXTURE = Path(__file__).parent / "fixtures" / "nfe-synthetic-55.xml"
XML = FIXTURE.read_bytes()


def test_synthetic_nfe_conforms_to_vendored_official_schema() -> None:
    result = validate_nfe_schema(XML)

    assert NFE_SCHEMA_PACKAGE == "PL_010g_v1.03"
    assert result.valid is True
    assert result.error_type is None
    assert result.field_path is None


def test_missing_required_field_fails_xsd_before_fiscal_rules() -> None:
    invalid = XML.replace(b"      <natOp>VENDA SINTETICA PARA TESTES</natOp>\n", b"")

    report = analyze_nfe(invalid)

    assert report.status == "rejected"
    (alert,) = report.alerts
    assert alert.rule_id == "XML-SCHEMA-001"
    assert alert.code == "schema_validation_failed"
    assert alert.evidence[0] == "schema_package=PL_010g_v1.03"
    assert alert.evidence[1].startswith("error_type=SCHEMAV_")
    assert "EMITENTE SINTETICO" not in repr(alert)
    assert "00000000000000" not in repr(alert)


def test_schema_validation_is_deterministic() -> None:
    first = validate_nfe_schema(XML)

    assert validate_nfe_schema(XML) == first
