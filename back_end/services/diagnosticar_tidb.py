"""Testa TiDB; --testar-escrita usa somente tabelas descartaveis de diagnostico."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.admin_reports import emit_report
from services.diagnostico_tidb import diagnose
from services.transferencia_banco import failure, load_profile


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--somente-leitura", action="store_true")
    mode.add_argument("--testar-escrita", action="store_true")
    parser.add_argument("--relatorio")
    args = parser.parse_args(argv)

    try:
        report = diagnose(
            load_profile("DESTINO"),
            write=args.testar_escrita,
        )
    except Exception as exc:
        report = failure(
            exc,
            getattr(
                exc,
                "etapa_diagnostico",
                "configuracao_ou_conexao",
            ),
        )

    try:
        emit_report(report, args.relatorio)
    except Exception as exc:
        emit_report({
            "status": "falha_relatorio",
            "erro_tipo": type(exc).__name__,
            "resultado": report,
        })
        return 2

    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())