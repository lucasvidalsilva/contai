from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from contai_fiscal_engine import NcmCatalogSnapshot, analyze_nfe

FIXTURE = Path(__file__).parent / "fixtures" / "nfe-synthetic-55.xml"
XML = FIXTURE.read_bytes()
HASH = "a" * 64


def catalog(*codes: str, source_as_of: date = date(2026, 11, 2)) -> NcmCatalogSnapshot:
    return NcmCatalogSnapshot(HASH, "b" * 64, source_as_of, frozenset(codes))


def test_synthetic_nfe_55_is_analyzed_with_matching_catalog() -> None:
    report = analyze_nfe(XML, catalog("01012100"))

    assert report.status == "analyzed"
    assert report.document_model == "55"
    assert report.issue_date == date(2026, 11, 2)
    assert report.ncm_release_id == HASH
    assert report.alerts == ()
    assert analyze_nfe(XML, catalog("01012100")) == report


def test_item_product_total_divergence_has_rule_and_evidence() -> None:
    mismatched = XML.replace(b">10.00</vProd></ICMSTot>", b">11.00</vProd></ICMSTot>")

    (alert,) = analyze_nfe(mismatched).alerts

    assert alert.rule_id == "NFE-TOTAL-PROD-001"
    assert alert.evidence == ("soma_dos_itens=10.00", "total_declarado=11.00")


def test_catalog_miss_is_an_advisory_with_release_provenance() -> None:
    (alert,) = analyze_nfe(XML, catalog("01012999")).alerts

    assert alert.code == "ncm_not_in_snapshot"
    assert "catalogo_release_id=" + HASH in alert.evidence
    assert "catalogo_sha256=" + "b" * 64 in alert.evidence


def test_historical_issue_date_does_not_claim_catalog_absence() -> None:
    report = analyze_nfe(XML, catalog("01012999", source_as_of=date(2026, 11, 1)))

    assert [alert.code for alert in report.alerts] == ["ncm_coverage_unavailable"]


@pytest.mark.parametrize(
    ("xml", "code"),
    [
        (b"<NFe>", "document_rejected"),
        (b'<!DOCTYPE NFe [<!ENTITY x "boom">]><NFe>&x;</NFe>', "document_rejected"),
        (XML.decode().encode("utf-16"), "document_rejected"),
        (b"<Other/>", "document_rejected"),
        (XML.replace(b' xmlns="http://www.portalfiscal.inf.br/nfe"', b""), "document_rejected"),
        (XML.replace(b"<mod>55</mod>", b"<mod>65</mod>"), "document_rejected"),
        (XML.replace(b'versao="4.00"', b'versao="3.10"'), "document_rejected"),
    ],
)
def test_rejects_malformed_unsafe_or_unsupported_xml(xml: bytes, code: str) -> None:
    report = analyze_nfe(xml)

    assert report.status == "rejected"
    assert report.alerts[0].code == code


def test_rejects_input_over_size_limit() -> None:
    report = analyze_nfe(XML + b" " * 2_000_000)

    assert report.status == "rejected"
    assert report.alerts[0].field_path is None


def test_invalid_catalog_hash_is_rejected_at_contract_boundary() -> None:
    with pytest.raises(ValueError, match="release_id"):
        NcmCatalogSnapshot("bad", "b" * 64, date(2026, 11, 2), frozenset())
