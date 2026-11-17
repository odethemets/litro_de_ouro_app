"""Lista dados de teste e reset futuro de karma. Nao implementa limpeza."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.admin_reports import emit_report
from services.database import DatabaseConfigError, get_db_connection


def build_preview(conn, expected_database=None):
    with conn.cursor() as cursor:
        cursor.execute("SELECT DATABASE() AS banco")
        database = cursor.fetchone()["banco"]

        if (
            expected_database
            and expected_database != database
        ):
            raise DatabaseConfigError(
                "--banco nao corresponde ao banco conectado."
            )

        cursor.execute(
            """
            SELECT
                id,
                posto_id,
                usuario_id,
                tipo_combustivel,
                preco,
                confianca_score,
                data_registro,
                (
                    foto_url IS NOT NULL
                    AND foto_url <> ''
                ) AS tem_foto
            FROM registos_preco
            ORDER BY id
            """
        )
        prices = cursor.fetchall()

        cursor.execute(
            """
            SELECT
                id,
                registo_id,
                usuario_id,
                tipo_voto,
                created_at
            FROM votos_registos
            ORDER BY id
            """
        )
        votes = cursor.fetchall()

        cursor.execute(
            "SELECT id,karma FROM usuarios ORDER BY id"
        )
        users = cursor.fetchall()

        cursor.execute(
            "SELECT COUNT(*) AS quantidade FROM postos"
        )
        stations = cursor.fetchone()["quantidade"]

    ids = {row["id"] for row in prices}

    related = [
        vote
        for vote in votes
        if vote["registo_id"] in ids
    ]

    orphans = [
        vote
        for vote in votes
        if vote["registo_id"] not in ids
    ]

    karma = [
        {
            "usuario_id": user["id"],
            "karma_atual": user["karma"],
            "karma_planejado_no_lancamento": 0,
        }
        for user in users
    ]

    return {
        "status": "ok",
        "modo": "dry-run",
        "gravacoes_no_banco": False,
        "gerado_em_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "banco": database,
        "selecao": (
            "Todos os precos presentes nesta previa; "
            "revisar estes IDs antes de qualquer limpeza futura."
        ),
        "politica_precos": (
            "pendente: exclusao ou arquivamento"
        ),
        "politica_votos": (
            "pendente; exclusao fisica de preco "
            "tem cascata no esquema atual"
        ),
        "reset_karma": (
            "planejado para o lancamento; nao executado"
        ),
        "datas_historicas": (
            "DATETIME sem fuso; "
            "nao foram convertidas ou regravadas"
        ),
        "fuso_votos_created_at": (
            "UTC: TIMESTAMP lido com sessao +00:00"
        ),
        "resumo": {
            "precos_de_teste": len(prices),
            "votos_associados": len(related),
            "votos_sem_preco_correspondente": len(orphans),
            "postos_com_precos": len({
                row["posto_id"]
                for row in prices
            }),
            "postos_preservados": stations,
            "usuarios_preservados": len(users),
            "usuarios_com_karma_diferente_de_zero_ou_nulo": sum(
                user["karma"] != 0
                for user in users
            ),
        },
        "precos": prices,
        "votos_associados": related,
        "votos_sem_preco_correspondente": orphans,
        "karma_previsto": karma,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Somente leitura, inclusive quando omitido.",
    )
    parser.add_argument(
        "--banco",
        help="Nome do banco esperado; a previa para se nao corresponder.",
    )
    parser.add_argument(
        "--relatorio",
        help="Novo arquivo .json. Nao sobrescreve arquivos existentes.",
    )
    args = parser.parse_args(argv)

    conn = None

    try:
        conn = get_db_connection(
            read_only=True,
            time_zone="+00:00",
        )
        report = build_preview(conn, args.banco)

    except DatabaseConfigError as exc:
        report = {
            "status": "falha",
            "modo": "dry-run",
            "erro": str(exc),
        }

    except Exception as exc:
        report = {
            "status": "falha",
            "modo": "dry-run",
            "erro_tipo": type(exc).__name__,
            "erro": (
                "Nao foi possivel gerar a previa; "
                "detalhes de conexao omitidos."
            ),
        }

    finally:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass

    try:
        emit_report(report, args.relatorio)

    except Exception as exc:
        emit_report({
            "status": "falha_relatorio",
            "erro_tipo": type(exc).__name__,
            "gravacoes_no_banco": False,
        })
        return 2

    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())