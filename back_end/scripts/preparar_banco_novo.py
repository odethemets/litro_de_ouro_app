"""Prévia da base inicial. Criação apenas em banco vazio e com hash confirmado."""
import argparse
import hashlib
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.admin_reports import emit_report
from services.database import config_from_mapping, get_db_connection
from services.migrations import compatibility, load_migrations, split_sql
from scripts.migrar_banco import diagnostico_erro

TABELAS_BASE = ("postos", "usuarios", "registos_preco", "votos_registos")
PROTEGIDOS = {"mysql", "sys", "information_schema", "performance_schema"}


class ErroPreparo(ValueError):
    """Mensagem controlada; não inclui detalhes de credenciais ou do driver."""


def nome_banco(valor):
    if (
        not 1 <= len(valor) <= 64
        or valor != valor.strip()
        or any(ord(c) < 32 or ord(c) == 127 for c in valor)
        or valor.lower() in PROTEGIDOS
    ):
        raise argparse.ArgumentTypeError("Informe o nome exato de um banco do aplicativo.")
    return valor


# Só aceita as quatro definições base; nunca executa os dados fictícios do Docker.
def carregar_base(caminho):
    texto = Path(caminho).read_text(encoding="utf-8-sig")
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    comandos = split_sql(texto)
    if len(comandos) != len(TABELAS_BASE):
        raise ErroPreparo("O SQL base deve conter somente quatro CREATE TABLE.")
    for tabela, sql in zip(TABELAS_BASE, comandos):
        padrao = r"CREATE\s+TABLE\s+`?" + re.escape(tabela) + r"`?\s*\("
        if not re.match(padrao, sql, re.I):
            raise ErroPreparo("Definição base inesperada; revise o SQL antes de continuar.")
    return comandos, hashlib.sha256(texto.encode("utf-8")).hexdigest()


# Não cria o database, não remove tabelas e não adota uma preparação parcial.
def preparar(conn, comandos, sha, banco, aplicar=False, sha_confirmado=None, progresso=None):
    progresso = {} if progresso is None else progresso
    if aplicar and sha_confirmado != sha:
        raise ErroPreparo("SHA256 da base não confere com a prévia revisada.")
    with conn.cursor() as cursor:
        # Conferir o destino antes de consultar compatibilidade ou executar DDL.
        cursor.execute("SELECT DATABASE() AS banco")
        destino = cursor.fetchone()
        if not isinstance(destino, dict) or destino.get("banco") != banco:
            raise ErroPreparo("A conexão não corresponde ao banco esperado.")
        servidor = compatibility(cursor)
        cursor.execute(
            "SELECT TABLE_NAME AS nome FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME"
        )
        existentes = cursor.fetchall()
        if existentes:
            raise ErroPreparo(
                "O banco já contém tabelas ou views. A preparação de banco novo foi recusada."
            )

    relatorio = {
        "status": "ok", "modo": "aplicar" if aplicar else "dry-run",
        **servidor, "banco_vazio_confirmado": True,
        "sha256_base": sha, "tabelas_planejadas": list(TABELAS_BASE),
        "tabelas_criadas": [], "dados_ficticios_incluidos": False,
        "migracoes_aplicadas": False, "ddl_tem_commit_implicito": True,
    }
    if not aplicar:
        return relatorio

    for tabela, sql in zip(TABELAS_BASE, comandos):
        progresso["ddl_iniciado"] = True
        with conn.cursor() as cursor:
            cursor.execute(sql)
        conn.commit()
        relatorio["tabelas_criadas"].append(tabela)
        progresso["tabelas_confirmadas"] = list(relatorio["tabelas_criadas"])

    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT TABLE_NAME AS nome FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME"
        )
        criadas = {r["nome"] for r in cursor.fetchall()}
        if criadas != set(TABELAS_BASE):
            raise ErroPreparo("A estrutura final divergiu; conferir o banco antes de repetir.")
        for tabela in TABELAS_BASE:
            cursor.execute("SELECT COUNT(*) AS quantidade FROM " + tabela)
            if cursor.fetchone()["quantidade"] != 0:
                raise ErroPreparo("A base recebeu dados durante a preparação; revisar o destino.")

    relatorio["base_vazia_criada"] = True
    return relatorio


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--banco", required=True, type=nome_banco)
    modos = parser.add_mutually_exclusive_group()
    modos.add_argument("--dry-run", action="store_true")
    modos.add_argument("--aplicar", action="store_true")
    parser.add_argument("--sha256-base", help="Hash exibido na prévia; obrigatório para aplicar.")
    parser.add_argument("--relatorio", help="Novo arquivo .json, sem sobrescrita.")
    parser.add_argument("--env-file", help="Configuração de conexão separada, sem alterar o ambiente local.")
    args = parser.parse_args(argv)
    if args.aplicar and not args.sha256_base:
        parser.error("--aplicar exige --sha256-base com o hash da prévia.")

    conn, etapa = None, "verificar_arquivos"
    progresso = {"ddl_iniciado": False, "tabelas_confirmadas": []}
    relatorio = None
    try:
        # Falhas de arquivos são detectadas antes de abrir a conexão.
        comandos, sha = carregar_base(ROOT / "docker/schema_base.sql")
        migracoes = load_migrations(ROOT / "migrations")
        if args.aplicar and args.sha256_base != sha:
            raise ErroPreparo("SHA256 da base divergente. Execute uma nova prévia.")
        if args.relatorio:
            caminho = Path(args.relatorio)
            if caminho.suffix.lower() != ".json" or caminho.exists():
                raise ErroPreparo("Escolha um arquivo .json novo para o relatório.")

        opcoes = {"read_only": not args.aplicar, "time_zone": "+00:00"}
        if args.env_file:
            from dotenv import dotenv_values
            etapa = "ler_configuracao_separada"
            if not Path(args.env_file).is_file():
                raise ErroPreparo("Arquivo de configuração separado não encontrado.")
            opcoes["config"] = config_from_mapping(
                dotenv_values(args.env_file, interpolate=False)
            )
        etapa = "conectar"
        conn = get_db_connection(**opcoes)
        etapa = "conferir_e_preparar_base"
        relatorio = preparar(
            conn, comandos, sha, args.banco, args.aplicar, args.sha256_base, progresso,
        )
        relatorio["migracoes_posteriores"] = [m["versao"] for m in migracoes]
    except Exception as erro:
        relatorio = {
            "status": "interrompido", "modo": "aplicar" if args.aplicar else "dry-run",
            **diagnostico_erro(erro, etapa),
            "erro": str(erro) if isinstance(erro, ErroPreparo) else
                "Preparação interrompida; detalhes de conexão omitidos.",
            "ddl_pode_ter_sido_aplicado": progresso["ddl_iniciado"],
            "tabelas_confirmadas_antes_da_falha": progresso["tabelas_confirmadas"],
        }
    finally:
        if conn is not None:
            for acao in (conn.rollback, conn.close):
                try:
                    acao()
                except Exception as erro:
                    relatorio = {
                        "status": "falha_encerramento", "resultado_banco": relatorio,
                        "erro_tipo": type(erro).__name__,
                    }
    try:
        emit_report(relatorio, args.relatorio)
    except Exception as erro:
        emit_report({
            "status": "falha_relatorio", "erro_tipo": type(erro).__name__,
            "resultado_banco": relatorio,
        })
        return 2
    return 0 if relatorio["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
