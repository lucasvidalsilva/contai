"""Staging privado, reprocessavel e nao interpretativo de blocos legais oficiais."""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from contai_tax_data.confaz_act import CONFAZ_ACT_BLOCK_CONTRACT, extract_confaz_act_artifact
from contai_tax_data.federal_law import (
    LC214_BLOCK_PARSER_ID,
    LC214_RECORD_BLOCK_PARSER_ID,
    write_lc214_blocks,
    write_lc214_record_blocks,
)
from contai_tax_data.normative_capture import (
    LC_214_OFFICIAL_RECORDS,
    LC_214_SOURCE_URL,
    NORMATIVE_CAPTURE_CONTRACT,
    OFFICIAL_RECORD_CAPTURE_CONTRACT,
)
from contai_tax_data.postgres import archive_source_artifact_observation, archive_source_artifact_payload

_SOURCE_CONFIG = {
    CONFAZ_ACT_BLOCK_CONTRACT: {
        "source_key": "confaz-act-blocks",
        "agency": "Conselho Nacional de Política Fazendária",
        "dataset_name": "Atos CONFAZ referenciados por fontes oficiais",
        "canonical_url": "https://www.confaz.fazenda.gov.br/sitemap.xml.gz",
        "capture_contract": "confaz-html-act-raw-v1",
        "source_authority": "CONFAZ",
        "document_kind": "confaz_act",
    },
    LC214_BLOCK_PARSER_ID: {
        "source_key": "camara-lc214-current",
        "agency": "Câmara dos Deputados - Legislação Informatizada",
        "dataset_name": "Lei Complementar 214/2025 atualizada",
        "canonical_url": "https://www2.camara.leg.br/legin/fed/leicom/2025/leicomplementar-214-16-janeiro-2025-796905-normaatualizada-pl.html",
        "capture_contract": NORMATIVE_CAPTURE_CONTRACT,
        "source_authority": "Câmara dos Deputados - Legislação Informatizada",
        "document_kind": "current",
    },
    LC214_RECORD_BLOCK_PARSER_ID: {
        "source_key": "camara-lc214-records",
        "agency": "Câmara dos Deputados - Legislação Informatizada",
        "dataset_name": "Publicação, veto e promulgação da Lei Complementar 214/2025",
        "canonical_url": LC_214_SOURCE_URL,
        "capture_contract": OFFICIAL_RECORD_CAPTURE_CONTRACT,
        "source_authority": "Câmara dos Deputados - Legislação Informatizada",
        "document_kind": "original",
    },
}
_MARKER_KINDS = frozenset(
    {"article", "paragraph", "sole_paragraph", "roman_item", "letter_item", "numbered_item", "text"}
)


@dataclass(frozen=True, slots=True)
class LegalBlockStageResult:
    source_key: str
    artifact_sha256: str
    contract_version: str
    snapshot_sha256: str
    block_count: int
    block_set_created: bool


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} inválido: {error}") from None
    if not isinstance(value, dict):
        raise ValueError(f"{label} precisa ser um objeto JSON")
    return value


