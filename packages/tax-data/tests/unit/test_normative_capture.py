from datetime import UTC, datetime
from pathlib import Path

import pytest

from contai_tax_data.normative_capture import LC_214_SOURCE_URL, capture_lc214_artifact
from contai_tax_data.source import RetrievedArtifact


def _artifact(
    *,
    body: bytes = b"<html><title>LC 214</title></html>",
    url: str = LC_214_SOURCE_URL,
    content_type: str = "text/html; charset=utf-8",
    status: int = 200,
) -> RetrievedArtifact:
    return RetrievedArtifact(
        requested_url=url,
        final_url=url,
        status=status,
        headers={"content-type": content_type, "set-cookie": "must-not-be-stored"},
        body=body,
        captured_at=datetime(2026, 10, 31, 22, 0, tzinfo=UTC),
    )


def test_capture_archives_original_and_records_law_metadata(tmp_path: Path) -> None:
    artifact = _artifact()

    result = capture_lc214_artifact(artifact, tmp_path)

    assert result.artifact_created and result.observation_created
    assert (tmp_path / result.raw_path).read_bytes() == artifact.body
    pointer = (tmp_path / "state" / "lc214-latest-capture.json").read_text(encoding="utf-8")
    assert '"status": "captured_raw_unparsed"' in pointer
    assert '"source_act": "Lei Complementar 214/2025 (texto atualizado pela Câmara dos Deputados)"' in pointer
    assert '"source_authority": "Câmara dos Deputados - Legislação Informatizada"' in pointer
    assert "must-not-be-stored" not in pointer
    assert not list(tmp_path.glob("releases/**"))


def test_same_capture_is_idempotent(tmp_path: Path) -> None:
    first = capture_lc214_artifact(_artifact(), tmp_path)
    second = capture_lc214_artifact(_artifact(), tmp_path)

    assert first.artifact_sha256 == second.artifact_sha256
    assert first.artifact_created and first.observation_created
    assert not second.artifact_created and not second.observation_created


@pytest.mark.parametrize(
    ("artifact", "message"),
    [
        (_artifact(url="https://example.invalid/law"), "URL solicitada"),
        (_artifact(content_type="application/json"), "Content-Type"),
        (_artifact(status=403), "status HTTP"),
        (_artifact(body=b""), "vazio"),
    ],
)
def test_unexpected_response_is_rejected(tmp_path: Path, artifact: RetrievedArtifact, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        capture_lc214_artifact(artifact, tmp_path)
