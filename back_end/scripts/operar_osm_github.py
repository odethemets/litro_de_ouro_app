"""Prepara, aplica ou confere OSM com backup previamente arquivado."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values

from scripts.completar_catalogo_osm import ler_estado
from scripts.prever_osm_github import configurar
from scripts.sincronizar_osm_online import gravar, preparar_fonte
from services.database import (
    config_from_mapping,
    get_db_connection,
)
from services.migrations import load_migrations
from services.operacao_osm import (
    ErroOperacao,
    assinatura_plano,
    canonico,
    minimizar_estado,
    validar_backup,
    validar_limites,
    verificar_artefato,
    verificar_historico,
)
from services.osm_online import FalhaOSM, sincronizar


def credenciais(env, escrita):
    prefixo = "OSM_WRITE_" if escrita else "OSM_"

    valores = {
        campo: env.get(prefixo + campo, "")
        for campo in (
            "DB_HOST",
            "DB_PORT",
            "DB_USER",
            "DB_PASSWORD",
            "DB_NAME",
        )
    }

    valores["OSM_DB_CA_PEM"] = env.get(
        prefixo + "DB_CA_PEM",
        "",
    )
    return valores


def definir_escrita(env):
    valor = env.get("OSM_APLICAR", "false")

    if valor not in ("true", "false"):
        raise ErroOperacao("modo_de_escrita_invalido")

    return valor == "true"


def limites(env):
    return (
        int(env.get("OSM_MAX_NOVOS") or "20"),
        int(env.get("OSM_MAX_METADADOS") or "1000"),
    )


def preparar(
    conn, fonte, lugares, migracoes, banco, pasta, escrita, env
):
    resultado = sincronizar(
        conn, fonte, lugares, migracoes, banco
    )

    if escrita:
        validar_limites(resultado, *limites(env))

    with conn.cursor() as cursor:
        postos, ofertas = ler_estado(cursor, fonte, False)

    dados = {
        "versao": 1,
        "capturado_em_utc": datetime.now(timezone.utc).isoformat(),
        "estado": minimizar_estado({
            "banco": banco,
            "fonte_sha256": fonte["sha256"],
            "postos": postos,
            "ofertas": ofertas,
        }),
        "previa": resultado,
    }

    sha = gravar(pasta, "backup_catalogo.json", dados)
    resultado["backup_sha256"] = sha

    if env.get("GITHUB_OUTPUT"):
        with Path(env["GITHUB_OUTPUT"]).open(
            "a", encoding="utf-8"
        ) as arquivo:
            arquivo.write("backup_sha256=" + sha + "\n")

    return resultado


def aplicar(
    conn, fonte, lugares, migracoes, banco,
    pasta, raiz, args, env
):
    if not definir_escrita(env):
        raise ErroOperacao("escrita_nao_habilitada")

    verificar_historico(env)
    verificar_artefato(env, args.artefato_backup)

    arquivo = raiz / "preparar/backup_catalogo.json"

    with arquivo.open("rb") as stream:
        bruto = stream.read(32 * 1024 * 1024 + 1)

    if len(bruto) > 32 * 1024 * 1024:
        raise ErroOperacao("backup_acima_do_limite")

    backup = validar_backup(
        bruto,
        args.backup_sha256,
        banco,
        fonte["sha256"],
    )

    validar_limites(backup["previa"], *limites(env))

    anterior = assinatura_plano(
        backup["previa"]["catalogo"],
        backup["previa"]["plano_metadados"],
        backup["estado"]["postos"],
    )

    def guardar_atual(dados):
        estado = minimizar_estado(dados)

        if canonico(estado) != canonico(backup["estado"]):
            raise ErroOperacao(
                "estado_mudou_apos_o_backup"
            )

        gravar(pasta, "backup_metadados.json", estado)

    def conferir_plano(catalogo, plano, postos):
        validar_limites(
            {
                "status": "ok",
                "catalogo": catalogo,
                "metadados_planejados": len(plano),
            },
            *limites(env),
        )

        if assinatura_plano(catalogo, plano, postos) != anterior:
            raise ErroOperacao(
                "plano_mudou_apos_a_previa"
            )

    return sincronizar(
        conn,
        fonte,
        lugares,
        migracoes,
        banco,
        True,
        guardar_atual,
        validar_plano=conferir_plano,
    )


def main(argv=None, env=None):
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--fase",
        choices=("preparar", "aplicar", "conferir"),
        required=True,
    )
    parser.add_argument("--backup-sha256")
    parser.add_argument("--artefato-backup")

    args = parser.parse_args(argv)
    env = os.environ if env is None else env

    conn = None
    pasta = None
    etapa = "validar_configuracao"

    resultado = {
        "status": "interrompido",
        "fase": args.fase,
    }

    try:
        escrita = definir_escrita(env)

        if args.fase == "aplicar" and not escrita:
            raise ErroOperacao("escrita_nao_habilitada")

        banco = env.get("OSM_BANCO_ESPERADO", "")

        if banco != "litro_de_ouro":
            raise ErroOperacao(
                "banco_esperado_deve_ser_litro_de_ouro"
            )

        if escrita:
            verificar_historico(env)

        raiz = Path(env["OSM_SAIDA"]).resolve()
        pasta = raiz / args.fase
        pasta.mkdir(parents=True, exist_ok=False)

        etapa = "validar_fonte"

        fonte, lugares, _ = preparar_fonte(
            env["OSM_FONTE_ARQUIVO"],
            pasta,
            env["OSM_FONTE_SHA256"],
        )

        etapa = "configurar_conexao"

        with tempfile.TemporaryDirectory(
            prefix="ldo-osm-operacao-"
        ) as temporaria:
            arquivo = configurar(
                Path(temporaria),
                credenciais(env, escrita),
                banco,
            )

            config = config_from_mapping(
                dotenv_values(arquivo, interpolate=False)
            )

            conn = get_db_connection(
                config=config,
                read_only=args.fase != "aplicar",
                time_zone="+00:00",
            )

            migracoes = load_migrations(
                ROOT / "migrations"
            )

            etapa = args.fase

            if args.fase == "preparar":
                resultado = preparar(
                    conn, fonte, lugares, migracoes,
                    banco, pasta, escrita, env,
                )

            elif args.fase == "aplicar":
                resultado = aplicar(
                    conn, fonte, lugares, migracoes,
                    banco, pasta, raiz, args, env,
                )

            else:
                resultado = sincronizar(
                    conn, fonte, lugares, migracoes, banco
                )

                if (
                    resultado["catalogo"]["novos"]
                    or resultado["metadados_planejados"]
                ):
                    raise ErroOperacao(
                        "conferencia_ainda_tem_alteracoes_pendentes"
                    )

        resultado.update(
            fase=args.fase,
            sha256_fonte=fonte["sha256"],
            atribuicao="© OpenStreetMap contributors — ODbL",
        )

    except FalhaOSM as erro:
        resultado = {
            "status": (
                "commit_incerto"
                if erro.commit_incerto
                else "interrompido"
            ),
            "fase": args.fase,
            "etapa": erro.etapa,
            "erro_tipo": erro.tipo,
            "erro_codigo": erro.codigo,
        }

    except Exception as erro:
        resultado = {
            "status": "interrompido",
            "fase": args.fase,
            "etapa": etapa,
            "erro_tipo": type(erro).__name__,
            "erro_codigo": (
                str(erro)
                if isinstance(erro, ErroOperacao)
                else None
            ),
        }

    finally:
        if conn is not None:
            for acao in (conn.rollback, conn.close):
                try:
                    acao()
                except Exception as erro:
                    resultado["falha_encerramento_tipo"] = (
                        type(erro).__name__
                    )

    try:
        if pasta is not None and pasta.is_dir():
            sha = gravar(
                pasta, "relatorio.json", resultado
            )
            gravar(
                pasta,
                "manifesto.json",
                {"relatorio_sha256": sha},
            )

    except Exception as erro:
        print(json.dumps({
            "status": "falha_artefatos",
            "resultado_banco": resultado["status"],
            "erro_tipo": type(erro).__name__,
        }))
        return 2

    campos = (
        "status",
        "fase",
        "etapa",
        "erro_tipo",
        "erro_codigo",
        "metadados_planejados",
        "metadados_aplicados",
    )

    print(json.dumps({
        chave: resultado[chave]
        for chave in campos
        if chave in resultado
    }))

    return (
        0
        if resultado["status"] == "ok"
        and "falha_encerramento_tipo" not in resultado
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())