from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

import psycopg

from contai_tax_data.postgres import archive_source_artifact_payload


def collect_payloads(
    data_root: Path,
    artifacts: list[tuple[str, str, int]],
    allow_missing: set[str],
) -> tuple[list[tuple[str, str, bytes]], list[tuple[str, str]]]:
    wanted_hashes = {artifact_sha for _, artifact_sha, _ in artifacts}
    by_hash: dict[str, bytes] = {}
    for path in data_root.rglob("*"):
        if not path.is_file():
            continue
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if digest in wanted_hashes:
            by_hash.setdefault(digest, payload)

    missing = [(source_key, artifact_sha) for source_key, artifact_sha, _ in artifacts if artifact_sha not in by_hash]
    unexpected = [(source_key, digest) for source_key, digest in missing if digest not in allow_missing]
    if unexpected:
        detail = ", ".join(f"{source_key}:{artifact_sha}" for source_key, artifact_sha in unexpected)
        raise ValueError(f"artefatos sem payload local verificável: {detail}")

    result: list[tuple[str, str, bytes]] = []
    for source_key, artifact_sha, expected_size in artifacts:
        if artifact_sha not in by_hash:
            continue
        payload = by_hash[artifact_sha]
        if len(payload) != expected_size:
            raise ValueError(f"tamanho divergente para artefato {artifact_sha}")
        result.append((source_key, artifact_sha, payload))
    return result, missing


def main() -> None:
    parser = argparse.ArgumentParser(description="Arquiva brutos existentes na tabela privada tax_ingest.")
    parser.add_argument(
        "--data-dir", type=Path, default=Path(__file__).parents[3] / "var" / "tax-data", help="raiz dos brutos"
    )
    parser.add_argument("--apply", action="store_true", help="grava os payloads; sem isto apenas verifica")
    parser.add_argument(
        "--allow-missing-sha256", action="append", default=[], help="hash histórico sem bytes disponíveis"
    )
    args = parser.parse_args()

    database_url = os.environ.get("CONTAI_DATABASE_URL")
    if not database_url:
        raise SystemExit("CONTAI_DATABASE_URL ausente")
    with psycopg.connect(database_url, connect_timeout=12) as connection:
        connection.execute("begin read only")
        artifacts = connection.execute(
            "select source_key, artifact_sha256, byte_size from tax_ingest.source_artifact order by 1, 2"
        ).fetchall()
        payloads, missing = collect_payloads(args.data_dir, artifacts, set(args.allow_missing_sha256))
        connection.rollback()

        total_bytes = sum(len(payload) for _, _, payload in payloads)
        print(f"payloads_verificados={len(payloads)} bytes={total_bytes} aplicacao={args.apply}")
        print(f"artefatos_sem_bruto={len(missing)} hashes={','.join(digest for _, digest in missing)}")
        if not args.apply:
            return

        with connection.transaction():
            connection.execute("set local role tax_ingest_writer")
            connection.execute("set local statement_timeout = '120s'")
            for source_key, artifact_sha, payload in payloads:
                archive_source_artifact_payload(connection, source_key, artifact_sha, payload)
        print(f"payloads_arquivados={len(payloads)}")


if __name__ == "__main__":
    main()
