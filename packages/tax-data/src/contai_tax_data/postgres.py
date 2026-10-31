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

from contai_tax_data.ncm import DEFAULT_QUALITY_POLICY, NcmDataset, QualityPolicy, parse_ncm_json, validate_ncm
from contai_tax_data.source import NCM_SOURCE_URL

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_KEY = "siscomex-ncm"
_QUALITY_CHECKS = frozenset({"entry_count", "leaf_count", "quality_policy", "release_identity", "snapshot_sha256"})


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
