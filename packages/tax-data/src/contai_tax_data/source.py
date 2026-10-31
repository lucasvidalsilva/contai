"""Cliente HTTP pequeno, limitado e testavel para fontes publicas."""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

NCM_SOURCE_URL = "https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json"
USER_AGENT = "contAI-tax-data/0.1 (fonte publica; contato via repositorio contAI)"
_TRANSIENT_HTTP_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


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

    def get(self, url: str, headers: Mapping[str, str], timeout_seconds: float) -> TransportResponse:
        request = Request(url, headers=dict(headers), method="GET")
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
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
        self._transport = transport or UrllibTransport()
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
