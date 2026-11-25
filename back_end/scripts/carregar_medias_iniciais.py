"""Carga explícita de referências estimadas; prévia por padrão."""

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.database import get_db_connection
from services.migrations import (
    MigrationError,
    load_migrations,
)
from services.referencias_medias import (
    ErroMedias,
    carregar_medias,
    carregar_snapshot,
)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--banco",
        required=True,
    )

    parser.add_argument(
        "--snapshot",
        required=True,
    )

    parser.add_argument(
        "--snapshot-sha256",
        required=True,
    )

    modo = parser.add_mutually_exclusive_group()

    modo.add_argument(
        "--dry-run",
        action="store_true",
    )

    modo.add_argument(
        "--aplicar",
        action="store_true",
    )

    args = parser.parse_args(argv)

    conn = None

    try:
        snapshot = carregar_snapshot(
            args.snapshot,
            args.snapshot_sha256,
        )

        migracoes = load_migrations(
            ROOT / "migrations"
        )

        conn = get_db_connection(
            read_only=not args.aplicar,
            time_zone="+00:00",
        )

        resultado = carregar_medias(
            conn,
            migracoes,
            snapshot,
            args.snapshot_sha256,
            banco=args.banco,
            aplicar=args.aplicar,
        )

        codigo = 0

    except Exception as erro:
        if isinstance(
            erro,
            (ErroMedias, MigrationError),
        ):
            mensagem = str(erro)
        else:
            mensagem = (
                "Falha na carga. "
                "Confira a prévia antes de repetir. "
                "Detalhes de conexão omitidos."
            )

        resultado = {
            "status": "interrompido",
            "erro_tipo": type(erro).__name__,
            "erro": mensagem,
        }

        codigo = 1

    finally:
        if conn is not None:
            conn.close()

    print(
        json.dumps(
            resultado,
            ensure_ascii=False,
            indent=2,
        )
    )

    return codigo


if __name__ == "__main__":
    raise SystemExit(main())