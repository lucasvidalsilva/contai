"""Staging privado e reprocessavel de candidatos CEST no PostgreSQL."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from contai_tax_data.cest_candidates import (
    CEST_CANDIDATE_CONTRACT,
    cest_candidates_jsonl,
    parse_cest_candidates,
)
from contai_tax_data.cest_capture import CEST_SOURCE_URL

_SOURCE_KEY = "confaz-cest"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class CestCandidateStageResult:
    candidate_set_sha256: str
    candidate_count: int
    candidate_set_created: bool


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} invalido: {error}") from None
    if not isinstance(value, dict):
        raise ValueError(f"{label} precisa ser um objeto JSON")
    return value


def _required_text(value: object, key: str, label: str) -> str:
    result = value.get(key) if isinstance(value, dict) else None
    if not isinstance(result, str) or not result:
        raise ValueError(f"{label}.{key} ausente ou invalido")
    return result


def stage_cest_candidates(
    connection: Connection[Any], candidates_path: Path, observation_path: Path, capture_root: Path
) -> CestCandidateStageResult:
    """Valida hashes/proveniÃªncia e insere ocorrÃªncias sem criar dados publicos."""
    snapshot = candidates_path.read_bytes()
    candidate_set_sha256 = hashlib.sha256(snapshot).hexdigest()
    observation = _read_json(observation_path, "observacao de captura CEST")
    candidate_manifest = _read_json(candidates_path.with_name("manifest.json"), "manifesto de candidatos CEST")
    artifact_sha256 = _required_text(candidate_manifest, "artifact_sha256", "manifesto")
    if not _SHA256.fullmatch(artifact_sha256):
        raise ValueError("manifesto.artifact_sha256 invalido")
    if _required_text(candidate_manifest, "candidate_set_sha256", "manifesto") != candidate_set_sha256:
        raise ValueError("hash do snapshot diverge do manifesto CEST")
    if _required_text(candidate_manifest, "source_url", "manifesto") != CEST_SOURCE_URL:
        raise ValueError("URL do manifesto nao corresponde a fonte oficial CEST")
    if _required_text(candidate_manifest, "parser_id", "manifesto") != CEST_CANDIDATE_CONTRACT:
        raise ValueError("parser_id do manifesto fora do contrato")
    if _required_text(candidate_manifest, "contract_version", "manifesto") != CEST_CANDIDATE_CONTRACT:
        raise ValueError("contract_version do manifesto fora do contrato")
    if _required_text(candidate_manifest, "status", "manifesto") != "candidates_unresolved":
        raise ValueError("status do manifesto nao pode ser publicado")
    observation_artifact_sha = _required_text(observation, "artifact_sha256", "observacao")
    requested_url = _required_text(observation, "requested_url", "observacao")
    final_url = _required_text(observation, "final_url", "observacao")
    raw_path = _required_text(observation, "raw_path", "observacao")
    captured_at_raw = _required_text(observation, "captured_at", "observacao")
    if observation_artifact_sha != artifact_sha256:
        raise ValueError("observacao de captura nao corresponde ao artifact_sha256")
    if _required_text(observation, "contract_version", "observacao") != "confaz-cest-raw-v1":
        raise ValueError("contract_version da observacao fora do contrato de captura")
    if _required_text(observation, "source_authority", "observacao") != "CONFAZ":
        raise ValueError("source_authority da observacao nao e CONFAZ")
    if _required_text(observation, "status", "observacao") != "captured_raw_uninterpreted":
        raise ValueError("observacao nao tem status de captura bruta nao interpretada")
    try:
        captured_at = datetime.fromisoformat(captured_at_raw.replace("Z", "+00:00"))
        http_status = int(observation["http_status"])
        byte_size = int(observation["byte_size"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("status, tamanho ou captured_at da observacao CEST invalido") from None
    if captured_at.tzinfo is None or not 200 <= http_status < 300 or byte_size <= 0:
        raise ValueError("metadados temporais/HTTP/tamanho da observacao CEST invalidos")
    if requested_url != CEST_SOURCE_URL or not final_url.startswith("https://www.confaz.fazenda.gov.br/"):
        raise ValueError("URL solicitada/final fora da fonte oficial CEST")
    raw_file = (capture_root / raw_path).resolve()
    try:
        raw_file.relative_to(capture_root.resolve())
    except ValueError:
        raise ValueError("raw_path da observacao sai do diretorio de captura") from None
    try:
        raw_body = raw_file.read_bytes()
    except OSError as error:
        raise ValueError(f"artefato bruto CEST indisponivel: {error}") from None
    if hashlib.sha256(raw_body).hexdigest() != artifact_sha256:
        raise ValueError("hash do artefato bruto CEST diverge da observacao")
    if len(raw_body) != byte_size:
        raise ValueError("byte_size da observacao diverge do artefato bruto CEST")
    if hashlib.sha256(snapshot).hexdigest() != candidate_set_sha256:
        raise ValueError("hash do snapshot de candidatos CEST inconsistente")
    if cest_candidates_jsonl(parse_cest_candidates(raw_body), artifact_sha256) != snapshot:
        raise ValueError("snapshot CEST nao corresponde ao reprocessamento do artefato original")
    headers = observation.get("response_headers", {})
    if captured_at.tzinfo is None or not 200 <= http_status < 300 or byte_size <= 0:
        raise ValueError("metadados temporais/HTTP/tamanho da observacao CEST invalidos")
    if not isinstance(headers, dict) or not isinstance(headers.get("content-type"), str):
        raise ValueError("Content-Type ausente na observacao CEST")
    if headers["content-type"].split(";", maxsplit=1)[0].strip().lower() != "text/html":
        raise ValueError("Content-Type da observacao CEST nao e text/html")
    if not snapshot.endswith(b"\n"):
        raise ValueError("snapshot CEST ausente ou incompleto")
    try:
        records = [json.loads(line) for line in snapshot.decode("utf-8").splitlines()]
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("snapshot JSONL CEST invalido") from None
    if not records or any(not isinstance(record, dict) for record in records):
        raise ValueError("snapshot CEST vazio ou fora do contrato")
    expected_count = candidate_manifest.get("candidate_count")
    if expected_count != len(records):
        raise ValueError("candidate_count diverge do snapshot CEST")
    matched = unmatched = 0
    for record in records:
        if record.get("artifact_sha256") != artifact_sha256 or record.get("parser_id") != CEST_CANDIDATE_CONTRACT:
            raise ValueError("proveniencia de ocorrencia diverge do manifesto CEST")
        if record.get("legal_status") != "unresolved":
            raise ValueError("candidatos CEST devem permanecer unresolved")
        if not isinstance(record.get("source_context"), list) or not isinstance(record.get("source_cell_tags"), list):
            raise ValueError("contexto ou tags da ocorrencia CEST invalidos")
        if record.get("segment_name") is None:
            unmatched += 1
        else:
            matched += 1
    if matched != candidate_manifest.get("segment_matched_count") or unmatched != candidate_manifest.get(
        "segment_unmatched_count"
    ):
        raise ValueError("contagens de segmentos divergem do manifesto CEST")

    with connection.transaction():
        connection.execute("set local role tax_ingest_writer")
        connection.execute("set local statement_timeout = '60s'")
        connection.execute("set local lock_timeout = '5s'")
        connection.execute("select pg_advisory_xact_lock(hashtextextended(%s, 0))", ("contai:cest:stage",))
        connection.execute(
            """
            insert into tax_ingest.source_registry (
              source_key, agency, dataset_name, canonical_url, source_format,
              contract_version, parser_version, updated_at
            ) values (%s, %s, %s, %s, 'text/html', %s, %s, %s)
            on conflict (source_key) do update set updated_at = excluded.updated_at
            """,
            (
                _SOURCE_KEY,
                "CONFAZ",
                "Convenio ICMS 142/18 / candidatos CEST",
                CEST_SOURCE_URL,
                CEST_CANDIDATE_CONTRACT,
                CEST_CANDIDATE_CONTRACT,
                datetime.now(UTC),
            ),
        )
        connection.execute(
            """
            insert into tax_ingest.source_artifact (
              source_key, artifact_sha256, requested_url, final_url, captured_at,
              http_status, content_type, byte_size, raw_path, response_headers, status
            ) values (%s, %s, %s, %s, %s, %s, 'text/html', %s, %s, %s, 'accepted')
            on conflict (source_key, artifact_sha256) do nothing
            """,
            (
                _SOURCE_KEY,
                artifact_sha256,
                requested_url,
                final_url,
                captured_at,
                http_status,
                byte_size,
                raw_path,
                Jsonb(headers),
            ),
        )
        inserted = connection.execute(
            """
            insert into tax_ingest.cest_candidate_set (
              candidate_set_sha256, source_key, artifact_sha256, parser_id, contract_version,
              candidate_count, segment_matched_count, segment_unmatched_count, captured_at
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (candidate_set_sha256) do nothing
            returning candidate_set_sha256
            """,
            (
                candidate_set_sha256,
                _SOURCE_KEY,
                artifact_sha256,
                CEST_CANDIDATE_CONTRACT,
                CEST_CANDIDATE_CONTRACT,
                len(records),
                matched,
                unmatched,
                captured_at,
            ),
        ).fetchone()
        created = inserted is not None
        if created:
            for occurrence_number, record in enumerate(records, start=1):
                connection.execute(
                    """
                    insert into tax_ingest.cest_candidate (
                      candidate_set_sha256, occurrence_number, source_table_index, source_row_index,
                      item_label, cest_code, ncm_sh_raw, description, source_context, segment_code,
                      segment_name, source_cell_classes, source_cell_tags, legal_status
                    ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        candidate_set_sha256,
                        occurrence_number,
                        record["source_table_index"],
                        record["source_row_index"],
                        record["item_label"],
                        record["cest_code"],
                        record["ncm_sh_raw"],
                        record["description"],
                        Jsonb(record["source_context"]),
                        record["segment_code"],
                        record["segment_name"],
                        Jsonb(record["source_cell_classes"]),
                        Jsonb(record["source_cell_tags"]),
                        record["legal_status"],
                    ),
                )
        else:
            stored_row = connection.execute(
                "select count(*) from tax_ingest.cest_candidate where candidate_set_sha256 = %s",
                (candidate_set_sha256,),
            ).fetchone()
            if stored_row is None:
                raise ValueError("nao foi possivel confirmar o staging existente CEST")
            stored = stored_row[0]
            if stored != len(records):
                raise ValueError("staging existente diverge do snapshot imutavel CEST")
    return CestCandidateStageResult(candidate_set_sha256, len(records), created)
