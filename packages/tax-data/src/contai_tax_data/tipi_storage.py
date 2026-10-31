"""Arquivamento local imutável e releases determinísticas TIPI."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from contai_tax_data.source import RetrievedArtifact
from contai_tax_data.tipi import (
    TIPI_CONTRACT_VERSION,
    TIPI_SOURCE_URL,
    TipiContractError,
    TipiQualityError,
    parse_tipi_xlsx,
    tipi_release_id,
    tipi_snapshot,
    validate_tipi,
)

_TIPI_CONTENT_TYPES = frozenset(
    {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",
        "application/xlsx",
    }
)
_SAFE_HEADERS = frozenset(
    {"cache-control", "content-disposition", "content-length", "content-type", "etag", "last-modified"}
)


class TipiSourceClient(Protocol):
    def fetch(self, url: str) -> RetrievedArtifact: ...


@dataclass(frozen=True, slots=True)
class TipiDiff:
    added: int
    changed: int
    removed: int


@dataclass(frozen=True, slots=True)
class TipiIngestionResult:
    artifact_sha256: str
    release_id: str
    artifact_created: bool
    release_created: bool
    entry_count: int
    ex_count: int
    diff: TipiDiff


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_once(path: Path, content: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(content)
    except FileExistsError:
        if path.read_bytes() != content:
            raise RuntimeError(f"colisão no caminho imutável {path}") from None
        return False
    return True


def _write_if_absent(path: Path, content: bytes) -> bool:
    if path.exists():
        return False
    return _write_once(path, content)


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


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("captured_at precisa de timezone")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _rows_by_key(snapshot: bytes) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for line in snapshot.decode("utf-8").splitlines():
        row = json.loads(line)
        result[(row["ncm_code"], row["ex_code"] or "")] = row
    return result


def _diff(previous: bytes | None, current: bytes) -> TipiDiff:
    if previous is None:
        return TipiDiff(added=len(_rows_by_key(current)), changed=0, removed=0)
    old = _rows_by_key(previous)
    new = _rows_by_key(current)
    shared = old.keys() & new.keys()
    return TipiDiff(
        added=len(new.keys() - old.keys()),
        changed=sum(old[key] != new[key] for key in shared),
        removed=len(old.keys() - new.keys()),
    )


def ingest_tipi_artifact(
    artifact: RetrievedArtifact,
    output_dir: Path,
    *,
    minimum_entries: int = 8_000,
    maximum_entries: int = 14_000,
    minimum_ex_entries: int = 500,
    maximum_missing_rates: int = 10,
) -> TipiIngestionResult:
    root = output_dir.resolve()
    artifact_sha = hashlib.sha256(artifact.body).hexdigest()
    raw_path = root / "artifacts" / "sha256" / f"{artifact_sha}.xlsx"
    raw_created = _write_once(raw_path, artifact.body)
    pointer_path = root / "state" / "tipi-current.json"
    previous_snapshot = None
    if pointer_path.exists():
        previous_id = str(json.loads(pointer_path.read_text(encoding="utf-8"))["release_id"])
        previous_path = root / "releases" / previous_id / "tipi.jsonl"
        if previous_path.exists():
            previous_snapshot = previous_path.read_bytes()
    content_type = artifact.headers.get("content-type", "").split(";", maxsplit=1)[0].strip().lower()
    headers = {key.lower(): str(value) for key, value in artifact.headers.items() if key.lower() in _SAFE_HEADERS}
    try:
        if artifact.requested_url != TIPI_SOURCE_URL:
            raise TipiContractError("URL solicitada não corresponde à fonte TIPI cadastrada")
        if content_type not in _TIPI_CONTENT_TYPES:
            raise TipiContractError(f"Content-Type TIPI inesperado: {content_type or '(ausente)'}")
        dataset = parse_tipi_xlsx(artifact.body)
        validate_tipi(
            dataset,
            minimum_entries=minimum_entries,
            maximum_entries=maximum_entries,
            minimum_ex_entries=minimum_ex_entries,
            maximum_missing_rates=maximum_missing_rates,
        )
    except (TipiContractError, TipiQualityError) as error:
        report = {
            "artifact_sha256": artifact_sha,
            "captured_at": _timestamp(artifact.captured_at),
            "error": str(error),
            "error_type": type(error).__name__,
            "raw_path": raw_path.relative_to(root).as_posix(),
            "status": "rejected",
        }
        _write_once(root / "quarantine" / f"{artifact_sha}.json", _json_bytes(report))
        _write_if_absent(
            root / "artifacts" / "manifests" / f"{artifact_sha}.json",
            _json_bytes(
                {
                    **report,
                    "byte_size": len(artifact.body),
                    "final_url": artifact.final_url,
                    "http_status": artifact.status,
                    "requested_url": artifact.requested_url,
                    "response_headers": headers,
                }
            ),
        )
        raise

    snapshot = tipi_snapshot(dataset)
    release_id = tipi_release_id(dataset)
    release_dir = root / "releases" / release_id
    snapshot_path = release_dir / "tipi.jsonl"
    release_created = _write_once(snapshot_path, snapshot)
    manifest = {
        "artifact_sha256": artifact_sha,
        "created_at": _timestamp(artifact.captured_at),
        "contract_version": TIPI_CONTRACT_VERSION,
        "entry_count": len(dataset.entries),
        "ex_count": sum(entry.ex_code is not None for entry in dataset.entries),
        "release_id": release_id,
        "snapshot_sha256": hashlib.sha256(snapshot).hexdigest(),
        "source_act": dataset.source_act,
        "source_url": TIPI_SOURCE_URL,
    }
    _write_if_absent(release_dir / "release.json", _json_bytes(manifest))
    _write_if_absent(
        root / "artifacts" / "manifests" / f"{artifact_sha}.json",
        _json_bytes(
            {
                "artifact_sha256": artifact_sha,
                "byte_size": len(artifact.body),
                "captured_at": _timestamp(artifact.captured_at),
                "final_url": artifact.final_url,
                "http_status": artifact.status,
                "raw_path": raw_path.relative_to(root).as_posix(),
                "requested_url": artifact.requested_url,
                "response_headers": headers,
                "status": "accepted",
            }
        ),
    )
    change = _diff(previous_snapshot, snapshot)
    pointer = {"release_id": release_id, "updated_at": _timestamp(artifact.captured_at)}
    _write_atomic_if_changed(pointer_path, _json_bytes(pointer))
    return TipiIngestionResult(
        artifact_sha256=artifact_sha,
        release_id=release_id,
        artifact_created=raw_created,
        release_created=release_created,
        entry_count=len(dataset.entries),
        ex_count=sum(entry.ex_code is not None for entry in dataset.entries),
        diff=change,
    )


def capture_tipi(output_dir: Path, *, client: TipiSourceClient) -> TipiIngestionResult:
    return ingest_tipi_artifact(client.fetch(TIPI_SOURCE_URL), output_dir)
