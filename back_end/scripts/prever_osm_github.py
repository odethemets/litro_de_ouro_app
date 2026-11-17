"""Executa somente a prévia OSM usando credenciais temporárias do executor."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from dotenv import set_key

ROOT = Path(__file__).resolve().parents[1]
CAMPOS = ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME")


class ErroPrevia(ValueError):
    """Código controlado: não contém valores privados da configuração."""


def validar_fonte(arquivo, esperado):
    if not re.fullmatch(r"[0-9a-fA-F]{64}", esperado):
        raise ErroPrevia("sha256_esperado_invalido")
    with Path(arquivo).open("rb") as stream:
        bruto = stream.read(16 * 1024 * 1024 + 1)
    if not bruto or len(bruto) > 16 * 1024 * 1024:
        raise ErroPrevia("tamanho_da_fonte_invalido")
    if hashlib.sha256(bruto).hexdigest() != esperado.lower():
        raise ErroPrevia("sha256_da_fonte_divergente")


def configurar(pasta, env, banco):
    if any(not isinstance(env.get(k), str) or not env[k].strip() for k in CAMPOS):
        raise ErroPrevia("credenciais_osm_incompletas")
    if env["DB_NAME"].strip() != banco:
        raise ErroPrevia("banco_configurado_divergente")
    dados = {k: env[k] for k in CAMPOS}
    # A CA é opcional. Sem ela, o driver verifica a identidade com as raízes do SO.
    pem = env.get("OSM_DB_CA_PEM", "")
    if pem.strip():
        ca = pasta / "ca.pem"
        with ca.open("x", encoding="utf-8") as stream:
            stream.write(pem)
        ca.chmod(0o600)
        dados["DB_SSL_CA"] = str(ca)
    caminho = pasta / "conexao.env"
    caminho.touch(mode=0o600, exist_ok=False)
    for campo, valor in dados.items():
        set_key(str(caminho), campo, valor, quote_mode="always")
    return caminho


def main(argv=None, env=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arquivo", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--banco", required=True)
    parser.add_argument("--saida", required=True)
    args = parser.parse_args(argv)
    etapa = "validar_fonte"
    try:
        validar_fonte(args.arquivo, args.sha256)
        etapa = "preparar_configuracao_temporaria"
        with tempfile.TemporaryDirectory(prefix="ldo-osm-conexao-") as temporaria:
            config = configurar(Path(temporaria), os.environ if env is None else env, args.banco)
            etapa = "executar_previa"
            resultado = subprocess.run(
                [
                    sys.executable, "-B", str(ROOT / "scripts/sincronizar_osm_online.py"),
                    "--arquivo", str(Path(args.arquivo).resolve()),
                    "--sha256", args.sha256.lower(), "--banco", args.banco,
                    "--env-file", str(config), "--dry-run",
                    "--saida", str(Path(args.saida).resolve()),
                ],
                check=False, timeout=300,
            )
            return resultado.returncode
    except Exception as erro:
        resumo = {
            "status": "interrompido", "etapa": etapa,
            "erro_tipo": type(erro).__name__, "gravacao_banco_habilitada": False,
        }
        if isinstance(erro, ErroPrevia):
            resumo["erro_codigo"] = str(erro)
        print(json.dumps(resumo, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
