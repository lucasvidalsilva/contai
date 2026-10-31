from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

import pytest

from contai_tax_data.source import FetchError, SourceClient, TransportResponse


class SequenceTransport:
    def __init__(self, outcomes: list[TransportResponse | Exception]) -> None:
        self.outcomes = outcomes
        self.calls = 0

    def get(self, url: str, headers: Mapping[str, str], timeout_seconds: float) -> TransportResponse:
        del url, headers, timeout_seconds
        outcome = self.outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def response(status: int, *, headers: Mapping[str, str] | None = None, body: bytes = b"{}") -> TransportResponse:
    return TransportResponse(status=status, headers=headers or {}, body=body, final_url="https://example.test/final")


def test_timeout_is_retried_and_reported_as_unavailable() -> None:
    transport = SequenceTransport([TimeoutError("lento"), TimeoutError("lento")])
    sleeps: list[float] = []
    client = SourceClient(
        attempts=2,
        timeout_seconds=0.1,
        base_delay_seconds=0.01,
        transport=transport,
        sleep=sleeps.append,
        jitter=lambda _start, _end: 0.0,
    )

    with pytest.raises(FetchError, match=r"apos 2 tentativa\(s\)"):
        client.fetch("https://example.test/ncm")

    assert transport.calls == 2
    assert sleeps == [0.01]


def test_retry_after_is_respected_before_success() -> None:
    transport = SequenceTransport(
        [
            response(503, headers={"retry-after": "2"}, body=b"indisponivel"),
            response(200, headers={"content-type": "application/json"}),
        ]
    )
    sleeps: list[float] = []
    now = datetime(2026, 10, 30, tzinfo=UTC)
    client = SourceClient(
        attempts=2,
        transport=transport,
        sleep=sleeps.append,
        jitter=lambda _start, _end: 0.0,
        now=lambda: now,
    )

    artifact = client.fetch("https://example.test/ncm")

    assert artifact.status == 200
    assert sleeps == [2.0]


def test_permanent_http_error_is_not_retried() -> None:
    transport = SequenceTransport([response(404)])
    client = SourceClient(attempts=3, transport=transport, sleep=lambda _delay: None)

    with pytest.raises(FetchError, match="HTTP 404"):
        client.fetch("https://example.test/ncm")

    assert transport.calls == 1
