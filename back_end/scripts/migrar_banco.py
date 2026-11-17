"""Previa por padrao. DDL somente com --aplicar e --banco explicitos."""
from __future__ import annotations

import argparse
import ssl
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.admin_reports import emit_report
from services.database import DatabaseConfigError, config_from_mapping, get_db_connection
from services.migrations import MigrationError, load_migrations, run


def diagnostico_erro(exc, etapa):
    """Retorna tipos e codigos; nunca serializa a mensagem original do driver."""
    chain, seen = [], set()
    current = exc

    while (
        current is not None
        and id(current) not in seen
        and len(chain) < 6
    ):
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__

    mysql_types = {
        "OperationalError",
        "ProgrammingError",
        "InternalError",
        "IntegrityError",
        "InterfaceError",
        "DataError",
        "NotSupportedError",
        "DatabaseError",
    }

    mysql_code = None
    os_code = None
    tls_code = None

    for error in chain:
        args = getattr(error, "args", ())
        if (
            mysql_code is None
            and type(error).__name__ in mysql_types
            and args
            and type(args[0]) is int
        ):
            mysql_code = args[0]

        if isinstance(error, OSError) and not isinstance(
            error, ssl.SSLError
        ):
            value = getattr(error, "winerror", None)
            if type(value) is not int:
                value = getattr(error, "errno", None)
            if os_code is None and type(value) is int:
                os_code = value

        value = getattr(error, "verify_code", None)
        if tls_code is None and type(value) is int:
            tls_code = value

    return {
        "erro_tipo": type(exc).__name__,
        "etapa": getattr(exc, "etapa_banco", etapa),
        "codigo_mysql": mysql_code,
        "causa_tipo": (
            type(chain[1]).__name__
            if len(chain) > 1
            else None
        ),
        "codigo_sistema": os_code,
        "falha_tls_detectada": (
            any(isinstance(e, ssl.SSLError) for e in chain)
            or mysql_code == 2026
        ),
        "codigo_verificacao_tls": tls_code,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Somente leitura; tambem e o padrao.",
    )
    mode.add_argument(
        "--aplicar",
        action="store_true",
        help="Aplica somente as migracoes pendentes.",
    )
    parser.add_argument(
        "--banco",
        help="Nome exato do banco esperado; obrigatorio com --aplicar.",
    )
    parser.add_argument(
        "--relatorio",
        help="Novo arquivo .json; arquivos existentes nao sao sobrescritos.",
    )
    parser.add_argument("--env-file", help="Arquivo de conexão separado, sem alterar o ambiente local.")
    args = parser.parse_args(argv)

    if args.aplicar and not args.banco:
        parser.error(
            "--aplicar exige --banco NOME_EXATO_DO_BANCO"
        )

    conn = None
    etapa = "carregar_migracoes"

    try:
        migrations = load_migrations(ROOT / "migrations")
        if args.relatorio:
            destino = Path(args.relatorio)
            if destino.exists() or destino.suffix.lower() != ".json":
                raise DatabaseConfigError("Escolha um arquivo .json novo para o relatório.")

        opcoes = {"read_only": not args.aplicar, "time_zone": "+00:00"}
        if args.env_file:
            from dotenv import dotenv_values
            etapa = "ler_configuracao_separada"
            if not Path(args.env_file).is_file():
                raise DatabaseConfigError("Arquivo de configuração separado não encontrado.")
            opcoes["config"] = config_from_mapping(
                dotenv_values(args.env_file, interpolate=False)
            )
        etapa = "abrir_conexao_e_sessao"
        conn = get_db_connection(**opcoes)

        etapa = "consultar_metadados_e_planejar"
        report = run(
            conn,
            migrations,
            apply=args.aplicar,
            expected_database=args.banco,
        )

    except (MigrationError, DatabaseConfigError) as exc:
        report = {
            "status": "interrompido",
            "erro": str(exc),
            "modo": "aplicar" if args.aplicar else "dry-run",
            **diagnostico_erro(exc, etapa),
        }

    except Exception as exc:
        report = {
            "status": "interrompido",
            **diagnostico_erro(exc, etapa),
            "erro": (
                "Falha ao ler arquivos ou acessar o banco; "
                "detalhes de conexao omitidos."
            ),
            "modo": "aplicar" if args.aplicar else "dry-run",
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
            "resultado_banco": report,
            "aviso": (
                "Confira o resultado_banco antes de repetir "
                "qualquer aplicacao."
            ),
        })
        return 2

    return (
        0
        if report.get("status") != "interrompido"
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())