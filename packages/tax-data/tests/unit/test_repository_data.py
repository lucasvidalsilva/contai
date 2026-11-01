from __future__ import annotations

import hashlib
import json
from pathlib import Path

from contai_tax_data.cest_candidates import CEST_CANDIDATE_CONTRACT, cest_candidates_jsonl, parse_cest_candidates
from contai_tax_data.federal_law import blocks_jsonl, parse_lc214_blocks, validate_lc214_block_volume
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


def test_versioned_lc214_official_capture_preserves_raw_provenance() -> None:
    root = DATA_ROOT / "laws" / "lc214"
    observation = json.loads((root / "state" / "lc214-latest-capture.json").read_text(encoding="utf-8"))
    artifact = (root / observation["raw_path"]).read_bytes()

    assert hashlib.sha256(artifact).hexdigest() == observation["artifact_sha256"]
    assert observation["artifact_sha256"] == "dc87a43e7a4c293bc3c47817754286438db33a7c42472eb0400258e7707a2bde"
    assert len(artifact) == observation["byte_size"] == 3_095_827
    assert observation["http_status"] == 200
    assert observation["source_authority"] == "Câmara dos Deputados - Legislação Informatizada"
    assert observation["contract_version"] == "camara-law-current-raw-v1"
    assert b"Lei Complementar n\xc2\xba 214" in artifact
    assert not list(root.glob("releases/**"))


def test_versioned_lc214_blocks_reprocess_from_the_official_raw_artifact() -> None:
    root = DATA_ROOT / "laws" / "lc214"
    current = json.loads((root / "state" / "lc214-latest-blocks.json").read_text(encoding="utf-8"))
    raw = (root / "artifacts" / "sha256" / "dc" / f"{current['artifact_sha256']}.html").read_bytes()
    snapshot_path = root / current["snapshot_path"]
    snapshot = snapshot_path.read_bytes()
    blocks = parse_lc214_blocks(raw)
    validate_lc214_block_volume(blocks)

    assert hashlib.sha256(snapshot).hexdigest() == current["snapshot_sha256"]
    assert current["snapshot_sha256"] == "d6eed7211094e706b096c6fd909ea8579c98de5208c17f13ea746397f3c24dea"
    assert current["contract_version"] == "federal-law-block-v3"
    assert current["interpretation_status"] == "not_performed"
    assert len(blocks) == current["block_count"] == 8_793
    assert blocks_jsonl(blocks) == snapshot


def test_versioned_lc214_publication_records_keep_separate_provenance() -> None:
    expected = {
        "original": ("efd06578a4789874fd277c3dbf68d424cd9b4baebc1a853735ec350b692ecd29", 958_783),
        "veto": ("de0fedef4f5c0725fd9a505675c7651b3c72b605466d37649dd368778ff5dc90", 77_738),
        "promulgation": ("554c50ed37f0aadf63bcf401814409fdfa3541b18a4149f67e0a7b0093638d3b", 43_729),
    }

    for record_id, (artifact_sha256, byte_size) in expected.items():
        root = DATA_ROOT / "laws" / "lc214" / "records" / record_id
        observation = json.loads((root / "state" / "latest-capture.json").read_text(encoding="utf-8"))
        artifact = (root / observation["raw_path"]).read_bytes()

        assert observation["source_record_id"] == record_id
        assert observation["contract_version"] == "camara-law-record-raw-v1"
        assert observation["http_status"] == 200
        assert hashlib.sha256(artifact).hexdigest() == observation["artifact_sha256"] == artifact_sha256
        assert len(artifact) == observation["byte_size"] == byte_size
