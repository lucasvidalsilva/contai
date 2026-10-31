"""Interface local, sem acesso a Supabase ou outros servicos persistentes."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

import psycopg

from contai_tax_data.pipeline import capture_ncm
from contai_tax_data.postgres import publish_ncm_release, stage_ncm_release
from contai_tax_data.postgres import result_as_dict as database_result_as_dict
from contai_tax_data.source import SourceClient
from contai_tax_data.storage import result_as_dict
from contai_tax_data.tipi import TIPI_ACCEPT
from contai_tax_data.tipi_storage import capture_tipi


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="contai-tax-data")
    commands = parser.add_subparsers(dest="command", required=True)
    ncm = commands.add_parser("capture-ncm", help="captura a NCM oficial e cria uma release local")
    ncm.add_argument("--output", type=Path, default=Path("var/tax-data"))
    ncm.add_argument("--attempts", type=int, default=3)
    ncm.add_argument("--timeout", type=float, default=30.0, dest="timeout_seconds")

    tipi = commands.add_parser("capture-tipi", help="captura a TIPI oficial XLSX e cria uma release local")
    tipi.add_argument("--output", type=Path, default=Path("var/tax-data"))
    tipi.add_argument("--attempts", type=int, default=3)
    tipi.add_argument("--timeout", type=float, default=30.0, dest="timeout_seconds")

    stage = commands.add_parser("stage-ncm", help="persiste uma release local no schema privado")
    stage.add_argument("--output", type=Path, default=Path("var/tax-data"))
    stage.add_argument("--release-id")

    publish = commands.add_parser("publish-ncm", help="publica atomicamente uma release NCM ja persistida")
    publish.add_argument("release_id")
    return parser


def _database_url() -> str:
    value = os.environ.get("CONTAI_DATABASE_URL")
    if not value:
        raise RuntimeError("CONTAI_DATABASE_URL nao configurada")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "capture-ncm":
        client = SourceClient(attempts=args.attempts, timeout_seconds=args.timeout_seconds)
        capture_result = capture_ncm(args.output, client=client)
        print(json.dumps(result_as_dict(capture_result), ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "capture-tipi":
        client = SourceClient(accept=TIPI_ACCEPT, attempts=args.attempts, timeout_seconds=args.timeout_seconds)
        tipi_result = capture_tipi(args.output / "tipi", client=client)
        print(json.dumps(asdict(tipi_result), ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "stage-ncm":
        with psycopg.connect(_database_url(), sslmode="require") as connection:
            stage_result = stage_ncm_release(connection, args.output, args.release_id)
        print(json.dumps(database_result_as_dict(stage_result), ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "publish-ncm":
        with psycopg.connect(_database_url(), sslmode="require") as connection:
            publication_result = publish_ncm_release(connection, args.release_id)
        print(json.dumps(database_result_as_dict(publication_result), ensure_ascii=False, sort_keys=True))
        return 0
    raise AssertionError(f"comando nao tratado: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
