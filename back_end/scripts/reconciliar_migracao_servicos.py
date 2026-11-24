"""Reconcilia somente o histórico da 005; nunca executa DDL ou recria tabelas."""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.database import get_db_connection
from services.migrations import (
    MigrationError, compatibility, inspect_schema,
    load_migrations, make_plan, validate_structure,
)

VERSAO = "005_solicitacoes_servicos"


def reconciliar(conn, migracoes, *, banco, sha256, aplicar=False):
    try:
        if not banco or not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise MigrationError("Informe banco e SHA-256 válidos.")

        alvo = [m for m in migracoes if m["versao"] == VERSAO]
        if (
            len(alvo) != 1
            or alvo[0]["sha256"] != sha256
            or len(alvo[0]["statements"]) != 1
        ):
            raise MigrationError(
                "A migração local diverge do hash esperado."
            )

        with conn.cursor() as cursor:
            servidor = compatibility(cursor)
            if servidor["banco"] != banco:
                raise MigrationError(
                    "Banco conectado diferente do esperado."
                )

            cursor.execute(
                "SELECT versao,sha256,estado,ultimo_passo,erro_tipo "
                "FROM schema_migrations ORDER BY versao"
                + (" FOR UPDATE" if aplicar else "")
            )
            linhas = cursor.fetchall()
            historico = {r["versao"]: r for r in linhas}

            if (
                len(historico) != len(linhas)
                or set(historico) != {m["versao"] for m in migracoes}
            ):
                raise MigrationError(
                    "Histórico ausente, duplicado ou desconhecido."
                )

            registro = historico[VERSAO]
            if registro["estado"] not in ("falhou", "aplicada"):
                raise MigrationError(
                    "Estado da 005 não permite reconciliação."
                )

            if (
                registro["ultimo_passo"] != 1
                or (
                    registro["estado"] == "falhou"
                    and registro["erro_tipo"] != "MigrationError"
                )
            ):
                raise MigrationError(
                    "A 005 não terminou o passo SQL esperado."
                )

            schema = inspect_schema(cursor)

            for migracao in migracoes:
                versao = migracao["versao"]
                linha = historico[versao]

                if linha["sha256"] != migracao["sha256"]:
                    raise MigrationError(
                        "Hash divergente no histórico: " + versao
                    )

                if versao != VERSAO and linha["estado"] != "aplicada":
                    raise MigrationError(
                        "Migração anterior não aplicada: " + versao
                    )

                validate_structure(cursor, schema, versao)

            anterior = registro["estado"]
            atualizar = aplicar and anterior == "falhou"

            if atualizar:
                cursor.execute(
                    """UPDATE schema_migrations
                       SET estado='aplicada',
                           aplicada_em=UTC_TIMESTAMP(),
                           erro_tipo=NULL
                       WHERE versao=%s
                         AND sha256=%s
                         AND estado='falhou'
                         AND ultimo_passo=1
                         AND erro_tipo='MigrationError'""",
                    (VERSAO, sha256),
                )
                if cursor.rowcount != 1:
                    raise MigrationError(
                        "Histórico mudou durante a reconciliação."
                    )

            if aplicar or anterior == "aplicada":
                plano = make_plan(cursor, migracoes)
                if any(m["estado"] != "aplicada" for m in plano):
                    raise MigrationError(
                        "Conferência final não aprovou o histórico."
                    )

        if atualizar:
            conn.commit()
        else:
            conn.rollback()

        return {
            "status": "ok",
            "banco": banco,
            "versao": VERSAO,
            "modo": "aplicar" if aplicar else "dry-run",
            "estado_anterior": anterior,
            "estrutura_validada": True,
            "historico_atualizado": atualizar,
            "ddl_executado": False,
        }

    except Exception:
        conn.rollback()
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--banco", required=True)
    parser.add_argument("--sha256", required=True)

    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--dry-run", action="store_true")
    modo.add_argument("--aplicar", action="store_true")
    args = parser.parse_args(argv)

    conn = None
    try:
        migracoes = load_migrations(ROOT / "migrations")
        conn = get_db_connection(
            read_only=not args.aplicar,
            time_zone="+00:00",
        )
        resultado = reconciliar(
            conn,
            migracoes,
            banco=args.banco,
            sha256=args.sha256,
            aplicar=args.aplicar,
        )
        codigo = 0

    except Exception as erro:
        resultado = {
            "status": "interrompido",
            "erro_tipo": type(erro).__name__,
            "erro": (
                str(erro)
                if isinstance(erro, MigrationError)
                else (
                    "Falha na operação. Confira o histórico antes de repetir; "
                    "detalhes de conexão omitidos."
                )
            ),
        }
        codigo = 1

    finally:
        if conn is not None:
            conn.close()

    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())