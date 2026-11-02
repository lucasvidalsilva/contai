from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from contai_fiscal_engine import NcmCatalogSnapshot, dump_ncm_catalog
from contai_fiscal_engine.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "nfe-synthetic-55.xml"
NCM_RELEASE_ID = "a" * 64
NCM_SNAPSHOT_SHA256 = "b" * 64


def complete_test_codes() -> frozenset[str]:
    codes = {f"{code:08d}" for code in range(1_000_000, 1_009_000)}
    codes.add("01012100")
    return frozenset(codes)


def test_cli_analyzes_local_xml_and_emits_stable_json(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([str(FIXTURE)])
    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert exit_code == 0
    assert report["status"] == "analyzed"
    assert report["issue_date"] == "2026-10-30"
    assert report["alerts"] == []


def test_cli_loads_verified_ncm_catalog(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    catalog_path = tmp_path / "ncm-catalog.json"
    catalog_path.write_bytes(
        dump_ncm_catalog(
            NcmCatalogSnapshot(
                NCM_RELEASE_ID,
                NCM_SNAPSHOT_SHA256,
                date(2026, 10, 30),
                complete_test_codes(),
            )
        )
    )

    exit_code = main([str(FIXTURE), "--ncm-catalog", str(catalog_path)])
    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert exit_code == 0
    assert report["ncm_release_id"] == NCM_RELEASE_ID
    assert report["alerts"] == []


def test_cli_rejects_missing_file_without_traceback(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["missing.xml"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert json.loads(captured.err)["error"]
