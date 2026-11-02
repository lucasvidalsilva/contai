"""Cliente HTTP pequeno, limitado e testavel para fontes publicas."""

from __future__ import annotations

import os
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

NCM_SOURCE_URL = "https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json"
USER_AGENT = "contAI-tax-data/0.1 (fonte publica; contato via repositorio contAI)"
_TRANSIENT_HTTP_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
_CONFAZ_HOST = "www.confaz.fazenda.gov.br"


def _origin(url: str) -> tuple[str, str, int | None]:
    parsed = urlsplit(url)
    return parsed.scheme.lower(), (parsed.hostname or "").lower(), parsed.port


class _SameOriginRedirectHandler(HTTPRedirectHandler):
    """Impede que o header de autenticação do proxy siga para outro host."""

    def __init__(self, allowed_origin: tuple[str, str, int | None]) -> None:
        super().__init__()
        self._allowed_origin = allowed_origin

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        if _origin(newurl) != self._allowed_origin:
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclass(frozen=True, slots=True)
class TransportResponse:
    """Resposta reduzida para manter transporte e politica de retry separados."""

    status: int
    headers: Mapping[str, str]
    body: bytes
    final_url: str


class Transport(Protocol):
    def get(self, url: str, headers: Mapping[str, str], timeout_seconds: float) -> TransportResponse: ...


class UrllibTransport:
    """Transporte padrao baseado apenas na biblioteca-padrao."""

    def __init__(self, *, redirect_origin: tuple[str, str, int | None] | None = None) -> None:
        self._opener = build_opener(_SameOriginRedirectHandler(redirect_origin)) if redirect_origin else None

    def get(self, url: str, headers: Mapping[str, str], timeout_seconds: float) -> TransportResponse:
        request = Request(url, headers=dict(headers), method="GET")
        try:
            response_context = (
                self._opener.open(request, timeout=timeout_seconds)
                if self._opener
                else urlopen(request, timeout=timeout_seconds)
            )
            with response_context as response:
                return TransportResponse(
                    status=response.status,
                    headers={key.lower(): value for key, value in response.headers.items()},
                    body=response.read(),
                    final_url=response.geturl(),
                )
        except HTTPError as error:
            return TransportResponse(
                status=error.code,
                headers={key.lower(): value for key, value in error.headers.items()},
                body=error.read(),
                final_url=error.geturl(),
            )


class ConfazProxyTransport:
    """Roteia somente URLs oficiais do CONFAZ pelo proxy autenticado opcional."""

    def __init__(
        self,
        proxy_url: str | None,
        proxy_key: str | None,
        *,
        direct_transport: Transport | None = None,
        proxy_transport: Transport | None = None,
    ) -> None:
        self._proxy_url = proxy_url
        self._proxy_key = proxy_key
        self._direct_transport = direct_transport or UrllibTransport()
        origin = _origin(proxy_url) if proxy_url else None
        self._proxy_transport = proxy_transport or UrllibTransport(redirect_origin=origin)

    def get(self, url: str, headers: Mapping[str, str], timeout_seconds: float) -> TransportResponse:
        parsed_source = urlsplit(url)
        if (
            parsed_source.scheme != "https"
            or (parsed_source.hostname or "").lower() != _CONFAZ_HOST
            or parsed_source.port not in (None, 443)
            or parsed_source.username
            or parsed_source.password
        ):
            return self._direct_transport.get(url, headers, timeout_seconds)

        if not self._proxy_url and not self._proxy_key:
            return self._direct_transport.get(url, headers, timeout_seconds)
        if not self._proxy_url or not self._proxy_key:
            raise ValueError("PROXY_BRASIL_URL e PROXY_BRASIL_CHAVE devem ser configuradas em conjunto")

        proxy = urlsplit(self._proxy_url)
        if (
            proxy.scheme != "https"
            or not proxy.hostname
            or proxy.username
            or proxy.password
            or proxy.query
            or proxy.fragment
        ):
            raise ValueError("PROXY_BRASIL_URL deve ser uma URL HTTPS sem credenciais, query ou fragmento")

        proxy_request_url = f"{self._proxy_url}?{urlencode({'url': url})}"
        proxy_headers = {key: value for key, value in headers.items() if key.lower() != "x-chave"}
        proxy_headers["x-chave"] = self._proxy_key
        response = self._proxy_transport.get(proxy_request_url, proxy_headers, timeout_seconds)
        # A resposta do proxy representa o recurso original, não seu endpoint de transporte.
        return TransportResponse(response.status, response.headers, response.body, url)


@dataclass(frozen=True, slots=True)
class RetrievedArtifact:
    requested_url: str
    final_url: str
    status: int
    headers: Mapping[str, str]
    body: bytes
    captured_at: datetime


class FetchError(RuntimeError):
    """Falha depois de esgotar a politica de tentativas."""


def _retry_after_seconds(value: str | None, now: datetime) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        return max(0.0, (retry_at - now).total_seconds())


class SourceClient:
    """GET com timeout, tentativas totais, backoff, jitter e Retry-After."""

    def __init__(
        self,
        *,
        accept: str = "application/json",
        attempts: int = 3,
        timeout_seconds: float = 30.0,
        base_delay_seconds: float = 1.0,
        transport: Transport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if attempts < 1:
            raise ValueError("attempts deve ser positivo")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds deve ser positivo")
        self._attempts = attempts
        self._accept = accept
        self._timeout_seconds = timeout_seconds
        self._base_delay_seconds = base_delay_seconds
        self._transport = transport or ConfazProxyTransport(
            os.environ.get("PROXY_BRASIL_URL"), os.environ.get("PROXY_BRASIL_CHAVE")
        )
        self._sleep = sleep
        self._jitter = jitter
        self._now = now

    def fetch(self, url: str) -> RetrievedArtifact:
        headers = {"Accept": self._accept, "User-Agent": USER_AGENT}
        last_error = "falha desconhecida"
        for attempt in range(1, self._attempts + 1):
            response: TransportResponse | None = None
            try:
                response = self._transport.get(url, headers, self._timeout_seconds)
                if 200 <= response.status < 300:
                    if not response.body:
                        raise OSError("resposta vazia")
                    return RetrievedArtifact(
                        requested_url=url,
                        final_url=response.final_url,
                        status=response.status,
                        headers=response.headers,
                        body=response.body,
                        captured_at=self._now(),
                    )
                last_error = f"HTTP {response.status}"
                retryable = response.status in _TRANSIENT_HTTP_STATUS
            except (OSError, TimeoutError, URLError) as error:
                last_error = f"{type(error).__name__}: {error}"
                retryable = True

            if not retryable or attempt == self._attempts:
                raise FetchError(f"falha ao capturar {url} apos {attempt} tentativa(s): {last_error}")

            now = self._now()
            retry_after = _retry_after_seconds(response.headers.get("retry-after") if response else None, now)
            base_delay = retry_after if retry_after is not None else self._base_delay_seconds * (2 ** (attempt - 1))
            self._sleep(base_delay + self._jitter(0.0, base_delay * 0.25))

        raise AssertionError("loop de tentativas terminou sem resultado")