def _required_text(value: dict[str, Any], key: str, label: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError(f"{label}.{key} ausente ou inválido")
    return result


def _reprocess_snapshot(
    contract_version: str,
    record_id: str | None,
    artifact_path: Path,
    observation_path: Path,
) -> bytes:
    with tempfile.TemporaryDirectory(prefix="contai-legal-blocks-") as temporary:
        output_root = Path(temporary)
        if contract_version == CONFAZ_ACT_BLOCK_CONTRACT:
            result = extract_confaz_act_artifact(artifact_path, observation_path, output_root)
        elif contract_version == LC214_BLOCK_PARSER_ID:
            result = write_lc214_blocks(artifact_path, observation_path, output_root)
        elif contract_version == LC214_RECORD_BLOCK_PARSER_ID and record_id in LC_214_OFFICIAL_RECORDS:
            result = write_lc214_record_blocks(record_id, artifact_path, observation_path, output_root)
        else:
            raise ValueError("contrato/registro de blocos legais sem reprocessador cadastrado")
        return (output_root / str(result["snapshot_path"])).read_bytes()


def _validate_blocks(snapshot: bytes, expected_count: int, contract_version: str) -> list[tuple[Any, ...]]:
    if not snapshot.endswith(b"\n"):
        raise ValueError("snapshot JSONL de blocos legais incompleto")
    try:
        objects = [json.loads(line) for line in snapshot.decode("utf-8").splitlines()]
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("snapshot JSONL de blocos legais inválido") from None
    if not objects or len(objects) != expected_count or any(not isinstance(value, dict) for value in objects):
        raise ValueError("block_count do manifesto diverge do snapshot legal")

    rows: list[tuple[Any, ...]] = []
    seen_indices: set[int] = set()
    for block in objects:
        index = block.get("source_block_index")
        source_tag = block.get("source_tag")
        source_class = block.get("source_class")
        text = block.get("text")
        marker_kind = block.get("marker_kind")
        marker = block.get("marker")
        if (
            not isinstance(index, int)
            or isinstance(index, bool)
            or index < 0
            or index in seen_indices
            or source_tag not in {"p", "td", "th"}
            or (source_class is not None and not isinstance(source_class, str))
            or (marker_kind is not None and marker_kind not in _MARKER_KINDS)
            or (marker is not None and not isinstance(marker, str))
            or (marker_kind is None and marker is not None)
            or not isinstance(text, str)
            or not text.strip()
        ):
            raise ValueError("bloco legal fora do contrato estrutural")
        if contract_version == CONFAZ_ACT_BLOCK_CONTRACT and (marker_kind is not None or marker is not None):
            raise ValueError("bloco CONFAZ não pode receber marcador jurídico inferido")
        seen_indices.add(index)
        rows.append((index, source_tag, source_class, marker_kind, marker, text))
    rows.sort(key=lambda row: row[0])
    return rows


def stage_legal_blocks(
    connection: Connection[Any],
    artifact_path: Path,
    observation_path: Path,
    manifest_path: Path,
    snapshot_path: Path,
    capture_root: Path,
) -> LegalBlockStageResult:
    """Valida proveniência e reprocessamento antes de gravar blocos no schema privado."""
    manifest = _read_object(manifest_path, "manifesto de blocos legais")
    observation = _read_object(observation_path, "observação de captura legal")
    contract_version = _required_text(manifest, "contract_version", "manifesto")
    config = _SOURCE_CONFIG.get(contract_version)
    if config is None:
        raise ValueError("contract_version de blocos legais não cadastrado")
    source_key = str(config["source_key"])
    artifact = artifact_path.read_bytes()
    snapshot = snapshot_path.read_bytes()
    artifact_sha256 = hashlib.sha256(artifact).hexdigest()
    snapshot_sha256 = hashlib.sha256(snapshot).hexdigest()
    if (
        manifest.get("artifact_sha256") != artifact_sha256
        or manifest.get("snapshot_sha256") != snapshot_sha256
        or manifest.get("interpretation_status") != "not_performed"
    ):
        raise ValueError("hash ou estado de interpretação do manifesto diverge dos artefatos")
    if observation.get("artifact_sha256") != artifact_sha256:
        raise ValueError("observação legal não corresponde ao hash do bruto")
    if observation.get("contract_version") != config["capture_contract"]:
        raise ValueError("contrato de captura da observação legal diverge da fonte")
    if (
        observation.get("source_authority") != config["source_authority"]
        or manifest.get("source_authority") != config["source_authority"]
        or observation.get("http_status") != 200
    ):
        raise ValueError("autoridade/status HTTP da observação legal inválido")
    requested_url = _required_text(observation, "requested_url", "observação")
    if manifest.get("source_url") != requested_url or observation.get("final_url") != requested_url:
        raise ValueError("URL solicitada/final diverge do manifesto legal")
    if contract_version == CONFAZ_ACT_BLOCK_CONTRACT:
        if not requested_url.startswith("https://www.confaz.fazenda.gov.br/"):
            raise ValueError("URL de ato CONFAZ fora do domínio oficial")
    elif contract_version == LC214_RECORD_BLOCK_PARSER_ID:
        record_id = observation.get("source_record_id")
        if record_id not in LC_214_OFFICIAL_RECORDS or LC_214_OFFICIAL_RECORDS[record_id][0] != requested_url:
            raise ValueError("registro LC 214 não corresponde à URL oficial cadastrada")
    elif requested_url != config["canonical_url"]:
        raise ValueError("URL LC 214 diverge da fonte oficial cadastrada")

    try:
        capture_root_resolved = capture_root.resolve()
        raw_path = artifact_path.resolve().relative_to(capture_root_resolved).as_posix()
        artifact_path.resolve().relative_to(capture_root_resolved)
    except ValueError:
        raise ValueError("artefato bruto legal fora da raiz de captura") from None
    if observation.get("raw_path") != raw_path or len(artifact) != observation.get("byte_size"):
        raise ValueError("raw_path/tamanho do bruto diverge da observação legal")
    headers = observation.get("response_headers")
    content_type = headers.get("content-type", "") if isinstance(headers, dict) else ""
    if "text/html" not in content_type.lower() or "charset=utf-8" not in content_type.lower().replace(" ", ""):
        raise ValueError("observação legal não confirma HTML UTF-8")

    captured_at_raw = _required_text(observation, "captured_at", "observação")
    try:
        captured_at = datetime.fromisoformat(captured_at_raw.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("captured_at da observação legal inválido") from None
    if captured_at.tzinfo is None:
        raise ValueError("captured_at da observação legal precisa ter timezone")
    captured_at = captured_at.astimezone(UTC)

    record_id = observation.get("source_record_id") if contract_version == LC214_RECORD_BLOCK_PARSER_ID else None
    reproduced = _reprocess_snapshot(contract_version, record_id, artifact_path, observation_path)
    if reproduced != snapshot:
        raise ValueError("snapshot legal diverge do reprocessamento do artefato original")
    block_count = manifest.get("block_count")
    if not isinstance(block_count, int) or isinstance(block_count, bool) or block_count <= 0:
        raise ValueError("manifesto legal.block_count inválido")
    blocks = _validate_blocks(snapshot, block_count, contract_version)
    source_lastmod = manifest.get("source_lastmod")
    if source_lastmod is not None and not isinstance(source_lastmod, str):
        raise ValueError("source_lastmod deve permanecer texto literal")

    document_kind = str(config["document_kind"])
    if contract_version == LC214_RECORD_BLOCK_PARSER_ID:
        document_kind = str(record_id)
    snapshot_key = (source_key, artifact_sha256, contract_version)
    source_registry_values = (
        source_key,
        str(config["agency"]),
        str(config["dataset_name"]),
        str(config["canonical_url"]),
        "text/html; charset=utf-8",
        contract_version,
        contract_version,
    )
    source_artifact_values = (
        source_key,
        artifact_sha256,
        requested_url,
        requested_url,
        captured_at,
        200,
        content_type,
        len(artifact),
        raw_path,
        Jsonb(headers),
    )

    with connection.transaction():
        connection.execute("set local role tax_ingest_writer")
        connection.execute("set local statement_timeout = '60s'")
        connection.execute("set local lock_timeout = '5s'")
        connection.execute(
            "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
            ("contai:legal-blocks:" + ":".join(snapshot_key),),
        )
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
            (*source_registry_values, datetime.now(UTC)),
        )
        connection.execute(
            """
            insert into tax_ingest.source_artifact (
              source_key, artifact_sha256, requested_url, final_url, captured_at,
              http_status, content_type, byte_size, raw_path, response_headers, status
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'accepted')
            on conflict (source_key, artifact_sha256) do nothing
            """,
            source_artifact_values,
        )
        archive_source_artifact_payload(connection, source_key, artifact_sha256, artifact)
        archive_source_artifact_observation(
            connection,
            source_key,
            artifact_sha256,
            captured_at=captured_at,
            requested_url=requested_url,
            final_url=requested_url,
            http_status=200,
            content_type=content_type,
            byte_size=len(artifact),
            response_headers={str(key): str(value) for key, value in headers.items()},
        )
        stored_artifact = connection.execute(
            """
            select requested_url, final_url, http_status, content_type,
                   byte_size, raw_path, status
            from tax_ingest.source_artifact
            where source_key = %s and artifact_sha256 = %s
            """,
            (source_key, artifact_sha256),
        ).fetchone()
        if stored_artifact != (
            requested_url,
            requested_url,
            200,
            content_type,
            len(artifact),
            raw_path,
            "accepted",
        ):
            raise ValueError("source_artifact existente diverge da captura legal verificada")

        inserted_set = connection.execute(
            """
            insert into tax_ingest.legal_block_set (
              source_key, artifact_sha256, contract_version, snapshot_sha256,
              source_url, document_kind, source_lastmod, captured_at, block_count
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (source_key, artifact_sha256, contract_version) do nothing
            returning source_key
            """,
            (
                source_key,
                artifact_sha256,
                contract_version,
                snapshot_sha256,
                requested_url,
                document_kind,
                source_lastmod,
                captured_at,
                block_count,
            ),
        ).fetchone()
        stored_set = connection.execute(
            """
            select snapshot_sha256, source_url, document_kind, source_lastmod,
                   block_count, interpretation_status
            from tax_ingest.legal_block_set
            where source_key = %s and artifact_sha256 = %s and contract_version = %s
            """,
            snapshot_key,
        ).fetchone()
        expected_set = (
            snapshot_sha256,
            requested_url,
            document_kind,
            source_lastmod,
            block_count,
            "not_performed",
        )
        if stored_set != expected_set:
            raise ValueError("conjunto legal existente diverge do snapshot imutável")

        with connection.cursor() as cursor:
            cursor.executemany(
                """
                insert into tax_ingest.legal_document_block (
                  source_key, artifact_sha256, contract_version, source_block_index,
                  source_tag, source_class, marker_kind, marker, block_text
                ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (source_key, artifact_sha256, contract_version, source_block_index) do nothing
                """,
                [(source_key, artifact_sha256, contract_version, *block) for block in blocks],
            )
        stored_blocks = connection.execute(
            """
            select source_block_index, source_tag, source_class, marker_kind, marker, block_text
            from tax_ingest.legal_document_block
            where source_key = %s and artifact_sha256 = %s and contract_version = %s
            order by source_block_index
            """,
            snapshot_key,
        ).fetchall()
        if stored_blocks != blocks:
            raise ValueError("blocos legais persistidos divergem do snapshot reproduzido")

    return LegalBlockStageResult(
        source_key=source_key,
        artifact_sha256=artifact_sha256,
        contract_version=contract_version,
        snapshot_sha256=snapshot_sha256,
        block_count=block_count,
        block_set_created=inserted_set is not None,
    )
