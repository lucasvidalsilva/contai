from __future__ import annotations

import hashlib
import json
from pathlib import Path

from contai_tax_data.cest_candidates import CEST_CANDIDATE_CONTRACT, cest_candidates_jsonl, parse_cest_candidates
from contai_tax_data.postgres import load_local_ibs_cbs_release, load_local_ncm_release, load_local_tipi_release

REPOSITORY_ROOT = Path(__file__).parents[4]
DATA_ROOT = REPOSITORY_ROOT / "data" / "tax-data"


def test_versioned_ncm_snapshot_reprocesses_from_its_original_artifact() -> None:
    release = load_local_ncm_release(DATA_ROOT / "ncm")

    assert len(release.dataset.entries) == 15_157
    assert release.dataset.leaf_count == 10_516


def test_versioned_tipi_snapshot_reprocesses_from_its_original_artifact() -> None:
    release = load_local_tipi_release(DATA_ROOT / "tipi")

    assert len(release.dataset.entries) == 11_103
    assert sum(entry.ex_code is not None for entry in release.dataset.entries) == 582


def test_versioned_ibs_cbs_snapshot_reprocesses_from_its_original_artifact() -> None:
    release = load_local_ibs_cbs_release(DATA_ROOT / "ibs-cbs")

    assert len(release.dataset.csts) == 18
    assert len(release.dataset.classifications) == 173
    assert len(release.dataset.annex_links) == 4_728


def test_versioned_cest_snapshot_is_reproducible_and_remains_unresolved() -> None:
    root = DATA_ROOT / "cest"
    current = json.loads((root / "state" / "cest-latest-candidates.json").read_text(encoding="utf-8"))
    assert current["parser_id"] == CEST_CANDIDATE_CONTRACT
    snapshot_path = root / "candidates" / current["artifact_sha256"] / CEST_CANDIDATE_CONTRACT / "cest-candidates.jsonl"
    snapshot = snapshot_path.read_bytes()
    candidate_manifest = json.loads(snapshot_path.with_name("manifest.json").read_text(encoding="utf-8"))
    observation_root = root / "artifacts" / "observations" / current["artifact_sha256"]
    observation_path = next(observation_root.glob("*.json"))
    observation = json.loads(observation_path.read_text(encoding="utf-8"))
    raw_path = root / observation["raw_path"]
    raw = raw_path.read_bytes()
    records = [json.loads(line) for line in snapshot.decode("utf-8").splitlines()]

    assert hashlib.sha256(raw).hexdigest() == current["artifact_sha256"]
    assert hashlib.sha256(snapshot).hexdigest() == current["candidate_set_sha256"]
    assert candidate_manifest["candidate_count"] == len(records) == 1_569
    assert cest_candidates_jsonl(parse_cest_candidates(raw), current["artifact_sha256"]) == snapshot
    assert all(record["legal_status"] == "unresolved" for record in records)
