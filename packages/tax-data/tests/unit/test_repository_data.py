from __future__ import annotations

import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[4]
RUN_INDEX = REPOSITORY_ROOT / "data" / "tax-data" / "latest-runs.json"


def test_data_tracks_only_the_latest_successful_run_for_each_source() -> None:
    index = json.loads(RUN_INDEX.read_text(encoding="utf-8"))
    runs = index["source_workflows"]
    expected_ids = {
        "NCM": 41518822131,
        "TIPI": 41517153762,
        "IBS/CBS": 41517298576,
        "LC 214": 41517823698,
        "CEST": 41528271509,
        "CONFAZ": 41528741312,
    }

    assert {run["source"]: run["run_id"] for run in runs} == expected_ids
    assert all(run["status"] == "success" for run in runs)
    assert all(run["artifact_retention_days"] == 14 for run in runs)
    assert all(run["artifact_expires_at"].startswith("2026-11-16T") for run in runs)
    assert all(run["url"].endswith(f"/runs/{run['run_id']}") for run in runs)


def test_supabase_archive_inventory_discloses_legacy_payload_gap() -> None:
    archive = json.loads(RUN_INDEX.read_text(encoding="utf-8"))["supabase_archive"]

    assert archive["project"] == "contai-dev"
    assert archive["schema"] == "tax_ingest"
    assert archive["metadata_artifacts"] == 35
    assert archive["payloads_archived"] == 34
    assert archive["payload_bytes"] == 20_563_634
    assert archive["missing_payload_sha256"] == "dfae9ea93ddaa01512009739341c38a01dd7a1d2c3e2fdf089f46dbe970d2fb5"
