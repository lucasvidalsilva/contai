"""Arquivo local imutavel e releases NCM identificadas por conteudo."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from contai_tax_data.ncm import (
    DEFAULT_QUALITY_POLICY,
    NCM_CONTRACT_VERSION,
    NCM_SOURCE_SCHEMA_VERSION,
    NcmContractError,
    NcmQualityError,
    QualityPolicy,
    parse_ncm_json,
    validate_ncm,
)
from contai_tax_data.source import RetrievedArtifact

_SAFE_RESPONSE_HEADERS = frozenset(
    {"cache-control", "content-disposition", "content-length", "content-type", "etag", "last-modified"}
)


@dataclass(frozen=True, slots=True)
class ReleaseDiff:
    added: int
    changed: int
    removed: int


@dataclass(frozen=True, slots=True)
class IngestionResult:
    artifact_sha256: str
    release_id: str
    artifact_created: bool
    release_created: bool
    diff: ReleaseDiff
    entry_count: int
    leaf_count: int


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _write_once(path: Path, content: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(content)
    except FileExistsError:
        if path.read_bytes() != content:
            raise RuntimeError(f"colisao de conteudo no caminho imutavel {path}") from None
        return False
    return True


def _write_atomic_if_changed(path: Path, content: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == content:
        return False
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
    return True


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _timestamp(artifact: RetrievedArtifact) -> str:
    return artifact.captured_at.isoformat().replace("+00:00", "Z")


def _headers(artifact: RetrievedArtifact) -> dict[str, str]:
    lowered = {key.lower(): value for key, value in artifact.headers.items()}
    return {key: lowered[key] for key in sorted(_SAFE_RESPONSE_HEADERS) if key in lowered}


def _artifact_paths(root: Path, artifact_sha256: str) -> tuple[Path, Path]:
    raw = root / "artifacts" / "sha256" / artifact_sha256[:2] / f"{artifact_sha256}.json"
    manifest = root / "artifacts" / "manifests" / f"{artifact_sha256}.json"
    return raw, manifest


def _index_jsonl(content: bytes) -> dict[str, dict[str, Any]]:
    records = [json.loads(line) for line in content.decode().splitlines() if line]
    return {str(record["code"]): record for record in records}


def _diff(previous: bytes | None, current: bytes) -> ReleaseDiff:
    current_records = _index_jsonl(current)
    if previous is None:
        return ReleaseDiff(added=len(current_records), changed=0, removed=0)
    previous_records = _index_jsonl(previous)
    added = current_records.keys() - previous_records.keys()
    removed = previous_records.keys() - current_records.keys()
    common = current_records.keys() & previous_records.keys()
    changed = sum(current_records[code] != previous_records[code] for code in common)
    return ReleaseDiff(added=len(added), changed=changed, removed=len(removed))


def _current_release(root: Path) -> str | None:
    pointer = root / "state" / "ncm-current.json"
    if not pointer.exists():
        return None
    value = json.loads(pointer.read_text(encoding="utf-8"))
    release_id = value.get("release_id")
    return release_id if isinstance(release_id, str) else None


def ingest_ncm_artifact(
    artifact: RetrievedArtifact,
    output_dir: Path,
    *,
    quality_policy: QualityPolicy = DEFAULT_QUALITY_POLICY,
) -> IngestionResult:
    """Arquiva o bruto; rejeita em quarentena ou cria uma release local imutavel."""
    root = output_dir.resolve()
    artifact_sha256 = hashlib.sha256(artifact.body).hexdigest()
    raw_path, artifact_manifest_path = _artifact_paths(root, artifact_sha256)
    artifact_created = _write_once(raw_path, artifact.body)

    try:
        content_type = _headers(artifact).get("content-type", "").split(";", maxsplit=1)[0].strip().lower()
        if content_type != "application/json":
            raise NcmContractError(f"Content-Type inesperado: {content_type or '(ausente)'}")
        dataset = parse_ncm_json(artifact.body)
        validate_ncm(dataset, quality_policy)
    except (NcmContractError, NcmQualityError) as error:
        report = {
            "artifact_sha256": artifact_sha256,
            "captured_at": _timestamp(artifact),
            "error": str(error),
            "error_type": type(error).__name__,
            "raw_path": _relative(raw_path, root),
            "status": "rejected",
        }
        quarantine_path = root / "quarantine" / f"{artifact_sha256}.json"
        if not quarantine_path.exists():
            _write_once(quarantine_path, _json_bytes(report))
        if not artifact_manifest_path.exists():
            _write_once(
                artifact_manifest_path,
                _json_bytes(
                    {
                        **report,
                        "byte_size": len(artifact.body),
                        "final_url": artifact.final_url,
                        "http_status": artifact.status,
                        "requested_url": artifact.requested_url,
                        "response_headers": _headers(artifact),
                    }
                ),
            )
        raise

    snapshot = dataset.snapshot_jsonl()
    release_id = dataset.release_id
    release_dir = root / "releases" / release_id
    snapshot_path = release_dir / "ncm.jsonl"
    release_manifest_path = release_dir / "manifest.json"
    snapshot_created = _write_once(snapshot_path, snapshot)

    release_manifest = {
        "artifact_sha256": artifact_sha256,
        "contract_version": NCM_CONTRACT_VERSION,
        "created_at": _timestamp(artifact),
        "domain": "ncm",
        "entry_count": len(dataset.entries),
        "leaf_count": dataset.leaf_count,
        "release_id": release_id,
        "snapshot_path": _relative(snapshot_path, root),
        "snapshot_sha256": hashlib.sha256(snapshot).hexdigest(),
        "source_act": dataset.source_act,
        "source_as_of": dataset.source_as_of.isoformat(),
        "source_schema_version": NCM_SOURCE_SCHEMA_VERSION,
        "status": "candidate-local",
    }
    if snapshot_created:
        manifest_created = _write_once(release_manifest_path, _json_bytes(release_manifest))
    else:
        if not release_manifest_path.exists():
            raise RuntimeError(f"release local parcial detectada em {release_dir}")
        manifest_created = False
    if snapshot_created != manifest_created:
        raise RuntimeError(f"release local parcial detectada em {release_dir}")
    release_created = snapshot_created

    previous_release = _current_release(root)
    previous_snapshot = None
    if previous_release and previous_release != release_id:
        previous_path = root / "releases" / previous_release / "ncm.jsonl"
        previous_snapshot = previous_path.read_bytes()
    release_diff = _diff(previous_snapshot if previous_release != release_id else snapshot, snapshot)

    pointer = {
        "contract_version": NCM_CONTRACT_VERSION,
        "release_id": release_id,
        "release_manifest": _relative(release_manifest_path, root),
    }
    _write_atomic_if_changed(root / "state" / "ncm-current.json", _json_bytes(pointer))

    artifact_manifest = {
        "artifact_sha256": artifact_sha256,
        "byte_size": len(artifact.body),
        "captured_at": _timestamp(artifact),
        "final_url": artifact.final_url,
        "http_status": artifact.status,
        "parser": f"contai_tax_data.ncm:{NCM_SOURCE_SCHEMA_VERSION}",
        "raw_path": _relative(raw_path, root),
        "release_id": release_id,
        "requested_url": artifact.requested_url,
        "response_headers": _headers(artifact),
        "status": "accepted",
    }
    if not artifact_manifest_path.exists():
        _write_once(artifact_manifest_path, _json_bytes(artifact_manifest))

    return IngestionResult(
        artifact_sha256=artifact_sha256,
        release_id=release_id,
        artifact_created=artifact_created,
        release_created=release_created,
        diff=release_diff,
        entry_count=len(dataset.entries),
        leaf_count=dataset.leaf_count,
    )


def result_as_dict(result: IngestionResult) -> dict[str, object]:
    value = asdict(result)
    value["diff"] = asdict(result.diff)
    return value
