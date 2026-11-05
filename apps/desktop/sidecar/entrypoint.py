"""Entrada do sidecar empacotado para o aplicativo desktop."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

from contai_fiscal_engine.cli import main
from contai_fiscal_engine.engine import analyze_nfe


def _json_default(value: object) -> str:
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"tipo não serializável: {type(value).__name__}")


def _desktop_batch(paths: list[str]) -> int:
    if not paths:
        print("lote desktop vazio", file=sys.stderr)
        return 2

    for index, raw_path in enumerate(paths):
        try:
            payload = Path(raw_path).read_bytes()
        except OSError:
            print(f"falha ao ler item interno {index}", file=sys.stderr)
            return 2
        report = analyze_nfe(payload)
        line = {"index": index, "report": asdict(report)}
        print(json.dumps(line, default=_json_default, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--desktop-batch":
        raise SystemExit(_desktop_batch(sys.argv[2:]))
    raise SystemExit(main())
