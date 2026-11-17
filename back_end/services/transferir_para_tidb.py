"""Transferencia pontual: previa por padrao, aplicacao apenas em schema TiDB vazio."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.admin_reports import emit_report
from services.transferencia_banco import failure, load_profile, transfer


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--aplicar", action="store_true")
    parser.add_argument("--banco-destino")
    parser.add_argument(
        "--pasta-backup",
        default=str(ROOT / "backups"),
    )
    parser.add_argument("--relatorio")
    args = parser.parse_args(argv)

    if args.aplicar and not args.banco_destino:
        parser.error(
            "--aplicar exige --banco-destino NOME_EXATO_DO_SCHEMA"
        )

    state = {
        "etapa": "configuracao",
        "modo": "aplicar" if args.aplicar else "dry-run",
    }

    try:
        report = transfer(
            load_profile("ORIGEM"),
            load_profile("DESTINO"),
            apply=args.aplicar,
            expected_database=args.banco_destino,
            backup_folder=args.pasta_backup,
            state=state,
        )
    except Exception as exc:
        report = {
            **state,
            **failure(exc, state["etapa"]),
        }

    try:
        emit_report(report, args.relatorio)
    except Exception as exc:
        emit_report({
            "status": "falha_relatorio",
            "erro_tipo": type(exc).__name__,
            "resultado_transferencia": report,
        })
        return 2

    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())