"""Interface local, sem acesso a Supabase ou outros servicos persistentes."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from contai_tax_data.pipeline import capture_ncm
from contai_tax_data.source import SourceClient
from contai_tax_data.storage import result_as_dict


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="contai-tax-data")
    commands = parser.add_subparsers(dest="command", required=True)
    ncm = commands.add_parser("capture-ncm", help="captura a NCM oficial e cria uma release local")
    ncm.add_argument("--output", type=Path, default=Path("var/tax-data"))
    ncm.add_argument("--attempts", type=int, default=3)
    ncm.add_argument("--timeout", type=float, default=30.0, dest="timeout_seconds")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "capture-ncm":
        client = SourceClient(attempts=args.attempts, timeout_seconds=args.timeout_seconds)
        result = capture_ncm(args.output, client=client)
        print(json.dumps(result_as_dict(result), ensure_ascii=False, sort_keys=True))
        return 0
    raise AssertionError(f"comando nao tratado: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
