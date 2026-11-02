from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

import psycopg


def main() -> None:
    parser = argparse.ArgumentParser(description="Restaura um artefato bruto privado do Supabase por SHA-256.")
    parser.add_argument("source_key")
    parser.add_argument("artifact_sha256")
    parser.add_argument(
        "--output",
        type=Path,
        help="arquivo de destino (padrão: var/tax-data/archive/<source_key>/<sha256>.bin)",
    )
    args = parser.parse_args()
    if len(args.artifact_sha256) != 64 or any(char not in "0123456789abcdef" for char in args.artifact_sha256):
        raise SystemExit("artifact_sha256 deve conter 64 caracteres hexadecimais minúsculos")

    database_url = os.environ.get("CONTAI_DATABASE_URL")
    if not database_url:
        raise SystemExit("CONTAI_DATABASE_URL ausente")
    destination = args.output or (
        Path("var") / "tax-data" / "archive" / args.source_key / f"{args.artifact_sha256}.bin"
    )
    with psycopg.connect(database_url, connect_timeout=12) as connection, connection.transaction():
        connection.execute("set local role tax_ingest_writer")
        row = connection.execute(
            """
                select byte_size, raw_content
                from tax_ingest.source_artifact_payload
                where source_key = %s and artifact_sha256 = %s
                """,
            (args.source_key, args.artifact_sha256),
        ).fetchone()
    if row is None:
        raise SystemExit("payload não encontrado no arquivo privado do Supabase")
    byte_size, raw_content = row
    if len(raw_content) != byte_size or hashlib.sha256(raw_content).hexdigest() != args.artifact_sha256:
        raise SystemExit("payload do Supabase falhou na validação SHA-256/tamanho")

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.read_bytes() != raw_content:
        raise SystemExit("destino já existe com conteúdo diferente; nenhum arquivo foi sobrescrito")
    if not destination.exists():
        destination.write_bytes(raw_content)
    print(f"restored={destination} sha256={args.artifact_sha256} bytes={byte_size}")


if __name__ == "__main__":
    main()
