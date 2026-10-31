"""Captura, quarentena e versionamento local do catalogo IBS/CBS."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import Any, Protocol

from contai_tax_data.ibs_cbs import (
    IBS_CBS_CONTRACT_VERSION,
    IBS_CBS_SOURCE_URL,
    IbsCbsContractError,
    IbsCbsQualityError,
    ibs_cbs_release_id,
    ibs_cbs_snapshot,
    parse_ibs_cbs_html,
    validate_ibs_cbs,
)
from contai_tax_data.source import RetrievedArtifact

_SAFE_HEADERS = frozenset(
    {"cache-control", "content-disposition", "content-length", "content-type", "etag", "last-modified"}
)


class IbsCbsSourceClient(Protocol):
    def fetch(self, url: str) -> RetrievedArtifact: ...


@dataclass(frozen=True, slots=True)
class IbsCbsIngestionResult:
    artifact_sha256: str
    release_id: str
    artifact_created: bool
    release_created: bool
    cst_count: int
    classification_count: int
    annex_link_count: int
    added: int
    changed: int
    removed: int


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_once(path: Path, body: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(body)
    except FileExistsError:
        if path.read_bytes() != body:
            raise RuntimeError(f"colisao no caminho imutavel {path}") from None
        return False
    return True


def _write_pointer(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
            temporary_name = stream.name
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _current_release(root: Path) -> str | None:
    pointer = root / "state" / "ibs-cbs-current.json"
    if not pointer.exists():
        return None
    try:
        value = json.loads(pointer.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ValueError("ponteiro local IBS/CBS invalido") from None
    release_id = value.get("release_id") if isinstance(value, dict) else None
    return release_id if isinstance(release_id, str) else None


def _release_records(body: bytes) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for line in body.decode("utf-8").splitlines():
        value = json.loads(line)
        record_type = value["record_type"]
        if record_type == "cst":
            key = f"cst:{value['Cst']}"
        elif record_type == "cclasstrib":
            key = f"class:{value['CodClassTrib']}"
        else:
            key = f"annex:{value['cclasstrib_code']}:{value['source_record_id']}"
        records[key] = value
    return records


def ingest_ibs_cbs_artifact(artifact: RetrievedArtifact, output_dir: Path) -> IbsCbsIngestionResult:
    root = output_dir.resolve()
    digest = hashlib.sha256(artifact.body).hexdigest()
    raw_path = root / "artifacts" / "sha256" / digest[:2] / f"{digest}.html"
    artifact_created = _write_once(raw_path, artifact.body)
    headers = {key.lower(): value for key, value in artifact.headers.items()}
    safe_headers = {key: headers[key] for key in sorted(_SAFE_HEADERS) if key in headers}
    captured_at = artifact.captured_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    artifact_manifest = root / "artifacts" / "manifests" / f"{digest}.json"

    try:
        content_type = safe_headers.get("content-type", "").split(";", maxsplit=1)[0].strip().lower()
        if content_type != "text/html":
            raise IbsCbsContractError(f"Content-Type inesperado: {content_type or '(ausente)'}")
        dataset = parse_ibs_cbs_html(artifact.body)
        validate_ibs_cbs(dataset)
        snapshot = ibs_cbs_snapshot(dataset)
    except (IbsCbsContractError, IbsCbsQualityError) as error:
        report = {
            "artifact_sha256": digest,
            "captured_at": captured_at,
            "error": str(error),
            "error_type": type(error).__name__,
            "http_status": artifact.status,
            "raw_path": raw_path.relative_to(root).as_posix(),
            "source_id": "svrs-cff-classificacao-tributaria",
            "status": "rejected",
        }
        _write_once(root / "quarantine" / f"{digest}.json", _json_bytes(report))
        if not artifact_manifest.exists():
            _write_once(
                artifact_manifest,
                _json_bytes(
                    {
                        "artifact_sha256": digest,
                        "captured_at": captured_at,
                        "headers": safe_headers,
                        "http_status": artifact.status,
                        "parser_version": IBS_CBS_CONTRACT_VERSION,
                        "source_id": "svrs-cff-classificacao-tributaria",
                        "status": "rejected",
                    }
                ),
            )
        raise

    release_id = ibs_cbs_release_id(snapshot)
    current = _current_release(root)
    old_path = root / "releases" / f"{current}.jsonl" if current else None
    old_records = _release_records(old_path.read_bytes()) if old_path and old_path.exists() else {}
    new_records = _release_records(snapshot)
    shared = old_records.keys() & new_records.keys()
    added = len(new_records.keys() - old_records.keys())
    removed = len(old_records.keys() - new_records.keys())
    changed = sum(old_records[key] != new_records[key] for key in shared)
    release_path = root / "releases" / f"{release_id}.jsonl"
    release_created = _write_once(release_path, snapshot)
    if release_created:
        _write_once(
            root / "releases" / f"{release_id}.json",
            _json_bytes(
                {
                    "contract_version": IBS_CBS_CONTRACT_VERSION,
                    "release_id": release_id,
                    "artifact_sha256": digest,
                    "snapshot_sha256": hashlib.sha256(snapshot).hexdigest(),
                    "created_at": captured_at,
                    "cst_count": len(dataset.csts),
                    "classification_count": len(dataset.classifications),
                    "annex_link_count": len(dataset.annex_links),
                }
            ),
        )
    if not artifact_manifest.exists():
        _write_once(
            artifact_manifest,
            _json_bytes(
                {
                    "artifact_sha256": digest,
                    "byte_size": len(artifact.body),
                    "captured_at": captured_at,
                    "headers": safe_headers,
                    "http_status": artifact.status,
                    "requested_url": IBS_CBS_SOURCE_URL,
                    "final_url": artifact.final_url,
                    "parser_version": IBS_CBS_CONTRACT_VERSION,
                    "release_id": release_id,
                    "raw_path": raw_path.relative_to(root).as_posix(),
                    "source_id": "svrs-cff-classificacao-tributaria",
                    "status": "accepted",
                }
            ),
        )
    _write_pointer(root / "state" / "ibs-cbs-current.json", _json_bytes({"release_id": release_id}))
    return IbsCbsIngestionResult(
        artifact_sha256=digest,
        release_id=release_id,
        artifact_created=artifact_created,
        release_created=release_created,
        cst_count=len(dataset.csts),
        classification_count=len(dataset.classifications),
        annex_link_count=len(dataset.annex_links),
        added=added,
        changed=changed,
        removed=removed,
    )


def capture_ibs_cbs(output_dir: Path, *, client: IbsCbsSourceClient) -> IbsCbsIngestionResult:
    """Faz apenas um GET manual por captura e preserva artefato e release locais."""
    artifact = client.fetch(IBS_CBS_SOURCE_URL)
    return ingest_ibs_cbs_artifact(artifact, output_dir)
