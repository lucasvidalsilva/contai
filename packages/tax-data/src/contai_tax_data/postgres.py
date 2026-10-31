"""Persistencia PostgreSQL e publicacao atomica de releases NCM aprovadas."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from contai_tax_data.ibs_cbs import (
    IBS_CBS_CONTRACT_VERSION,
    IBS_CBS_SOURCE_URL,
    IbsCbsDataset,
    ibs_cbs_release_id,
    ibs_cbs_snapshot,
    parse_ibs_cbs_html,
    validate_ibs_cbs,
)
from contai_tax_data.ncm import DEFAULT_QUALITY_POLICY, NcmDataset, QualityPolicy, parse_ncm_json, validate_ncm
from contai_tax_data.source import NCM_SOURCE_URL
from contai_tax_data.tipi import (
    TIPI_SOURCE_URL,
    TipiDataset,
    parse_tipi_xlsx,
    tipi_release_id,
    tipi_snapshot,
    validate_tipi,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_KEY = "siscomex-ncm"
_QUALITY_CHECKS = frozenset({"entry_count", "leaf_count", "quality_policy", "release_identity", "snapshot_sha256"})
_TIPI_SOURCE_KEY = "rfb-tipi"
_TIPI_QUALITY_CHECKS = frozenset({"entry_count", "ex_count", "quality_policy", "release_identity", "snapshot_sha256"})
_IBS_CBS_SOURCE_KEY = "svrs-cff-classificacao-tributaria"
_IBS_CBS_QUALITY_CHECKS = frozenset(
    {"entry_count", "cst_count", "annex_link_count", "quality_policy", "release_identity", "snapshot_sha256"}
)


@dataclass(frozen=True, slots=True)
class LocalNcmRelease:
    release_id: str
    artifact_sha256: str
    snapshot_sha256: str
    contract_version: str
    source_schema_version: str
    source_act: str
    source_as_of: date
    created_at: datetime
    captured_at: datetime
    requested_url: str
    final_url: str
    http_status: int
    content_type: str
    byte_size: int
    raw_path: str
    response_headers: dict[str, str]
    dataset: NcmDataset


@dataclass(frozen=True, slots=True)
class LocalTipiRelease:
    release_id: str
    artifact_sha256: str
    snapshot_sha256: str
    contract_version: str
    source_act: str
    created_at: datetime
    captured_at: datetime
    requested_url: str
    final_url: str
    http_status: int
    content_type: str
    byte_size: int
    raw_path: str
    response_headers: dict[str, str]
    dataset: TipiDataset


@dataclass(frozen=True, slots=True)
class LocalIbsCbsRelease:
    release_id: str
    artifact_sha256: str
    snapshot_sha256: str
    contract_version: str
    created_at: datetime
    captured_at: datetime
    requested_url: str
    final_url: str
    http_status: int
    content_type: str
    byte_size: int
    raw_path: str
    response_headers: dict[str, str]
    dataset: IbsCbsDataset


@dataclass(frozen=True, slots=True)
class StageResult:
    release_id: str
    release_created: bool
    entry_count: int
    leaf_count: int


@dataclass(frozen=True, slots=True)
class PublicationResult:
    release_id: str
    published: bool
    entry_count: int
    published_at: datetime


def result_as_dict(result: StageResult | PublicationResult) -> dict[str, object]:
    value = asdict(result)
    for key, item in value.items():
        if isinstance(item, (date, datetime)):
            value[key] = item.isoformat().replace("+00:00", "Z")
    return value


def _object(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{context} deve ser objeto JSON")
    return value


def _text(mapping: dict[str, Any], key: str, context: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context}.{key} deve ser texto nao vazio")
    return value


def _integer(mapping: dict[str, Any], key: str, context: str) -> int:
    value = mapping.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{context}.{key} deve ser inteiro")
    return value


def _timestamp(value: str, context: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{context} deve ser timestamp ISO-8601") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{context} deve conter fuso horario")
    return parsed


def _date(value: str, context: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{context} deve ser data ISO-8601") from error


def _safe_local_path(root: Path, relative: str, context: str) -> Path:
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"{context} aponta para fora do repositorio local de dados")
    return candidate


def _read_json(path: Path, context: str) -> dict[str, Any]:
    try:
        return _object(json.loads(path.read_text(encoding="utf-8")), context)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"nao foi possivel ler {context}: {path}") from error


def load_local_ncm_release(output_dir: Path, release_id: str | None = None) -> LocalNcmRelease:
    """Revalida bruto, snapshot e manifestos antes de qualquer escrita no banco."""
    root = output_dir.resolve()
    if release_id is None:
        pointer = _read_json(root / "state" / "ncm-current.json", "ponteiro NCM")
        release_id = _text(pointer, "release_id", "ponteiro NCM")
    if not _SHA256.fullmatch(release_id):
        raise ValueError("release_id deve ser SHA-256 hexadecimal")

    release_manifest = _read_json(root / "releases" / release_id / "manifest.json", "manifesto da release")
    if _text(release_manifest, "release_id", "manifesto da release") != release_id:
        raise ValueError("release_id diverge do manifesto")
    artifact_sha256 = _text(release_manifest, "artifact_sha256", "manifesto da release")
    snapshot_sha256 = _text(release_manifest, "snapshot_sha256", "manifesto da release")
    if not _SHA256.fullmatch(artifact_sha256) or not _SHA256.fullmatch(snapshot_sha256):
        raise ValueError("manifesto contem hash SHA-256 invalido")

    snapshot_path = _safe_local_path(
        root, _text(release_manifest, "snapshot_path", "manifesto da release"), "snapshot_path"
    )
    snapshot = snapshot_path.read_bytes()
    if hashlib.sha256(snapshot).hexdigest() != snapshot_sha256:
        raise ValueError("hash do snapshot diverge do manifesto")

    artifact_manifest = _read_json(
        root / "artifacts" / "manifests" / f"{artifact_sha256}.json", "manifesto do artefato"
    )
    if _text(artifact_manifest, "artifact_sha256", "manifesto do artefato") != artifact_sha256:
        raise ValueError("hash do artefato diverge do manifesto")
    if _text(artifact_manifest, "status", "manifesto do artefato") != "accepted":
        raise ValueError("somente artefatos aceitos podem ser persistidos")
    raw_path = _text(artifact_manifest, "raw_path", "manifesto do artefato")
    raw = _safe_local_path(root, raw_path, "raw_path").read_bytes()
    if hashlib.sha256(raw).hexdigest() != artifact_sha256:
        raise ValueError("hash do artefato bruto diverge do manifesto")
    byte_size = _integer(artifact_manifest, "byte_size", "manifesto do artefato")
    if len(raw) != byte_size:
        raise ValueError("tamanho do artefato bruto diverge do manifesto")

    dataset = parse_ncm_json(raw)
    if dataset.release_id != release_id:
        raise ValueError("identidade semantica da release diverge do manifesto")
    if dataset.snapshot_jsonl() != snapshot:
        raise ValueError("snapshot nao e reproduzivel a partir do artefato bruto")
    if len(dataset.entries) != _integer(release_manifest, "entry_count", "manifesto da release"):
        raise ValueError("contagem de entradas diverge do manifesto")
    if dataset.leaf_count != _integer(release_manifest, "leaf_count", "manifesto da release"):
        raise ValueError("contagem de subitens diverge do manifesto")

    headers = _object(artifact_manifest.get("response_headers"), "response_headers")
    if not all(isinstance(value, str) for value in headers.values()):
        raise ValueError("response_headers deve conter somente textos")
    content_type = str(headers.get("content-type", "")).split(";", maxsplit=1)[0].strip().lower()
    if content_type != "application/json":
        raise ValueError("manifesto nao confirma Content-Type application/json")

    source_as_of = _date(_text(release_manifest, "source_as_of", "manifesto da release"), "source_as_of")
    if dataset.source_as_of != source_as_of:
        raise ValueError("data da fonte diverge do manifesto")
    source_act = _text(release_manifest, "source_act", "manifesto da release")
    if dataset.source_act != source_act:
        raise ValueError("ato da fonte diverge do manifesto")

    return LocalNcmRelease(
        release_id=release_id,
        artifact_sha256=artifact_sha256,
        snapshot_sha256=snapshot_sha256,
        contract_version=_text(release_manifest, "contract_version", "manifesto da release"),
        source_schema_version=_text(release_manifest, "source_schema_version", "manifesto da release"),
        source_act=source_act,
        source_as_of=source_as_of,
        created_at=_timestamp(_text(release_manifest, "created_at", "manifesto da release"), "created_at"),
        captured_at=_timestamp(_text(artifact_manifest, "captured_at", "manifesto do artefato"), "captured_at"),
        requested_url=_text(artifact_manifest, "requested_url", "manifesto do artefato"),
        final_url=_text(artifact_manifest, "final_url", "manifesto do artefato"),
        http_status=_integer(artifact_manifest, "http_status", "manifesto do artefato"),
        content_type=content_type,
        byte_size=byte_size,
        raw_path=raw_path,
        response_headers={key: str(value) for key, value in headers.items()},
        dataset=dataset,
    )


def load_local_tipi_release(
    output_dir: Path,
    release_id: str | None = None,
    *,
    minimum_entries: int = 8_000,
    maximum_entries: int = 14_000,
    minimum_ex_entries: int = 500,
    maximum_missing_rates: int = 10,
) -> LocalTipiRelease:
    """Revalida o XLSX bruto, o contrato e o snapshot antes de gravar no PostgreSQL."""
    root = output_dir.resolve()
    if release_id is None:
        pointer = _read_json(root / "state" / "tipi-current.json", "ponteiro TIPI")
        release_id = _text(pointer, "release_id", "ponteiro TIPI")
    if not _SHA256.fullmatch(release_id):
        raise ValueError("release_id deve ser SHA-256 hexadecimal")

    release_manifest = _read_json(root / "releases" / release_id / "release.json", "manifesto da release TIPI")
    if _text(release_manifest, "release_id", "manifesto da release TIPI") != release_id:
        raise ValueError("release_id diverge do manifesto TIPI")
    artifact_sha256 = _text(release_manifest, "artifact_sha256", "manifesto da release TIPI")
    snapshot_sha256 = _text(release_manifest, "snapshot_sha256", "manifesto da release TIPI")
    if not _SHA256.fullmatch(artifact_sha256) or not _SHA256.fullmatch(snapshot_sha256):
        raise ValueError("manifesto TIPI contem hash SHA-256 invalido")

    snapshot = (root / "releases" / release_id / "tipi.jsonl").read_bytes()
    if hashlib.sha256(snapshot).hexdigest() != snapshot_sha256:
        raise ValueError("hash do snapshot TIPI diverge do manifesto")
    artifact_manifest = _read_json(
        root / "artifacts" / "manifests" / f"{artifact_sha256}.json", "manifesto do artefato TIPI"
    )
    if _text(artifact_manifest, "artifact_sha256", "manifesto do artefato TIPI") != artifact_sha256:
        raise ValueError("hash do artefato TIPI diverge do manifesto")
    if _text(artifact_manifest, "status", "manifesto do artefato TIPI") != "accepted":
        raise ValueError("somente artefatos TIPI aceitos podem ser persistidos")

    raw_path = _text(artifact_manifest, "raw_path", "manifesto do artefato TIPI")
    raw = _safe_local_path(root, raw_path, "raw_path").read_bytes()
    if hashlib.sha256(raw).hexdigest() != artifact_sha256:
        raise ValueError("hash do XLSX bruto diverge do manifesto")
    byte_size = _integer(artifact_manifest, "byte_size", "manifesto do artefato TIPI")
    if len(raw) != byte_size:
        raise ValueError("tamanho do XLSX bruto diverge do manifesto")

    dataset = parse_tipi_xlsx(raw)
    validate_tipi(
        dataset,
        minimum_entries=minimum_entries,
        maximum_entries=maximum_entries,
        minimum_ex_entries=minimum_ex_entries,
        maximum_missing_rates=maximum_missing_rates,
    )
    if tipi_release_id(dataset) != release_id or tipi_snapshot(dataset) != snapshot:
        raise ValueError("release TIPI nao e reproduzivel a partir do XLSX bruto")
    if dataset.source_act != _text(release_manifest, "source_act", "manifesto da release TIPI"):
        raise ValueError("atos da fonte TIPI divergem do manifesto")
    if len(dataset.entries) != _integer(release_manifest, "entry_count", "manifesto da release TIPI"):
        raise ValueError("contagem da release TIPI diverge do manifesto")
    ex_count = sum(entry.ex_code is not None for entry in dataset.entries)
    if ex_count != _integer(release_manifest, "ex_count", "manifesto da release TIPI"):
        raise ValueError("contagem EX da release TIPI diverge do manifesto")

    headers = _object(artifact_manifest.get("response_headers"), "response_headers TIPI")
    if not all(isinstance(value, str) for value in headers.values()):
        raise ValueError("response_headers TIPI deve conter somente textos")
    content_type = str(headers.get("content-type", "")).split(";", maxsplit=1)[0].strip().lower()
    if content_type not in {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",
        "application/xlsx",
    }:
        raise ValueError("manifesto nao confirma Content-Type XLSX TIPI")
    captured_at = _timestamp(_text(artifact_manifest, "captured_at", "manifesto do artefato TIPI"), "captured_at")
    created_value = release_manifest.get("created_at")
    created_at = _timestamp(created_value, "created_at") if isinstance(created_value, str) else captured_at

    return LocalTipiRelease(
        release_id=release_id,
        artifact_sha256=artifact_sha256,
        snapshot_sha256=snapshot_sha256,
        contract_version=_text(release_manifest, "contract_version", "manifesto da release TIPI"),
        source_act=dataset.source_act,
        created_at=created_at,
        captured_at=captured_at,
        requested_url=_text(artifact_manifest, "requested_url", "manifesto do artefato TIPI"),
        final_url=_text(artifact_manifest, "final_url", "manifesto do artefato TIPI"),
        http_status=_integer(artifact_manifest, "http_status", "manifesto do artefato TIPI"),
        content_type=content_type,
        byte_size=byte_size,
        raw_path=raw_path,
        response_headers={key: str(value) for key, value in headers.items()},
        dataset=dataset,
    )


def load_local_ibs_cbs_release(
    output_dir: Path,
    release_id: str | None = None,
    *,
    minimum_csts: int = 1,
    maximum_csts: int = 40,
    minimum_classifications: int = 100,
    maximum_classifications: int = 500,
    maximum_annex_links: int = 50_000,
) -> LocalIbsCbsRelease:
    """Revalida o HTML bruto e o snapshot local antes do staging PostgreSQL."""
    root = output_dir.resolve()
    if release_id is None:
        pointer = _read_json(root / "state" / "ibs-cbs-current.json", "ponteiro IBS/CBS")
        release_id = _text(pointer, "release_id", "ponteiro IBS/CBS")
    if not _SHA256.fullmatch(release_id):
        raise ValueError("release_id IBS/CBS deve ser SHA-256 hexadecimal")

    release_manifest = _read_json(root / "releases" / f"{release_id}.json", "manifesto da release IBS/CBS")
    if _text(release_manifest, "release_id", "manifesto da release IBS/CBS") != release_id:
        raise ValueError("release_id diverge do manifesto IBS/CBS")
    snapshot_sha256 = _text(release_manifest, "snapshot_sha256", "manifesto da release IBS/CBS")
    artifact_sha256_value = release_manifest.get("artifact_sha256")
    if isinstance(artifact_sha256_value, str):
        artifact_sha256 = artifact_sha256_value
    else:
        legacy_matches: list[str] = []
        for manifest_path in (root / "artifacts" / "manifests").glob("*.json"):
            try:
                manifest_candidate = _read_json(manifest_path, "manifesto local IBS/CBS")
            except ValueError:
                continue
            candidate_hash = manifest_candidate.get("artifact_sha256")
            if manifest_candidate.get("release_id") == release_id and isinstance(candidate_hash, str):
                legacy_matches.append(candidate_hash)
        if len(set(legacy_matches)) != 1:
            raise ValueError("manifesto IBS/CBS nao identifica univocamente o artefato bruto")
        artifact_sha256 = legacy_matches[0]
    if not _SHA256.fullmatch(artifact_sha256) or not _SHA256.fullmatch(snapshot_sha256):
        raise ValueError("manifesto IBS/CBS contem hash SHA-256 invalido")

    snapshot = _safe_local_path(root, f"releases/{release_id}.jsonl", "snapshot IBS/CBS").read_bytes()
    if hashlib.sha256(snapshot).hexdigest() != snapshot_sha256:
        raise ValueError("hash do snapshot IBS/CBS diverge do manifesto")
    artifact_manifest = _read_json(
        root / "artifacts" / "manifests" / f"{artifact_sha256}.json", "manifesto do artefato IBS/CBS"
    )
    if _text(artifact_manifest, "artifact_sha256", "manifesto do artefato IBS/CBS") != artifact_sha256:
        raise ValueError("hash do artefato IBS/CBS diverge do manifesto")
    if _text(artifact_manifest, "status", "manifesto do artefato IBS/CBS") != "accepted":
        raise ValueError("somente artefatos IBS/CBS aceitos podem ser persistidos")
    parser_version = artifact_manifest.get("parser_version")
    if parser_version is not None and parser_version != IBS_CBS_CONTRACT_VERSION:
        raise ValueError("parser IBS/CBS diverge do manifesto do artefato")
    raw_path = _text(artifact_manifest, "raw_path", "manifesto do artefato IBS/CBS")
    raw = _safe_local_path(root, raw_path, "raw_path IBS/CBS").read_bytes()
    if hashlib.sha256(raw).hexdigest() != artifact_sha256:
        raise ValueError("hash do HTML bruto IBS/CBS diverge do manifesto")
    headers = _object(artifact_manifest.get("headers"), "response_headers IBS/CBS")
    if not all(isinstance(value, str) for value in headers.values()):
        raise ValueError("response_headers IBS/CBS deve conter somente textos")
    content_type = str(headers.get("content-type", "")).split(";", maxsplit=1)[0].strip().lower()
    if content_type != "text/html":
        raise ValueError("manifesto nao confirma Content-Type HTML IBS/CBS")
    byte_size_value = artifact_manifest.get("byte_size", headers.get("content-length", len(raw)))
    if not isinstance(byte_size_value, int | str) or isinstance(byte_size_value, bool):
        raise ValueError("byte_size IBS/CBS deve ser inteiro")
    try:
        byte_size = int(byte_size_value)
    except ValueError:
        raise ValueError("byte_size IBS/CBS deve ser inteiro") from None
    if len(raw) != byte_size:
        raise ValueError("tamanho do HTML bruto IBS/CBS diverge do manifesto")
    dataset = parse_ibs_cbs_html(raw)
    validate_ibs_cbs(
        dataset,
        minimum_csts=minimum_csts,
        maximum_csts=maximum_csts,
        minimum_classifications=minimum_classifications,
        maximum_classifications=maximum_classifications,
        maximum_annex_links=maximum_annex_links,
    )
    if ibs_cbs_release_id(ibs_cbs_snapshot(dataset)) != release_id:
        raise ValueError("release IBS/CBS nao e reproduzivel a partir do HTML bruto")
    if ibs_cbs_snapshot(dataset) != snapshot:
        raise ValueError("snapshot IBS/CBS diverge do HTML bruto")
    counts = {
        "cst_count": len(dataset.csts),
        "classification_count": len(dataset.classifications),
        "annex_link_count": len(dataset.annex_links),
    }
    for key, observed in counts.items():
        if _integer(release_manifest, key, "manifesto da release IBS/CBS") != observed:
            raise ValueError(f"{key} da release IBS/CBS diverge do manifesto")
    captured_at = _timestamp(_text(artifact_manifest, "captured_at", "manifesto do artefato IBS/CBS"), "captured_at")
    created_at_value = release_manifest.get("created_at")
    created_at = _timestamp(created_at_value, "created_at") if isinstance(created_at_value, str) else captured_at
    source_id = artifact_manifest.get("source_id", _IBS_CBS_SOURCE_KEY)
    if source_id != _IBS_CBS_SOURCE_KEY:
        raise ValueError("source_id do artefato IBS/CBS diverge do contrato")
    if _text(artifact_manifest, "requested_url", "manifesto do artefato IBS/CBS") != IBS_CBS_SOURCE_URL:
        raise ValueError("requested_url do artefato IBS/CBS diverge da fonte oficial")
    return LocalIbsCbsRelease(
        release_id=release_id,
        artifact_sha256=artifact_sha256,
        snapshot_sha256=snapshot_sha256,
        contract_version=_text(release_manifest, "contract_version", "manifesto da release IBS/CBS"),
        created_at=created_at,
        captured_at=captured_at,
        requested_url=_text(artifact_manifest, "requested_url", "manifesto do artefato IBS/CBS"),
        final_url=_text(artifact_manifest, "final_url", "manifesto do artefato IBS/CBS"),
        http_status=_integer(artifact_manifest, "http_status", "manifesto do artefato IBS/CBS"),
        content_type=content_type,
        byte_size=byte_size,
        raw_path=raw_path,
        response_headers={key: str(value) for key, value in headers.items()},
        dataset=dataset,
    )


def _configure_transaction(connection: Connection[Any], lock_name: str) -> None:
    connection.execute("set local role tax_ingest_writer")
    connection.execute("set local statement_timeout = '60s'")
    connection.execute("set local lock_timeout = '5s'")
    connection.execute("select pg_advisory_xact_lock(hashtextextended(%s, 0))", (lock_name,))


def _upsert_source(connection: Connection[Any], local: LocalNcmRelease) -> None:
    connection.execute(
        """
        insert into tax_ingest.source_registry (
          source_key, agency, dataset_name, canonical_url, source_format,
          contract_version, parser_version, updated_at
        ) values (%s, %s, %s, %s, %s, %s, %s, %s)
        on conflict (source_key) do update set
          agency = excluded.agency,
          dataset_name = excluded.dataset_name,
          canonical_url = excluded.canonical_url,
          source_format = excluded.source_format,
          contract_version = excluded.contract_version,
          parser_version = excluded.parser_version,
          updated_at = excluded.updated_at
        """,
        (
            _SOURCE_KEY,
            "Receita Federal do Brasil / Portal Unico Siscomex",
            "Nomenclatura Comum do Mercosul vigente",
            NCM_SOURCE_URL,
            "application/json",
            local.contract_version,
            local.source_schema_version,
            datetime.now(UTC),
        ),
    )
    connection.execute(
        """
        insert into tax_ingest.source_artifact (
          source_key, artifact_sha256, requested_url, final_url, captured_at,
          http_status, content_type, byte_size, raw_path, response_headers, status
        ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'accepted')
        on conflict (source_key, artifact_sha256) do nothing
        """,
        (
            _SOURCE_KEY,
            local.artifact_sha256,
            local.requested_url,
            local.final_url,
            local.captured_at,
            local.http_status,
            local.content_type,
            local.byte_size,
            local.raw_path,
            Jsonb(local.response_headers),
        ),
    )


def _record_failed_run(
    connection: Connection[Any], local: LocalNcmRelease, started_at: datetime, error: Exception
) -> None:
    try:
        with connection.transaction():
            _configure_transaction(connection, "contai:ncm:failure-log")
            _upsert_source(connection, local)
            connection.execute(
                """
                insert into tax_ingest.ingestion_run (
                  source_key, artifact_sha256, release_id, started_at, completed_at, status, error_message
                ) values (%s, %s, %s, %s, %s, 'failed', %s)
                """,
                (
                    _SOURCE_KEY,
                    local.artifact_sha256,
                    local.release_id,
                    started_at,
                    datetime.now(UTC),
                    f"{type(error).__name__}: {error}"[:4000],
                ),
            )
    except Exception as log_error:  # pragma: no cover - depende de falha dupla do banco
        error.add_note(f"nao foi possivel registrar a falha de ingestao: {log_error}")


def stage_ncm_release(
    connection: Connection[Any],
    output_dir: Path,
    release_id: str | None = None,
    *,
    quality_policy: QualityPolicy = DEFAULT_QUALITY_POLICY,
) -> StageResult:
    """Persiste candidato privado e controles de qualidade de forma idempotente."""
    local = load_local_ncm_release(output_dir, release_id)
    validate_ncm(local.dataset, quality_policy)
    started_at = datetime.now(UTC)
    try:
        with connection.transaction():
            _configure_transaction(connection, "contai:ncm:stage")
            _upsert_source(connection, local)
            inserted = connection.execute(
                """
                insert into tax_ingest.dataset_release (
                  release_id, source_key, artifact_sha256, domain, contract_version,
                  source_schema_version, source_act, source_as_of, snapshot_sha256,
                  entry_count, leaf_count, metadata, created_at
                ) values (%s, %s, %s, 'ncm', %s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (release_id) do nothing
                returning release_id
                """,
                (
                    local.release_id,
                    _SOURCE_KEY,
                    local.artifact_sha256,
                    local.contract_version,
                    local.source_schema_version,
                    local.source_act,
                    local.source_as_of,
                    local.snapshot_sha256,
                    len(local.dataset.entries),
                    local.dataset.leaf_count,
                    Jsonb({"raw_path": local.raw_path}),
                    local.created_at,
                ),
            ).fetchone()
            release_created = inserted is not None

            rows = (
                (
                    local.release_id,
                    entry.code,
                    entry.code_digits,
                    entry.description,
                    entry.level,
                    entry.parent_code,
                    entry.valid_from,
                    entry.valid_to,
                    entry.initial_act_type,
                    entry.initial_act_number,
                    entry.initial_act_year,
                    entry.source_row_id,
                )
                for entry in local.dataset.entries
            )
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    insert into tax_ingest.ncm_entry (
                      release_id, code, code_digits, description, level, parent_code,
                      valid_from, valid_to, initial_act_type, initial_act_number,
                      initial_act_year, source_row_id
                    ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    on conflict (release_id, code) do nothing
                    """,
                    rows,
                )

            persisted_count = connection.execute(
                "select count(*) from tax_ingest.ncm_entry where release_id = %s", (local.release_id,)
            ).fetchone()
            if persisted_count is None or persisted_count[0] != len(local.dataset.entries):
                raise RuntimeError("contagem persistida da NCM diverge da release local")

            quality_results = {
                "entry_count": {"observed": len(local.dataset.entries)},
                "leaf_count": {"observed": local.dataset.leaf_count},
                "quality_policy": asdict(quality_policy),
                "release_identity": {"release_id": local.release_id},
                "snapshot_sha256": {"snapshot_sha256": local.snapshot_sha256},
            }
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    insert into tax_ingest.quality_result (release_id, check_name, passed, observed)
                    values (%s, %s, true, %s)
                    on conflict (release_id, check_name) do update set
                      passed = excluded.passed,
                      observed = excluded.observed,
                      evaluated_at = now()
                    """,
                    (
                        (local.release_id, check_name, Jsonb(observed))
                        for check_name, observed in quality_results.items()
                    ),
                )
            connection.execute(
                """
                insert into tax_ingest.ingestion_run (
                  source_key, artifact_sha256, release_id, started_at, completed_at, status
                ) values (%s, %s, %s, %s, %s, 'succeeded')
                """,
                (_SOURCE_KEY, local.artifact_sha256, local.release_id, started_at, datetime.now(UTC)),
            )
    except Exception as error:
        _record_failed_run(connection, local, started_at, error)
        raise

    return StageResult(
        release_id=local.release_id,
        release_created=release_created,
        entry_count=len(local.dataset.entries),
        leaf_count=local.dataset.leaf_count,
    )


def publish_ncm_release(connection: Connection[Any], release_id: str) -> PublicationResult:
    """Promove um candidato aprovado sem expor estado parcial nem perder a versao corrente."""
    if not _SHA256.fullmatch(release_id):
        raise ValueError("release_id deve ser SHA-256 hexadecimal")
    with connection.transaction():
        _configure_transaction(connection, "contai:ncm:publish")
        release = connection.execute(
            """
            select status, contract_version, source_act, source_as_of, artifact_sha256,
                   snapshot_sha256, entry_count, leaf_count, published_at
            from tax_ingest.dataset_release
            where release_id = %s and domain = 'ncm'
            for update
            """,
            (release_id,),
        ).fetchone()
        if release is None:
            raise ValueError(f"release NCM inexistente: {release_id}")
        status, _, _, _, _, _, entry_count, _, existing_published_at = release

        checks = connection.execute(
            "select check_name, passed from tax_ingest.quality_result where release_id = %s", (release_id,)
        ).fetchall()
        check_map = {str(name): bool(passed) for name, passed in checks}
        if check_map.keys() != _QUALITY_CHECKS or not all(check_map.values()):
            raise RuntimeError("release nao possui todos os controles de qualidade aprovados")

        private_count = connection.execute(
            "select count(*) from tax_ingest.ncm_entry where release_id = %s", (release_id,)
        ).fetchone()
        if private_count is None or private_count[0] != entry_count:
            raise RuntimeError("contagem privada da NCM diverge da release")

        if status == "approved":
            current = connection.execute(
                "select release_id from tax_public.dataset_current where domain = 'ncm'"
            ).fetchone()
            if current is None or current[0] != release_id or existing_published_at is None:
                raise RuntimeError("release aprovada diverge do ponteiro publico; requer reparo manual")
            public_count = connection.execute(
                "select count(*) from tax_public.ncm_entry where release_id = %s", (release_id,)
            ).fetchone()
            if public_count is None or public_count[0] != entry_count:
                raise RuntimeError("release publica aprovada esta incompleta")
            return PublicationResult(
                release_id=release_id,
                published=False,
                entry_count=entry_count,
                published_at=existing_published_at,
            )
        if status != "candidate":
            raise RuntimeError(f"status da release nao pode ser publicado: {status}")

        published_at = datetime.now(UTC)
        connection.execute(
            """
            insert into tax_public.dataset_release (
              release_id, domain, contract_version, source_act, source_as_of,
              artifact_sha256, snapshot_sha256, entry_count, leaf_count, published_at
            )
            select release_id, domain, contract_version, source_act, source_as_of,
                   artifact_sha256, snapshot_sha256, entry_count, leaf_count, %s
            from tax_ingest.dataset_release
            where release_id = %s
            on conflict (release_id) do nothing
            """,
            (published_at, release_id),
        )
        connection.execute(
            """
            insert into tax_public.ncm_entry (
              release_id, code, code_digits, description, level, parent_code,
              valid_from, valid_to, initial_act_type, initial_act_number,
              initial_act_year, source_row_id
            )
            select release_id, code, code_digits, description, level, parent_code,
                   valid_from, valid_to, initial_act_type, initial_act_number,
                   initial_act_year, source_row_id
            from tax_ingest.ncm_entry
            where release_id = %s
            on conflict (release_id, code) do nothing
            """,
            (release_id,),
        )
        public_count = connection.execute(
            "select count(*) from tax_public.ncm_entry where release_id = %s", (release_id,)
        ).fetchone()
        if public_count is None or public_count[0] != entry_count:
            raise RuntimeError("copia publica da NCM ficou incompleta")

        connection.execute(
            """
            insert into tax_public.dataset_current (domain, release_id, updated_at)
            values ('ncm', %s, %s)
            on conflict (domain) do update set
              release_id = excluded.release_id,
              updated_at = excluded.updated_at
            """,
            (release_id, published_at),
        )
        connection.execute(
            """
            update tax_ingest.dataset_release
            set status = 'approved', published_at = %s
            where release_id = %s
            """,
            (published_at, release_id),
        )

    return PublicationResult(
        release_id=release_id,
        published=True,
        entry_count=entry_count,
        published_at=published_at,
    )


def _upsert_tipi_source(connection: Connection[Any], local: LocalTipiRelease) -> None:
    connection.execute(
        """
        insert into tax_ingest.source_registry (
          source_key, agency, dataset_name, canonical_url, source_format,
          contract_version, parser_version, updated_at
        ) values (%s, %s, %s, %s, %s, %s, %s, %s)
        on conflict (source_key) do update set
          agency = excluded.agency,
          dataset_name = excluded.dataset_name,
          canonical_url = excluded.canonical_url,
          source_format = excluded.source_format,
          contract_version = excluded.contract_version,
          parser_version = excluded.parser_version,
          updated_at = excluded.updated_at
        """,
        (
            _TIPI_SOURCE_KEY,
            "Receita Federal do Brasil",
            "Tabela de Incidencia do Imposto sobre Produtos Industrializados",
            TIPI_SOURCE_URL,
            local.content_type,
            local.contract_version,
            "contai_tax_data.tipi:tipi-v1",
            datetime.now(UTC),
        ),
    )
    connection.execute(
        """
        insert into tax_ingest.source_artifact (
          source_key, artifact_sha256, requested_url, final_url, captured_at,
          http_status, content_type, byte_size, raw_path, response_headers, status
        ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'accepted')
        on conflict (source_key, artifact_sha256) do nothing
        """,
        (
            _TIPI_SOURCE_KEY,
            local.artifact_sha256,
            local.requested_url,
            local.final_url,
            local.captured_at,
            local.http_status,
            local.content_type,
            local.byte_size,
            local.raw_path,
            Jsonb(local.response_headers),
        ),
    )


def _record_failed_tipi_run(
    connection: Connection[Any], local: LocalTipiRelease, started_at: datetime, error: Exception
) -> None:
    try:
        with connection.transaction():
            _configure_transaction(connection, "contai:tipi:failure-log")
            _upsert_tipi_source(connection, local)
            connection.execute(
                """
                insert into tax_ingest.ingestion_run (
                  source_key, artifact_sha256, release_id, started_at, completed_at, status, error_message
                ) values (%s, %s, %s, %s, %s, 'failed', %s)
                """,
                (
                    _TIPI_SOURCE_KEY,
                    local.artifact_sha256,
                    local.release_id,
                    started_at,
                    datetime.now(UTC),
                    f"{type(error).__name__}: {error}"[:4000],
                ),
            )
    except Exception as log_error:  # pragma: no cover - depende de falha dupla no banco
        error.add_note(f"nao foi possivel registrar a falha TIPI: {log_error}")


def stage_tipi_release(
    connection: Connection[Any],
    output_dir: Path,
    release_id: str | None = None,
    *,
    minimum_entries: int = 8_000,
    maximum_entries: int = 14_000,
    minimum_ex_entries: int = 500,
    maximum_missing_rates: int = 10,
) -> StageResult:
    """Persiste candidato TIPI privado após revalidar bruto e release local."""
    local = load_local_tipi_release(
        output_dir,
        release_id,
        minimum_entries=minimum_entries,
        maximum_entries=maximum_entries,
        minimum_ex_entries=minimum_ex_entries,
        maximum_missing_rates=maximum_missing_rates,
    )
    validate_tipi(
        local.dataset,
        minimum_entries=minimum_entries,
        maximum_entries=maximum_entries,
        minimum_ex_entries=minimum_ex_entries,
        maximum_missing_rates=maximum_missing_rates,
    )
    started_at = datetime.now(UTC)
    entry_count = len(local.dataset.entries)
    ex_count = sum(entry.ex_code is not None for entry in local.dataset.entries)
    quality_policy = {
        "maximum_entries": maximum_entries,
        "maximum_missing_rates": maximum_missing_rates,
        "minimum_entries": minimum_entries,
        "minimum_ex_entries": minimum_ex_entries,
    }
    try:
        with connection.transaction():
            _configure_transaction(connection, "contai:tipi:stage")
            _upsert_tipi_source(connection, local)
            inserted = connection.execute(
                """
                insert into tax_ingest.dataset_release (
                  release_id, source_key, artifact_sha256, domain, contract_version,
                  source_schema_version, source_act, source_as_of, snapshot_sha256,
                  entry_count, leaf_count, metadata, created_at
                ) values (%s, %s, %s, 'tipi', %s, %s, %s, null, %s, %s, 0, %s, %s)
                on conflict (release_id) do nothing
                returning release_id
                """,
                (
                    local.release_id,
                    _TIPI_SOURCE_KEY,
                    local.artifact_sha256,
                    local.contract_version,
                    local.contract_version,
                    local.source_act,
                    local.snapshot_sha256,
                    entry_count,
                    Jsonb({"raw_path": local.raw_path, "ex_count": ex_count}),
                    local.created_at,
                ),
            ).fetchone()
            release_created = inserted is not None

            rows = (
                (
                    local.release_id,
                    entry.ncm_code,
                    entry.ex_code or "",
                    entry.ex_code,
                    entry.description,
                    entry.ipi_rate,
                )
                for entry in local.dataset.entries
            )
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    insert into tax_ingest.tipi_entry (
                      release_id, ncm_code, ex_key, ex_code, description, ipi_rate
                    ) values (%s, %s, %s, %s, %s, %s)
                    on conflict (release_id, ncm_code, ex_key) do nothing
                    """,
                    rows,
                )
            persisted_count = connection.execute(
                "select count(*) from tax_ingest.tipi_entry where release_id = %s", (local.release_id,)
            ).fetchone()
            if persisted_count is None or persisted_count[0] != entry_count:
                raise RuntimeError("contagem persistida TIPI diverge da release local")

            quality_results = {
                "entry_count": {"observed": entry_count},
                "ex_count": {"observed": ex_count},
                "quality_policy": quality_policy,
                "release_identity": {"release_id": local.release_id},
                "snapshot_sha256": {"snapshot_sha256": local.snapshot_sha256},
            }
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    insert into tax_ingest.quality_result (release_id, check_name, passed, observed)
                    values (%s, %s, true, %s)
                    on conflict (release_id, check_name) do update set
                      passed = excluded.passed,
                      observed = excluded.observed,
                      evaluated_at = now()
                    """,
                    (
                        (local.release_id, check_name, Jsonb(observed))
                        for check_name, observed in quality_results.items()
                    ),
                )
            connection.execute(
                """
                insert into tax_ingest.ingestion_run (
                  source_key, artifact_sha256, release_id, started_at, completed_at, status
                ) values (%s, %s, %s, %s, %s, 'succeeded')
                """,
                (_TIPI_SOURCE_KEY, local.artifact_sha256, local.release_id, started_at, datetime.now(UTC)),
            )
    except Exception as error:
        _record_failed_tipi_run(connection, local, started_at, error)
        raise

    return StageResult(
        release_id=local.release_id,
        release_created=release_created,
        entry_count=entry_count,
        leaf_count=0,
    )


def _source_timestamp(value: object, context: str, *, nullable: bool = False) -> datetime | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{context} deve ser timestamp ISO")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{context} deve ser timestamp ISO") from None


def _ibs_attributes(record: dict[str, Any], excluded: frozenset[str]) -> Jsonb:
    return Jsonb({key: value for key, value in record.items() if key not in excluded})


def _upsert_ibs_cbs_source(connection: Connection[Any], local: LocalIbsCbsRelease) -> None:
    connection.execute(
        """
        insert into tax_ingest.source_registry (
          source_key, agency, dataset_name, canonical_url, source_format,
          contract_version, parser_version, updated_at
        ) values (%s, %s, %s, %s, 'text/html', %s, %s, %s)
        on conflict (source_key) do update set
          agency = excluded.agency,
          dataset_name = excluded.dataset_name,
          canonical_url = excluded.canonical_url,
          source_format = excluded.source_format,
          contract_version = excluded.contract_version,
          parser_version = excluded.parser_version,
          updated_at = excluded.updated_at
        """,
        (
            _IBS_CBS_SOURCE_KEY,
            "SVRS / ENCAT",
            "Classificacao Tributaria IBS e CBS",
            IBS_CBS_SOURCE_URL,
            local.contract_version,
            "contai_tax_data.ibs_cbs:ibs-cbs-v1",
            datetime.now(UTC),
        ),
    )
    connection.execute(
        """
        insert into tax_ingest.source_artifact (
          source_key, artifact_sha256, requested_url, final_url, captured_at,
          http_status, content_type, byte_size, raw_path, response_headers, status
        ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'accepted')
        on conflict (source_key, artifact_sha256) do nothing
        """,
        (
            _IBS_CBS_SOURCE_KEY,
            local.artifact_sha256,
            local.requested_url,
            local.final_url,
            local.captured_at,
            local.http_status,
            local.content_type,
            local.byte_size,
            local.raw_path,
            Jsonb(local.response_headers),
        ),
    )


def _record_failed_ibs_cbs_run(
    connection: Connection[Any], local: LocalIbsCbsRelease, started_at: datetime, error: Exception
) -> None:
    try:
        with connection.transaction():
            _configure_transaction(connection, "contai:ibs-cbs:failure-log")
            _upsert_ibs_cbs_source(connection, local)
            connection.execute(
                """
                insert into tax_ingest.ingestion_run (
                  source_key, artifact_sha256, release_id, started_at, completed_at, status, error_message
                ) values (%s, %s, %s, %s, %s, 'failed', %s)
                """,
                (
                    _IBS_CBS_SOURCE_KEY,
                    local.artifact_sha256,
                    local.release_id,
                    started_at,
                    datetime.now(UTC),
                    f"{type(error).__name__}: {error}"[:4000],
                ),
            )
    except Exception as log_error:  # pragma: no cover - depende de falha dupla no banco
        error.add_note(f"nao foi possivel registrar a falha IBS/CBS: {log_error}")


def stage_ibs_cbs_release(
    connection: Connection[Any],
    output_dir: Path,
    release_id: str | None = None,
    *,
    minimum_csts: int = 1,
    maximum_csts: int = 40,
    minimum_classifications: int = 100,
    maximum_classifications: int = 500,
    maximum_annex_links: int = 50_000,
) -> StageResult:
    """Carrega CST, cClassTrib e anexos no schema privado apos revalidar o bruto."""
    local = load_local_ibs_cbs_release(
        output_dir,
        release_id,
        minimum_csts=minimum_csts,
        maximum_csts=maximum_csts,
        minimum_classifications=minimum_classifications,
        maximum_classifications=maximum_classifications,
        maximum_annex_links=maximum_annex_links,
    )
    dataset = local.dataset
    started_at = datetime.now(UTC)
    cst_count = len(dataset.csts)
    entry_count = len(dataset.classifications)
    annex_count = len(dataset.annex_links)
    quality_policy = {
        "minimum_csts": minimum_csts,
        "maximum_csts": maximum_csts,
        "minimum_classifications": minimum_classifications,
        "maximum_classifications": maximum_classifications,
        "maximum_annex_links": maximum_annex_links,
    }
    try:
        with connection.transaction():
            _configure_transaction(connection, "contai:ibs-cbs:stage")
            _upsert_ibs_cbs_source(connection, local)
            inserted = connection.execute(
                """
                insert into tax_ingest.dataset_release (
                  release_id, source_key, artifact_sha256, domain, contract_version,
                  source_schema_version, source_act, source_as_of, snapshot_sha256,
                  entry_count, leaf_count, metadata, created_at
                ) values (%s, %s, %s, 'ibs_cbs', %s, %s, 'Tabela pública SVRS/Conformidade Fácil',
                          null, %s, %s, 0, %s, %s)
                on conflict (release_id) do nothing
                returning release_id
                """,
                (
                    local.release_id,
                    _IBS_CBS_SOURCE_KEY,
                    local.artifact_sha256,
                    local.contract_version,
                    local.contract_version,
                    local.snapshot_sha256,
                    entry_count,
                    Jsonb(
                        {
                            "raw_path": local.raw_path,
                            "cst_count": cst_count,
                            "classification_count": entry_count,
                            "annex_link_count": annex_count,
                        }
                    ),
                    local.created_at,
                ),
            ).fetchone()
            release_created = inserted is not None

            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    insert into tax_ingest.ibs_cbs_cst (
                      release_id, cst_code, description, valid_from, valid_to, attributes
                    ) values (%s, %s, %s, %s, %s, %s)
                    on conflict (release_id, cst_code) do nothing
                    """,
                    (
                        (
                            local.release_id,
                            row["Cst"],
                            row["NomeCst"],
                            _source_timestamp(row["DthIniVig"], "CST.DthIniVig"),
                            _source_timestamp(row["DthFimVig"], "CST.DthFimVig", nullable=True),
                            _ibs_attributes(row, frozenset({"Cst", "NomeCst", "DthIniVig", "DthFimVig"})),
                        )
                        for row in dataset.csts
                    ),
                )
                cursor.executemany(
                    """
                    insert into tax_ingest.ibs_cbs_classification (
                      release_id, cclasstrib_code, cst_code, description, short_description,
                      valid_from, valid_to, legislation_url, attributes
                    ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    on conflict (release_id, cclasstrib_code) do nothing
                    """,
                    (
                        (
                            local.release_id,
                            row["CodClassTrib"],
                            row["Cst"],
                            row["NomeClassTrib"],
                            row["NomeReduzido"],
                            _source_timestamp(row["DthIniVig"], "cClassTrib.DthIniVig"),
                            _source_timestamp(row["DthFimVig"], "cClassTrib.DthFimVig", nullable=True),
                            row["TexUrlLegislacao"],
                            _ibs_attributes(
                                row,
                                frozenset(
                                    {
                                        "CodClassTrib",
                                        "Cst",
                                        "NomeClassTrib",
                                        "NomeReduzido",
                                        "DthIniVig",
                                        "DthFimVig",
                                        "TexUrlLegislacao",
                                    }
                                ),
                            ),
                        )
                        for row in dataset.classifications
                    ),
                )
                cursor.executemany(
                    """
                    insert into tax_ingest.ibs_cbs_annex_link (
                      release_id, cclasstrib_code, source_record_id, annex_number, code, code_type,
                      permission, condition, exception, observation, valid_from, valid_to,
                      annex_item_number, item_description, annex_description, attributes
                    ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    on conflict (release_id, cclasstrib_code, source_record_id) do nothing
                    """,
                    (
                        (
                            local.release_id,
                            row["cclasstrib_code"],
                            row["source_record_id"],
                            row["NroAnexo"],
                            row["CodNcmNbs"],
                            row["TipoCodigo"],
                            row["TipoPermissao"],
                            row["DescCondicao"],
                            row["DescExcecao"],
                            row["Observacao"],
                            _source_timestamp(row["DthIniVig"], "anexo.DthIniVig"),
                            _source_timestamp(row["DthFimVig"], "anexo.DthFimVig", nullable=True),
                            row["NroItemAnexoLei"],
                            row["DescItemAnexo"],
                            row["DescAnexo"],
                            _ibs_attributes(
                                row,
                                frozenset(
                                    {
                                        "cclasstrib_code",
                                        "source_record_id",
                                        "NroAnexo",
                                        "CodNcmNbs",
                                        "TipoCodigo",
                                        "TipoPermissao",
                                        "DescCondicao",
                                        "DescExcecao",
                                        "Observacao",
                                        "DthIniVig",
                                        "DthFimVig",
                                        "NroItemAnexoLei",
                                        "DescItemAnexo",
                                        "DescAnexo",
                                    }
                                ),
                            ),
                        )
                        for row in dataset.annex_links
                    ),
                )

            counts = {
                "tax_ingest.ibs_cbs_cst": ("cst_code", cst_count),
                "tax_ingest.ibs_cbs_classification": ("cclasstrib_code", entry_count),
                "tax_ingest.ibs_cbs_annex_link": ("source_record_id", annex_count),
            }
            for table, (key_column, expected) in counts.items():
                result = connection.execute(
                    f"select count(*) from {table} where release_id = %s", (local.release_id,)
                ).fetchone()
                if result is None or result[0] != expected:
                    raise RuntimeError(f"contagem persistida IBS/CBS diverge em {key_column}")

            quality_results = {
                "entry_count": {"observed": entry_count},
                "cst_count": {"observed": cst_count},
                "annex_link_count": {"observed": annex_count},
                "quality_policy": quality_policy,
                "release_identity": {"release_id": local.release_id},
                "snapshot_sha256": {"snapshot_sha256": local.snapshot_sha256},
            }
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    insert into tax_ingest.quality_result (release_id, check_name, passed, observed)
                    values (%s, %s, true, %s)
                    on conflict (release_id, check_name) do update set
                      passed = excluded.passed, observed = excluded.observed, evaluated_at = now()
                    """,
                    (
                        (local.release_id, check_name, Jsonb(observed))
                        for check_name, observed in quality_results.items()
                    ),
                )
            connection.execute(
                """
                insert into tax_ingest.ingestion_run (
                  source_key, artifact_sha256, release_id, started_at, completed_at, status
                ) values (%s, %s, %s, %s, %s, 'succeeded')
                """,
                (_IBS_CBS_SOURCE_KEY, local.artifact_sha256, local.release_id, started_at, datetime.now(UTC)),
            )
    except Exception as error:
        _record_failed_ibs_cbs_run(connection, local, started_at, error)
        raise

    return StageResult(local.release_id, release_created, entry_count, 0)


def publish_tipi_release(connection: Connection[Any], release_id: str) -> PublicationResult:
    """Publica TIPI aprovada atomically, sem atribuir vigência ausente na fonte."""
    if not _SHA256.fullmatch(release_id):
        raise ValueError("release_id deve ser SHA-256 hexadecimal")
    with connection.transaction():
        _configure_transaction(connection, "contai:tipi:publish")
        release = connection.execute(
            """
            select status, entry_count, published_at
            from tax_ingest.dataset_release
            where release_id = %s and domain = 'tipi'
            for update
            """,
            (release_id,),
        ).fetchone()
        if release is None:
            raise ValueError(f"release TIPI inexistente: {release_id}")
        status, entry_count, existing_published_at = release
        checks = connection.execute(
            "select check_name, passed from tax_ingest.quality_result where release_id = %s", (release_id,)
        ).fetchall()
        check_map = {str(name): bool(passed) for name, passed in checks}
        if check_map.keys() != _TIPI_QUALITY_CHECKS or not all(check_map.values()):
            raise RuntimeError("release TIPI nao possui todos os controles de qualidade aprovados")
        private_count = connection.execute(
            "select count(*) from tax_ingest.tipi_entry where release_id = %s", (release_id,)
        ).fetchone()
        if private_count is None or private_count[0] != entry_count:
            raise RuntimeError("contagem privada TIPI diverge da release")

        if status == "approved":
            current = connection.execute(
                "select release_id from tax_public.dataset_current where domain = 'tipi'"
            ).fetchone()
            if current is None or current[0] != release_id or existing_published_at is None:
                raise RuntimeError("release TIPI aprovada diverge do ponteiro publico; requer reparo manual")
            public_count = connection.execute(
                "select count(*) from tax_public.tipi_entry where release_id = %s", (release_id,)
            ).fetchone()
            if public_count is None or public_count[0] != entry_count:
                raise RuntimeError("release TIPI aprovada esta incompleta")
            return PublicationResult(release_id, False, entry_count, existing_published_at)
        if status != "candidate":
            raise RuntimeError(f"status da release TIPI nao pode ser publicado: {status}")

        published_at = datetime.now(UTC)
        connection.execute(
            """
            insert into tax_public.dataset_release (
              release_id, domain, contract_version, source_act, source_as_of,
              artifact_sha256, snapshot_sha256, entry_count, leaf_count, published_at
            )
            select release_id, domain, contract_version, source_act, source_as_of,
                   artifact_sha256, snapshot_sha256, entry_count, leaf_count, %s
            from tax_ingest.dataset_release where release_id = %s
            on conflict (release_id) do nothing
            """,
            (published_at, release_id),
        )
        connection.execute(
            """
            insert into tax_public.tipi_entry (
              release_id, ncm_code, ex_key, ex_code, description, ipi_rate
            )
            select release_id, ncm_code, ex_key, ex_code, description, ipi_rate
            from tax_ingest.tipi_entry where release_id = %s
            on conflict (release_id, ncm_code, ex_key) do nothing
            """,
            (release_id,),
        )
        public_count = connection.execute(
            "select count(*) from tax_public.tipi_entry where release_id = %s", (release_id,)
        ).fetchone()
        if public_count is None or public_count[0] != entry_count:
            raise RuntimeError("copia publica TIPI ficou incompleta")
        connection.execute(
            """
            insert into tax_public.dataset_current (domain, release_id, updated_at)
            values ('tipi', %s, %s)
            on conflict (domain) do update set
              release_id = excluded.release_id,
              updated_at = excluded.updated_at
            """,
            (release_id, published_at),
        )
        connection.execute(
            "update tax_ingest.dataset_release set status = 'approved', published_at = %s where release_id = %s",
            (published_at, release_id),
        )

    return PublicationResult(release_id, True, entry_count, published_at)


def publish_ibs_cbs_release(connection: Connection[Any], release_id: str) -> PublicationResult:
    """Publica o snapshot IBS/CBS inteiro em transacao, sem expor estado parcial."""
    if not _SHA256.fullmatch(release_id):
        raise ValueError("release_id deve ser SHA-256 hexadecimal")
    with connection.transaction():
        _configure_transaction(connection, "contai:ibs-cbs:publish")
        release = connection.execute(
            """
            select status, entry_count, metadata, published_at
            from tax_ingest.dataset_release
            where release_id = %s and domain = 'ibs_cbs'
            for update
            """,
            (release_id,),
        ).fetchone()
        if release is None:
            raise ValueError(f"release IBS/CBS inexistente: {release_id}")
        status, entry_count, metadata_value, existing_published_at = release
        metadata = _object(metadata_value, "metadata IBS/CBS")
        checks = connection.execute(
            "select check_name, passed from tax_ingest.quality_result where release_id = %s", (release_id,)
        ).fetchall()
        check_map = {str(name): bool(passed) for name, passed in checks}
        if check_map.keys() != _IBS_CBS_QUALITY_CHECKS or not all(check_map.values()):
            raise RuntimeError("release IBS/CBS nao possui todos os controles de qualidade aprovados")

        private_counts = {
            "tax_ingest.ibs_cbs_cst": _integer(metadata, "cst_count", "metadata IBS/CBS"),
            "tax_ingest.ibs_cbs_classification": entry_count,
            "tax_ingest.ibs_cbs_annex_link": _integer(metadata, "annex_link_count", "metadata IBS/CBS"),
        }
        for table, expected in private_counts.items():
            result = connection.execute(f"select count(*) from {table} where release_id = %s", (release_id,)).fetchone()
            if result is None or expected is None or result[0] != expected:
                raise RuntimeError(f"contagem privada IBS/CBS diverge em {table}")

        if status == "approved":
            current = connection.execute(
                "select release_id from tax_public.dataset_current where domain = 'ibs_cbs'"
            ).fetchone()
            if current is None or current[0] != release_id or existing_published_at is None:
                raise RuntimeError("release IBS/CBS aprovada diverge do ponteiro publico; requer reparo manual")
            for table, expected in (
                ("tax_public.ibs_cbs_cst", private_counts["tax_ingest.ibs_cbs_cst"]),
                ("tax_public.ibs_cbs_classification", entry_count),
                ("tax_public.ibs_cbs_annex_link", private_counts["tax_ingest.ibs_cbs_annex_link"]),
            ):
                result = connection.execute(
                    f"select count(*) from {table} where release_id = %s", (release_id,)
                ).fetchone()
                if result is None or result[0] != expected:
                    raise RuntimeError(f"release IBS/CBS aprovada incompleta em {table}")
            return PublicationResult(release_id, False, entry_count, existing_published_at)
        if status != "candidate":
            raise RuntimeError(f"status da release IBS/CBS nao pode ser publicado: {status}")

        published_at = datetime.now(UTC)
        connection.execute(
            """
            insert into tax_public.dataset_release (
              release_id, domain, contract_version, source_act, source_as_of,
              artifact_sha256, snapshot_sha256, entry_count, leaf_count, published_at
            )
            select release_id, domain, contract_version, source_act, source_as_of,
                   artifact_sha256, snapshot_sha256, entry_count, leaf_count, %s
            from tax_ingest.dataset_release where release_id = %s
            on conflict (release_id) do nothing
            """,
            (published_at, release_id),
        )
        for table in ("ibs_cbs_cst", "ibs_cbs_classification", "ibs_cbs_annex_link"):
            columns = {
                "ibs_cbs_cst": "cst_code, description, valid_from, valid_to, attributes",
                "ibs_cbs_classification": (
                    "cclasstrib_code, cst_code, description, short_description, valid_from, valid_to, "
                    "legislation_url, attributes"
                ),
                "ibs_cbs_annex_link": (
                    "cclasstrib_code, source_record_id, annex_number, code, code_type, permission, condition, "
                    "exception, observation, valid_from, valid_to, annex_item_number, item_description, "
                    "annex_description, attributes"
                ),
            }[table]
            connection.execute(
                f"""
                insert into tax_public.{table} (release_id, {columns})
                select release_id, {columns}
                from tax_ingest.{table} where release_id = %s
                on conflict do nothing
                """,
                (release_id,),
            )
        public_counts = {
            "tax_public.ibs_cbs_cst": private_counts["tax_ingest.ibs_cbs_cst"],
            "tax_public.ibs_cbs_classification": entry_count,
            "tax_public.ibs_cbs_annex_link": private_counts["tax_ingest.ibs_cbs_annex_link"],
        }
        for table, expected in public_counts.items():
            result = connection.execute(f"select count(*) from {table} where release_id = %s", (release_id,)).fetchone()
            if result is None or result[0] != expected:
                raise RuntimeError(f"copia publica IBS/CBS ficou incompleta em {table}")
        connection.execute(
            """
            insert into tax_public.dataset_current (domain, release_id, updated_at)
            values ('ibs_cbs', %s, %s)
            on conflict (domain) do update set
              release_id = excluded.release_id, updated_at = excluded.updated_at
            """,
            (release_id, published_at),
        )
        connection.execute(
            "update tax_ingest.dataset_release set status = 'approved', published_at = %s where release_id = %s",
            (published_at, release_id),
        )

    return PublicationResult(release_id, True, entry_count, published_at)
