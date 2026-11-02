from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from contai_tax_data.federal_law import (
    parse_lc214_blocks,
    validate_lc214_block_volume,
    write_lc214_blocks,
    write_lc214_record_blocks,
)
from contai_tax_data.normative_capture import LC_214_OFFICIAL_RECORDS, OFFICIAL_RECORD_CAPTURE_CONTRACT

LC214_URL = "https://www2.camara.leg.br/legin/fed/leicom/2025/leicomplementar-214-16-janeiro-2025-796905-normaatualizada-pl.html"
AUTHORITY = "C\u00e2mara dos Deputados - Legisla\u00e7\u00e3o Informatizada"


def _capture_fixture(root: Path, raw: bytes, *, requested_url: str, record_id: str | None = None) -> tuple[Path, Path]:
    artifact_hash = hashlib.sha256(raw).hexdigest()
    raw_path = root / "artifacts" / "sha256" / artifact_hash[:2] / f"{artifact_hash}.html"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(raw)
    observation_path = root / "artifacts" / "observations" / artifact_hash / "2026-11-01T00-00-00Z.json"
    observation_path.parent.mkdir(parents=True, exist_ok=True)
    observation = {
        "artifact_sha256": artifact_hash,
        "captured_at": "2026-11-01T00:00:00Z",
        "contract_version": OFFICIAL_RECORD_CAPTURE_CONTRACT if record_id else "camara-law-current-raw-v1",
        "final_url": requested_url,
        "http_status": 200,
        "raw_path": raw_path.relative_to(root).as_posix(),
        "requested_url": requested_url,
        "response_headers": {"content-type": "text/html; charset=utf-8"},
        "source_authority": AUTHORITY,
    }
    if record_id:
        observation["source_record_id"] = record_id
    observation_path.write_text(json.dumps(observation), encoding="utf-8")
    return raw_path, observation_path


def _lc214_volume_fixture() -> bytes:
    paragraphs = [f"<p>Art. {index}. Texto do artigo {index}.</p>" for index in range(1, 582)]
    paragraphs.extend(f"<p>Texto estrutural {index}.</p>" for index in range(8_212))
    return ("<!doctype html><html><body>" + "".join(paragraphs) + "</body></html>").encode("utf-8")


def test_parses_literal_structural_markers_without_assigning_legal_effects() -> None:
    source = """<!doctype html><html><body>
    <p class="article"><b>Art. 7º-A.</b> Texto &amp; continua.</p>
    <p>§ 1º Condição.</p>
    <p>Parágrafo único. Texto.</p>
    <p>I - Primeiro item.</p><p>a) Alínea.</p><p>Nota sem marcador.</p>
    <table><tr><td>Texto direto da tabela.</td><td><p>Parágrafo da célula.</p></td></tr></table>
    </body></html>""".encode()

    blocks = parse_lc214_blocks(source)

    assert [(block.marker_kind, block.marker) for block in blocks] == [
        ("article", "7º-A"),
        ("paragraph", "§ 1"),
        ("sole_paragraph", "Parágrafo único"),
        ("roman_item", "I"),
        ("letter_item", "a"),
        ("text", None),
        ("text", None),
        ("text", None),
    ]
    assert blocks[0].source_class == "article"
    assert blocks[0].source_tag == "p"
    assert blocks[0].text == "Art. 7º-A. Texto & continua."
    assert blocks[-2].source_tag == "td"
    assert blocks[-1].source_tag == "p"


@pytest.mark.parametrize(
    ("source", "message"),
    [(b"<html>\xff</html>", "UTF-8"), (b"<body>texto</body>", "raiz HTML")],
)
def test_rejects_undecodable_or_unrecognized_input(source: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_lc214_blocks(source)


def test_volume_gate_rejects_incomplete_extraction() -> None:
    source = "<html><body><p>Art. 1º Texto.</p></body></html>".encode()
    blocks = parse_lc214_blocks(source)

    with pytest.raises(ValueError, match="contagem inesperada de artigos"):
        validate_lc214_block_volume(blocks)


def test_writer_is_idempotent_from_the_archived_capture(tmp_path: Path) -> None:
    raw_path, observation_path = _capture_fixture(
        tmp_path / "capture", _lc214_volume_fixture(), requested_url=LC214_URL
    )

    first = write_lc214_blocks(raw_path, observation_path, tmp_path)
    second = write_lc214_blocks(raw_path, observation_path, tmp_path)

    assert first == second
    assert first["block_count"] == 8_793


def test_writer_rejects_a_capture_manifest_from_another_source(tmp_path: Path) -> None:
    raw_path, observation_path = _capture_fixture(
        tmp_path / "capture", _lc214_volume_fixture(), requested_url=LC214_URL
    )
    observation = json.loads(observation_path.read_text(encoding="utf-8"))
    observation["requested_url"] = "https://example.invalid/law.html"
    wrong_source = tmp_path / "wrong-source.json"
    wrong_source.write_text(json.dumps(observation), encoding="utf-8")
    with pytest.raises(ValueError, match="observação oficial"):
        write_lc214_blocks(raw_path, wrong_source, tmp_path / "output")


def test_writer_rejects_a_non_object_capture_manifest(tmp_path: Path) -> None:
    raw_path, _ = _capture_fixture(tmp_path / "capture", b"<html><body>fixture</body></html>", requested_url=LC214_URL)
    manifest_path = tmp_path / "observation.json"
    manifest_path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="objeto JSON"):
        write_lc214_blocks(raw_path, manifest_path, tmp_path / "output")


@pytest.mark.parametrize("record_id", ("original", "veto", "promulgation"))
def test_official_linked_records_are_reprocessed_and_match_versioned_snapshots(tmp_path: Path, record_id: str) -> None:
    requested_url, _source_act = LC_214_OFFICIAL_RECORDS[record_id]
    raw_path, observation_path = _capture_fixture(
        tmp_path / f"capture-{record_id}",
        f"<!doctype html><html><body><p>Registro oficial {record_id}.</p></body></html>".encode(),
        requested_url=requested_url,
        record_id=record_id,
    )
    output_root = tmp_path / record_id

    first = write_lc214_record_blocks(record_id, raw_path, observation_path, output_root)
    second = write_lc214_record_blocks(record_id, raw_path, observation_path, output_root)

    assert first == second
    assert first["source_record_id"] == record_id
    assert first["interpretation_status"] == "not_performed"
    assert first["block_count"] > 0
    replay_snapshot = (output_root / first["snapshot_path"]).read_bytes()
    assert hashlib.sha256(replay_snapshot).hexdigest() == first["snapshot_sha256"]


def test_linked_record_writer_rejects_wrong_official_record(tmp_path: Path) -> None:
    requested_url, _source_act = LC_214_OFFICIAL_RECORDS["veto"]
    raw_path, observation_path = _capture_fixture(
        tmp_path / "capture-veto",
        b"<!doctype html><html><body><p>Registro oficial veto.</p></body></html>",
        requested_url=requested_url,
        record_id="veto",
    )

    with pytest.raises(ValueError, match="observação oficial"):
        write_lc214_record_blocks(
            "original",
            raw_path,
            observation_path,
            tmp_path / "output",
        )
