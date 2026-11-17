"""Prévia por padrão; aplica somente um JSON municipal arquivado e com hash conferido."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values
from scripts.completar_catalogo_osm import carregar_fonte
from scripts.importar_postos_osm import normalizar_entrada
from scripts.preparar_banco_novo import nome_banco
from scripts.revisar_osm import ler_arquivo, rejeitar_constante
from services.admin_reports import json_default
from services.database import config_from_mapping, get_db_connection
from services.migrations import load_migrations
from services.osm_online import ErroOSM, FalhaOSM, sincronizar, validar_data


def gravar(pasta, nome, dados):
    bruto = (json.dumps(dados, ensure_ascii=False, indent=2,
                        allow_nan=False, default=json_default) + "\n").encode("utf-8")
    descriptor = os.open(pasta / nome, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as arquivo:
        arquivo.write(bruto)
    return hashlib.sha256(bruto).hexdigest()


def preparar_fonte(arquivo, pasta, esperado=None):
    bruto = ler_arquivo(arquivo)
    sha = hashlib.sha256(bruto).hexdigest()
    if esperado is not None and sha != esperado.lower():
        raise ErroOSM("sha256_fonte_divergente")
    corpo = json.loads(bruto, parse_constant=rejeitar_constante)
    if not isinstance(corpo, dict) or not isinstance(corpo.get("elements"), list):
        raise ErroOSM("fonte_json_invalida")
    if len(corpo["elements"]) > 5000:
        raise ErroOSM("fonte_acima_do_limite")
    with (pasta / "fonte.json").open("xb") as destino:
        destino.write(bruto)
    # O segundo parser usa a cópia arquivada e confere exatamente o mesmo hash.
    fonte = carregar_fonte(pasta / "fonte.json", sha)
    # O schema usa DATETIME sem frações de segundo.
    fonte["data_base_utc"] = fonte["data_base_utc"].replace(microsecond=0)
    validar_data(fonte["data_base_utc"])
    lugares, descartados = normalizar_entrada(corpo)
    if not 1 <= len(lugares) <= 3000:
        raise ErroOSM("quantidade_de_postos_invalida")
    return fonte, lugares, descartados


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arquivo", required=True)
    parser.add_argument("--banco", required=True, type=nome_banco)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--saida", required=True, help="Pasta nova para fonte, backup e relatório.")
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--dry-run", action="store_true")
    modo.add_argument("--aplicar", action="store_true")
    parser.add_argument("--sha256", help="Hash da fonte revisada; obrigatório para aplicar.")
    args = parser.parse_args(argv)
    if args.aplicar and (not args.sha256 or not re.fullmatch(r"[0-9a-fA-F]{64}", args.sha256)):
        parser.error("--aplicar exige --sha256 com o hash da fonte revisada.")
    pasta, conn, hashes = Path(args.saida), None, {}
    etapa = "reservar_pasta"
    relatorio = {
        "iniciado_em_utc": datetime.now(timezone.utc).isoformat(),
        "modo": "aplicar" if args.aplicar else "dry-run",
        "atribuicao": "© OpenStreetMap contributors — ODbL",
        "licenca_url": "https://www.openstreetmap.org/copyright",
    }
    try:
        pasta.mkdir(parents=True, exist_ok=False)
    except Exception as erro:
        print(json.dumps({"status": "falha_preparacao", "erro_tipo": type(erro).__name__}))
        return 2
    try:
        etapa = "validar_fonte"
        fonte, lugares, descartados = preparar_fonte(args.arquivo, pasta, args.sha256)
        hashes["fonte.json"] = fonte["sha256"]
        relatorio.update(
            sha256_fonte=fonte["sha256"], municipio=fonte["municipio"],
            data_base_utc=fonte["data_base_utc"], descartados_na_leitura=descartados,
        )
        etapa = "configurar_conexao"
        if not Path(args.env_file).is_file():
            raise ErroOSM("arquivo_env_nao_encontrado")
        config = config_from_mapping(dotenv_values(args.env_file, interpolate=False))
        if config.database != args.banco:
            raise ErroOSM("banco_do_arquivo_env_divergente")
        migracoes = load_migrations(ROOT / "migrations")
        etapa = "conectar"
        conn = get_db_connection(config=config, read_only=not args.aplicar, time_zone="+00:00")

        def backup(dados):
            hashes["backup_metadados.json"] = gravar(pasta, "backup_metadados.json", dados)

        etapa = "sincronizar"
        relatorio.update(sincronizar(
            conn, fonte, lugares, migracoes, args.banco, args.aplicar, backup,
        ))
    except FalhaOSM as erro:
        relatorio.update(
            status="commit_incerto" if erro.commit_incerto else "interrompido",
            etapa=erro.etapa, erro_tipo=erro.tipo, erro_codigo=erro.codigo,
        )
    except Exception as erro:
        relatorio.update(
            status="interrompido", etapa=etapa, erro_tipo=type(erro).__name__,
            erro_codigo=str(erro) if isinstance(erro, ErroOSM) else None,
        )
    finally:
        if conn is not None:
            for acao in (conn.rollback, conn.close):
                try:
                    acao()
                except Exception as erro:
                    relatorio["falha_encerramento_tipo"] = type(erro).__name__
    relatorio["finalizado_em_utc"] = datetime.now(timezone.utc).isoformat()
    try:
        hashes["relatorio.json"] = gravar(pasta, "relatorio.json", relatorio)
        gravar(pasta, "manifesto.json", {"status": relatorio["status"], "sha256": hashes})
    except Exception as erro:
        print(json.dumps({"status": "falha_artefatos", "resultado_banco": relatorio["status"],
                          "erro_tipo": type(erro).__name__}))
        return 2
    resumo = {k: relatorio[k] for k in (
        "status", "modo", "banco", "sha256_fonte", "etapa", "erro_tipo", "erro_codigo",
        "metadados_planejados", "metadados_aplicados", "falha_encerramento_tipo",
    ) if k in relatorio}
    if "catalogo" in relatorio:
        resumo["catalogo"] = {k: relatorio["catalogo"][k] for k in (
            "novos", "existentes", "ambiguos", "ignorados", "inseridos", "vinculados",
        )}
    print(json.dumps({**resumo, "pasta": str(pasta)}, ensure_ascii=False, indent=2))
    return 0 if relatorio["status"] == "ok" and "falha_encerramento_tipo" not in relatorio else 1


if __name__ == "__main__":
    raise SystemExit(main())
