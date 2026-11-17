"""Executa ferramentas existentes no DESTINO sem trocar o .env ativo da aplicacao."""
from __future__ import annotations

import argparse
import os
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.admin_reports import emit_report
from services.transferencia_banco import (
    TransferError,
    close,
    connect,
    failure,
    load_profile,
    server,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "ferramenta",
        choices=("migracoes", "previa-limpeza"),
    )
    args, remaining = parser.parse_known_args(argv)

    conn = None
    try:
        config = load_profile("DESTINO")
        conn = connect(config, read_only=True)

        if "tidb" not in server(conn)["versao"].lower():
            raise TransferError(
                "O perfil DESTINO nao aponta para TiDB."
            )
    except Exception as exc:
        emit_report(
            failure(exc, "validar_perfil_destino")
        )
        return 1
    finally:
        close(conn)

    values = {
        "DATABASE_URL": "",
        "DB_HOST": config.host,
        "DB_PORT": str(config.port),
        "DB_USER": config.user,
        "DB_PASSWORD": config.password,
        "DB_NAME": config.database,
        "DB_SSL_CA": config.ca_file or "",
    }

    previous = {
        key: os.environ.get(key)
        for key in values
    }
    old_argv = sys.argv[:]
    file = (
        "migrar_banco.py"
        if args.ferramenta == "migracoes"
        else "previa_limpeza_precos.py"
    )

    try:
        os.environ.update(values)
        sys.argv = [
            str(ROOT / "scripts" / file),
            *remaining,
        ]
        runpy.run_path(
            sys.argv[0],
            run_name="__main__",
        )
        return 0

    finally:
        sys.argv = old_argv
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    raise SystemExit(main())