from __future__ import annotations

import json
from pathlib import Path

import pytest

from contai_tax_data.federal_law import (
    parse_lc214_blocks,
    validate_lc214_block_volume,
    write_lc214_blocks,
)

REPOSITORY_ROOT = Path(__file__).parents[4]
LC214_ROOT = REPOSITORY_ROOT / "data" / "tax-data" / "laws" / "lc214"


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
    current = json.loads((LC214_ROOT / "state" / "lc214-latest-capture.json").read_text(encoding="utf-8"))
    captured_at = current["captured_at"].replace(":", "-")
    observation_path = LC214_ROOT / "artifacts" / "observations" / current["artifact_sha256"] / f"{captured_at}.json"
    observation = json.loads(observation_path.read_text(encoding="utf-8"))
    raw_path = LC214_ROOT / observation["raw_path"]

    first = write_lc214_blocks(raw_path, observation_path, tmp_path)
    second = write_lc214_blocks(raw_path, observation_path, tmp_path)

    assert first == second
    assert first["block_count"] == 8_793


def test_writer_rejects_a_capture_manifest_from_another_source(tmp_path: Path) -> None:
    current = json.loads((LC214_ROOT / "state" / "lc214-latest-capture.json").read_text(encoding="utf-8"))
    captured_at = current["captured_at"].replace(":", "-")
    observation_path = LC214_ROOT / "artifacts" / "observations" / current["artifact_sha256"] / f"{captured_at}.json"
    observation = json.loads(observation_path.read_text(encoding="utf-8"))
    observation["requested_url"] = "https://example.invalid/law.html"
    wrong_source = tmp_path / "wrong-source.json"
    wrong_source.write_text(json.dumps(observation), encoding="utf-8")
    raw_path = LC214_ROOT / observation["raw_path"]

    with pytest.raises(ValueError, match="observação oficial"):
        write_lc214_blocks(raw_path, wrong_source, tmp_path / "output")


def test_writer_rejects_a_non_object_capture_manifest(tmp_path: Path) -> None:
    raw_path = (
        LC214_ROOT
        / "artifacts"
        / "sha256"
        / "dc"
        / "dc87a43e7a4c293bc3c47817754286438db33a7c42472eb0400258e7707a2bde.html"
    )
    manifest_path = tmp_path / "observation.json"
    manifest_path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="objeto JSON"):
        write_lc214_blocks(raw_path, manifest_path, tmp_path / "output")
