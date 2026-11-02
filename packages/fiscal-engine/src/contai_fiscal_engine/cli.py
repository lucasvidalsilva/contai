"""Interface local para demonstrar o motor sem expor o conteúdo da NF-e."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date
from pathlib import Path

from contai_fiscal_engine.catalog import load_ncm_catalog
from contai_fiscal_engine.engine import analyze_nfe


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analisa uma NF-e modelo 55 local e emite alertas em JSON.")
    parser.add_argument("xml", type=Path, help="caminho para um XML NF-e sintético ou autorizado pelo usuário")
    parser.add_argument(
        "--ncm-catalog",
        type=Path,
        help="manifesto contai-ncm-catalog-v1 previamente sincronizado",
    )
    return parser


def _json_default(value: object) -> str:
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"tipo não serializável: {type(value).__name__}")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        xml_bytes = args.xml.read_bytes()
        catalog = load_ncm_catalog(args.ncm_catalog.read_bytes()) if args.ncm_catalog else None
    except (OSError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2

    report = analyze_nfe(xml_bytes, catalog)
    print(json.dumps(asdict(report), default=_json_default, ensure_ascii=False, sort_keys=True))
    return 0 if report.status == "analyzed" else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
