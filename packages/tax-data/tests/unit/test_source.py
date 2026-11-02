from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from urllib.request import Request

import pytest

from contai_tax_data.source import (
    ConfazProxyTransport,
    FetchError,
    SourceClient,
    TransportResponse,
    _SameOriginRedirectHandler,
)
from contai_tax_data.tipi import TIPI_ACCEPT, TIPI_SOURCE_URL


class SequenceTransport:
    def __init__(self, outcomes: list[TransportResponse | Exception]) -> None:
        self.outcomes = outcomes
        self.calls = 0
        self.last_url = ""
        self.last_headers: Mapping[str, str] = {}

    def get(self, url: str, headers: Mapping[str, str], timeout_seconds: float) -> TransportResponse:
        del timeout_seconds
        self.last_url = url
        self.last_headers = headers
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


def test_xlsx_source_accept_header_is_explicit() -> None:
    transport = SequenceTransport([response(200, headers={"content-type": "application/octet-stream"}, body=b"PK")])
    client = SourceClient(accept=TIPI_ACCEPT, attempts=1, transport=transport)

    artifact = client.fetch(TIPI_SOURCE_URL)

    assert artifact.body == b"PK"
    assert transport.last_headers["Accept"] == TIPI_ACCEPT


def test_confaz_proxy_routes_only_allowlisted_host_and_restores_source_url() -> None:
    proxy_transport = SequenceTransport(
        [TransportResponse(200, {"content-type": "text/html"}, b"html", "https://proxy.test/api/buscar")]
    )
    direct_transport = SequenceTransport([response(200)])
    transport = ConfazProxyTransport(
        "https://proxy.test/api/buscar",
        "private-key",
        direct_transport=direct_transport,
        proxy_transport=proxy_transport,
    )
    source_url = "https://www.confaz.fazenda.gov.br/sitemap.xml.gz"

    result = transport.get(source_url, {"Accept": "application/gzip"}, 10)
    other_result = transport.get("https://example.test/file", {"Accept": "application/json"}, 10)

    assert (
        proxy_transport.last_url
        == "https://proxy.test/api/buscar?url=https%3A%2F%2Fwww.confaz.fazenda.gov.br%2Fsitemap.xml.gz"
    )
    assert proxy_transport.last_headers["x-chave"] == "private-key"
    assert result.final_url == source_url
    assert result.body == b"html"
    assert direct_transport.last_url == "https://example.test/file"
    assert other_result.final_url == "https://example.test/final"


def test_confaz_proxy_requires_both_settings_only_for_confaz() -> None:
    transport = ConfazProxyTransport(
        "https://proxy.test/api/buscar", None, direct_transport=SequenceTransport([response(200)])
    )

    with pytest.raises(ValueError, match="devem ser configuradas em conjunto"):
        transport.get("https://www.confaz.fazenda.gov.br/sitemap.xml.gz", {}, 10)


def test_confaz_proxy_requires_https_endpoint_without_userinfo_or_query() -> None:
    transport = ConfazProxyTransport("http://proxy.test/api/buscar?token=unsafe", "private-key")

    with pytest.raises(ValueError, match="URL HTTPS"):
        transport.get("https://www.confaz.fazenda.gov.br/sitemap.xml.gz", {}, 10)


def test_proxy_authentication_redirect_cannot_leave_proxy_origin() -> None:
    handler = _SameOriginRedirectHandler(("https", "proxy.test", None))
    request = Request("https://proxy.test/api/buscar")

    assert handler.redirect_request(request, None, 302, "Found", {}, "https://attacker.test/steal") is None
    assert handler.redirect_request(request, None, 302, "Found", {}, "https://proxy.test/next") is not None
