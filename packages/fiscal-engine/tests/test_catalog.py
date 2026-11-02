from __future__ import annotations

import hashlib
import json
from datetime import date

import pytest

from contai_fiscal_engine import NcmCatalogSnapshot, dump_ncm_catalog, load_ncm_catalog

NCM_RELEASE_ID = "a" * 64
NCM_SNAPSHOT_SHA256 = "b" * 64


def snapshot() -> NcmCatalogSnapshot:
    codes = {f"{code:08d}" for code in range(1_000_000, 1_009_000)}
    codes.add("01012100")
    return NcmCatalogSnapshot(
        NCM_RELEASE_ID,
        NCM_SNAPSHOT_SHA256,
        date(2026, 10, 30),
        frozenset(codes),
    )


def test_catalog_round_trip_is_canonical_and_verified() -> None:
    payload = dump_ncm_catalog(snapshot())

    assert load_ncm_catalog(payload) == snapshot()
    assert dump_ncm_catalog(load_ncm_catalog(payload)) == payload
    assert json.loads(payload)["code_count"] == 9_001
    assert "01012100" in json.loads(payload)["code_digits"]


def test_catalog_rejects_projection_inconsistent_with_its_hash() -> None:
    payload = dump_ncm_catalog(snapshot()).replace(b"01012100", b"01013000")

    with pytest.raises(ValueError, match="hash da projeção"):
        load_ncm_catalog(payload)


def test_catalog_dump_rejects_incomplete_projection() -> None:
    empty = NcmCatalogSnapshot(NCM_RELEASE_ID, NCM_SNAPSHOT_SHA256, date(2026, 10, 30), frozenset())

    with pytest.raises(ValueError, match="quantidade de códigos"):
        dump_ncm_catalog(empty)


def test_catalog_load_rejects_internally_consistent_but_incomplete_projection() -> None:
    payload = json.loads(dump_ncm_catalog(snapshot()))
    payload["code_digits"] = ["01012100"]
    payload["code_count"] = 1
    payload["projection_sha256"] = hashlib.sha256(b"01012100\n").hexdigest()

    with pytest.raises(ValueError, match="contagem ou lista"):
        load_ncm_catalog(json.dumps(payload).encode())


@pytest.mark.parametrize("payload", [b"", b"not-json", b"{}"])
def test_catalog_rejects_empty_malformed_or_unknown_schema(payload: bytes) -> None:
    with pytest.raises(ValueError):
        load_ncm_catalog(payload)
