import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from contai_tax_data.normative_capture import (
    LC_214_OFFICIAL_RECORDS,
    LC_214_SOURCE_URL,
    capture_lc214_artifact,
    capture_lc214_official_records,
)
from contai_tax_data.source import RetrievedArtifact


def _artifact(
    *,
    body: bytes = b"<html><title>LC 214</title></html>",
    url: str = LC_214_SOURCE_URL,
    final_url: str | None = None,
    content_type: str = "text/html; charset=utf-8",
    status: int = 200,
) -> RetrievedArtifact:
    return RetrievedArtifact(
        requested_url=url,
        final_url=final_url or url,
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
        (_artifact(final_url="https://example.invalid/redirected.html"), "URL final"),
        (_artifact(content_type="application/json"), "Content-Type"),
        (_artifact(content_type="text/html; charset=iso-8859-1"), "charset"),
        (_artifact(status=403), "status HTTP"),
        (_artifact(body=b""), "vazio"),
    ],
)
def test_unexpected_response_is_rejected(tmp_path: Path, artifact: RetrievedArtifact, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        capture_lc214_artifact(artifact, tmp_path)


def test_related_official_records_are_captured_separately_and_idempotently(tmp_path: Path) -> None:
    class Client:
        def __init__(self) -> None:
            self.requested_urls: list[str] = []

        def fetch(self, url: str) -> RetrievedArtifact:
            self.requested_urls.append(url)
            return _artifact(url=url, body=url.encode())

    client = Client()
    first = capture_lc214_official_records(tmp_path, client=client)
    second = capture_lc214_official_records(tmp_path, client=client)

    assert set(first) == set(second) == set(LC_214_OFFICIAL_RECORDS)
    assert len(client.requested_urls) == 2 * len(LC_214_OFFICIAL_RECORDS)
    assert all(first[key].artifact_sha256 == second[key].artifact_sha256 for key in first)
    assert all(not second[key].artifact_created and not second[key].observation_created for key in second)
    for record_id in LC_214_OFFICIAL_RECORDS:
        pointer = json.loads(
            (tmp_path / "records" / record_id / "state" / "latest-capture.json").read_text(encoding="utf-8")
        )
        assert pointer["source_record_id"] == record_id
        assert pointer["contract_version"] == "camara-law-record-raw-v1"
        assert pointer["source_authority"] == "Câmara dos Deputados - Legislação Informatizada"
