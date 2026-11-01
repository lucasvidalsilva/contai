"""Captura bruta de lei federal compilada, sem interpretar seu efeito jurídico."""

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

LC_214_SOURCE_URL = "https://www2.camara.leg.br/legin/fed/leicom/2025/leicomplementar-214-16-janeiro-2025-796905-normaatualizada-pl.html"
LC_214_SOURCE_ACT = "Lei Complementar 214/2025 (texto atualizado pela Câmara dos Deputados)"
NORMATIVE_CAPTURE_CONTRACT = "camara-law-current-raw-v1"
LC_214_OFFICIAL_RECORDS = {
    "original": (
        "https://www2.camara.leg.br/legin/fed/leicom/2025/leicomplementar-214-16-janeiro-2025-796905-publicacaooriginal-174141-pl.html",
        "Lei Complementar 214/2025 (publicação original)",
    ),
    "veto": (
        "https://www2.camara.leg.br/legin/fed/leicom/2025/leicomplementar-214-16-janeiro-2025-796905-veto-174147-pl.html",
        "Lei Complementar 214/2025 (mensagem de veto)",
    ),
    "promulgation": (
        "https://www2.camara.leg.br/legin/fed/leicom/2025/leicomplementar-214-16-janeiro-2025-796905-promulgacaodevetos-175784-pl.html",
        "Lei Complementar 214/2025 (promulgação de vetos)",
    ),
}
OFFICIAL_RECORD_CAPTURE_CONTRACT = "camara-law-record-raw-v1"
_SAFE_HEADERS = frozenset({"content-type", "content-length", "etag", "last-modified", "cache-control"})


class NormativeSourceClient(Protocol):
    def fetch(self, url: str) -> RetrievedArtifact: ...


@dataclass(frozen=True, slots=True)
class NormativeCaptureResult:
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


def capture_lc214_artifact(artifact: RetrievedArtifact, output_dir: Path) -> NormativeCaptureResult:
    """Armazena texto atualizado oficial da Câmara por conteúdo, sem interpretar vigência."""
    return _capture_camara_artifact(
        artifact,
        output_dir,
        expected_url=LC_214_SOURCE_URL,
        source_act=LC_214_SOURCE_ACT,
        contract_version=NORMATIVE_CAPTURE_CONTRACT,
        pointer_name="lc214-latest-capture.json",
    )


def capture_lc214(output_dir: Path, *, client: NormativeSourceClient) -> NormativeCaptureResult:
    """Faz uma requisição ao texto oficial compilado da LC 214/2025."""
    return capture_lc214_artifact(client.fetch(LC_214_SOURCE_URL), output_dir)


def capture_lc214_official_record_artifact(
    artifact: RetrievedArtifact, output_dir: Path, *, record_id: str
) -> NormativeCaptureResult:
    """Arquiva uma publicação relacionada à LC 214 referenciada pela ficha oficial da Câmara."""
    if record_id not in LC_214_OFFICIAL_RECORDS:
        raise ValueError("identificador de publicação oficial LC 214 desconhecido")
    source_url, source_act = LC_214_OFFICIAL_RECORDS[record_id]
    return _capture_camara_artifact(
        artifact,
        output_dir,
        expected_url=source_url,
        source_act=source_act,
        contract_version=OFFICIAL_RECORD_CAPTURE_CONTRACT,
        pointer_name="latest-capture.json",
        record_id=record_id,
    )


def capture_lc214_official_records(
    output_dir: Path, *, client: NormativeSourceClient
) -> dict[str, NormativeCaptureResult]:
    """Captura texto original, veto e promulgação sem consolidar seus efeitos jurídicos."""
    return {
        record_id: capture_lc214_official_record_artifact(
            client.fetch(source_url), output_dir / "records" / record_id, record_id=record_id
        )
        for record_id, (source_url, _source_act) in LC_214_OFFICIAL_RECORDS.items()
    }


def _capture_camara_artifact(
    artifact: RetrievedArtifact,
    output_dir: Path,
    *,
    expected_url: str,
    source_act: str,
    contract_version: str,
    pointer_name: str,
    record_id: str | None = None,
) -> NormativeCaptureResult:
    if artifact.requested_url != expected_url:
        raise ValueError("URL solicitada não corresponde à fonte oficial cadastrada")
    if artifact.final_url != expected_url:
        raise ValueError("URL final redirecionou para fora da fonte oficial cadastrada")
    if not 200 <= artifact.status < 300:
        raise ValueError(f"status HTTP inesperado para fonte oficial: {artifact.status}")
    content_type = artifact.headers.get("content-type", "").split(";", maxsplit=1)[0].strip().lower()
    if content_type != "text/html":
        raise ValueError(f"Content-Type da fonte oficial inesperado: {content_type or '(ausente)'}")
    if "charset=utf-8" not in artifact.headers.get("content-type", "").lower().replace(" ", ""):
        raise ValueError("charset da fonte oficial inesperado; esperado UTF-8")
    if not artifact.body:
        raise ValueError("artefato oficial vazio")
    if artifact.captured_at.tzinfo is None:
        raise ValueError("captured_at precisa de timezone")

    root = output_dir.resolve()
    digest = hashlib.sha256(artifact.body).hexdigest()
    captured_at = artifact.captured_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    raw_path = root / "artifacts" / "sha256" / digest[:2] / f"{digest}.html"
    relative_raw_path = raw_path.relative_to(root).as_posix()
    artifact_created = _write_once(raw_path, artifact.body)
    safe_headers = {key.lower(): str(value) for key, value in artifact.headers.items() if key.lower() in _SAFE_HEADERS}
    observation = {
        "artifact_sha256": digest,
        "byte_size": len(artifact.body),
        "captured_at": captured_at,
        "contract_version": contract_version,
        "final_url": artifact.final_url,
        "http_status": artifact.status,
        "raw_path": relative_raw_path,
        "requested_url": artifact.requested_url,
        "response_headers": safe_headers,
        "source_act": source_act,
        "source_authority": "Câmara dos Deputados - Legislação Informatizada",
        "status": "captured_raw_unparsed",
    }
    if record_id is not None:
        observation["source_record_id"] = record_id
    observation_path = root / "artifacts" / "observations" / digest / f"{captured_at.replace(':', '-')}.json"
    observation_created = _write_once(observation_path, _json_bytes(observation))
    _write_pointer(root / "state" / pointer_name, _json_bytes(observation))
    return NormativeCaptureResult(
        artifact_sha256=digest,
        artifact_created=artifact_created,
        observation_created=observation_created,
        byte_size=len(artifact.body),
        captured_at=captured_at,
        raw_path=relative_raw_path,
    )
