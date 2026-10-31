"""Captura e arquivamento bruto do Convênio ICMS 142/18 do CONFAZ.

Este módulo não interpreta vigência nem transforma redações compiladas em
registros CEST atuais. Cada observação fica registrada junto ao artefato.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import Protocol

from contai_tax_data.source import RetrievedArtifact

CEST_SOURCE_URL = "https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18"
CEST_CAPTURE_CONTRACT = "confaz-cest-raw-v1"
_SAFE_HEADERS = frozenset({"content-type", "content-length", "etag", "last-modified", "cache-control"})


class CestSourceClient(Protocol):
    def fetch(self, url: str) -> RetrievedArtifact: ...


@dataclass(frozen=True, slots=True)
class CestCaptureResult:
    artifact_sha256: str
    artifact_created: bool
    observation_created: bool
    byte_size: int
    captured_at: str
    raw_path: str


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_once(path: Path, content: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(content)
    except FileExistsError:
        if path.read_bytes() != content:
            raise RuntimeError(f"colisao no caminho imutavel {path}") from None
        return False
    return True


def _write_pointer(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
            temporary_name = stream.name
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def capture_cest_artifact(artifact: RetrievedArtifact, output_dir: Path) -> CestCaptureResult:
    """Armazena resposta oficial sem afirmar que linhas compiladas estão vigentes."""
    if artifact.requested_url != CEST_SOURCE_URL:
        raise ValueError("URL solicitada nao corresponde a fonte CEST cadastrada")
    content_type = artifact.headers.get("content-type", "").split(";", maxsplit=1)[0].strip().lower()
    if not (200 <= artifact.status < 300):
        raise ValueError(f"status HTTP inesperado para CEST: {artifact.status}")
    if content_type != "text/html":
        raise ValueError(f"Content-Type CEST inesperado: {content_type or '(ausente)'}")
    if not artifact.body:
        raise ValueError("artefato CEST vazio")
    try:
        artifact.body.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("artefato CEST nao e UTF-8") from None
    if artifact.captured_at.tzinfo is None:
        raise ValueError("captured_at precisa de timezone")

    root = output_dir.resolve()
    digest = hashlib.sha256(artifact.body).hexdigest()
    captured_at = artifact.captured_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    raw_path = root / "artifacts" / "sha256" / digest[:2] / f"{digest}.html"
    relative_raw_path = raw_path.relative_to(root).as_posix()
    artifact_created = _write_once(raw_path, artifact.body)
    headers = {key.lower(): str(value) for key, value in artifact.headers.items() if key.lower() in _SAFE_HEADERS}
    observation = {
        "artifact_sha256": digest,
        "byte_size": len(artifact.body),
        "captured_at": captured_at,
        "contract_version": CEST_CAPTURE_CONTRACT,
        "final_url": artifact.final_url,
        "http_status": artifact.status,
        "raw_path": relative_raw_path,
        "requested_url": artifact.requested_url,
        "response_headers": headers,
        "source_authority": "CONFAZ",
        "status": "captured_raw_uninterpreted",
    }
    observation_path = root / "artifacts" / "observations" / digest / f"{captured_at.replace(':', '-')}.json"
    observation_created = _write_once(observation_path, _json_bytes(observation))
    _write_pointer(root / "state" / "cest-latest-capture.json", _json_bytes(observation))
    return CestCaptureResult(
        artifact_sha256=digest,
        artifact_created=artifact_created,
        observation_created=observation_created,
        byte_size=len(artifact.body),
        captured_at=captured_at,
        raw_path=relative_raw_path,
    )


def capture_cest(output_dir: Path, *, client: CestSourceClient) -> CestCaptureResult:
    """Faz uma única requisição à página oficial e arquiva a resposta bruta."""
    return capture_cest_artifact(client.fetch(CEST_SOURCE_URL), output_dir)
