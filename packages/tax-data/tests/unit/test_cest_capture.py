from datetime import UTC, datetime
from pathlib import Path

import pytest

from contai_tax_data.cest_capture import CEST_SOURCE_URL, capture_cest_artifact
from contai_tax_data.source import RetrievedArtifact


def _artifact(
    *,
    body: bytes = b"<html><table><tr><td>CEST</td></tr></table></html>",
    url: str = CEST_SOURCE_URL,
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


def test_capture_archives_raw_and_records_provenance_without_normalizing(tmp_path: Path) -> None:
    artifact = _artifact()

    result = capture_cest_artifact(artifact, tmp_path)

    assert result.artifact_created
    assert result.observation_created
    assert (tmp_path / result.raw_path).read_bytes() == artifact.body
    pointer = (tmp_path / "state" / "cest-latest-capture.json").read_text(encoding="utf-8")
    assert '"status": "captured_raw_uninterpreted"' in pointer
    assert "must-not-be-stored" not in pointer
    assert not list(tmp_path.glob("releases/**"))


def test_repeat_capture_is_idempotent_for_artifact_and_observation(tmp_path: Path) -> None:
    first = capture_cest_artifact(_artifact(), tmp_path)
    second = capture_cest_artifact(_artifact(), tmp_path)

    assert first.artifact_sha256 == second.artifact_sha256
    assert first.artifact_created and first.observation_created
    assert not second.artifact_created and not second.observation_created


@pytest.mark.parametrize(
    ("artifact", "message"),
    [
        (_artifact(url="https://example.invalid/source"), "URL solicitada"),
        (_artifact(content_type="application/json"), "Content-Type"),
        (_artifact(status=503), "status HTTP"),
        (_artifact(body=b"\xff"), "UTF-8"),
    ],
)
def test_unexpected_source_response_is_rejected(tmp_path: Path, artifact: RetrievedArtifact, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        capture_cest_artifact(artifact, tmp_path)
