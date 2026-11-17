"""Executor da prévia OSM, sem aplicação de alterações no banco."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.database import config_from_mapping, tls_context

LIMITE_EXECUCAO = 300
MAX_CA_BYTES = 128 * 1024

CAMPOS_BANCO = (
    "DB_HOST",
    "DB_PORT",
    "DB_USER",
    "DB_PASSWORD",
    "DB_NAME",
    "DB_SSL_CA",
)


class ErroJob(ValueError):
    """Código público que não contém valores de configuração."""


def nome_banco(valor):
    if (
        not 1 <= len(valor) <= 64
        or valor != valor.strip()
        or any(ord(c) < 32 or ord(c) == 127 for c in valor)
    ):
        raise argparse.ArgumentTypeError(
            "Informe o nome exato do banco."
        )
    return valor


# Configura o subprocesso sem alterar o ambiente do servidor.
def preparar_ambiente(origem, banco, temporario):
    ambiente = dict(origem)
    ambiente["PYTHONIOENCODING"] = "utf-8"
    ambiente["DATABASE_URL"] = ""
    ambiente["OSM_SYNC_ENABLED"] = "false"
    ambiente["OSM_SYNC_APPLY"] = "false"

    pem = ambiente.pop("OSM_DB_CA_PEM", "")

    if banco is None:
        for campo in CAMPOS_BANCO:
            ambiente[campo] = ""
        return ambiente

    if origem.get("DATABASE_URL", "").strip():
        raise ErroJob("use_campos_db_separados")

    # Sem PEM explícito, utiliza as raízes TLS do sistema.
    ambiente["DB_SSL_CA"] = ""

    try:
        config = config_from_mapping(ambiente)
    except ValueError:
        raise ErroJob("configuracao_banco_invalida") from None

    if config.database != banco:
        raise ErroJob("banco_configurado_divergente")

    if pem.strip():
        if (
            len(pem.encode("utf-8")) > MAX_CA_BYTES
            or "PRIVATE KEY" in pem
        ):
            raise ErroJob("ca_pem_invalida")

        caminho = Path(temporario) / "osm-ca.pem"
        descriptor = os.open(
            caminho,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )

        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
        ) as arquivo:
            arquivo.write(pem.strip() + "\n")

        ambiente["DB_SSL_CA"] = str(caminho)

    try:
        tls_context(config_from_mapping(ambiente))
    except ValueError:
        raise ErroJob("ca_tls_invalida") from None

    return ambiente


# Lista de argumentos fixa, executada sem interpretação pelo shell.
def montar_comando(args):
    comando = [
        sys.executable,
        "-B",
        str(ROOT / "scripts/revisar_osm.py"),
    ]

    if args.arquivo:
        comando.extend(("--arquivo", args.arquivo))
    else:
        comando.append("--joao-pessoa")

    if args.banco is None:
        comando.append("--somente-fonte")
    else:
        comando.extend(("--banco", args.banco))

    comando.extend((
        "--saida",
        args.saida,
        "--tentativas",
        "2",
        "--max-espera",
        "60",
    ))

    return comando


def emitir(status, **dados):
    print(
        json.dumps({
            "executor": "osm_previa",
            "status": status,
            "gravacao_habilitada": False,
            **dados,
        }, ensure_ascii=False),
        flush=True,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--saida",
        required=True,
        help="Pasta nova dos artefatos.",
    )
    parser.add_argument(
        "--arquivo",
        help="Opcional: teste com fonte já salva.",
    )
    parser.add_argument(
        "--banco",
        type=nome_banco,
        help="Comparar com este banco exato.",
    )

    args = parser.parse_args(argv)

    try:
        # O certificado fica fora da pasta publicada como artefato.
        with tempfile.TemporaryDirectory(
            prefix="ldo-osm-tls-",
            dir=os.getenv("RUNNER_TEMP") or None,
        ) as temporario:
            ambiente = preparar_ambiente(
                os.environ,
                args.banco,
                temporario,
            )

            resultado = subprocess.run(
                montar_comando(args),
                env=ambiente,
                check=False,
                shell=False,
                timeout=LIMITE_EXECUCAO,
            )

        codigo = resultado.returncode

        emitir(
            "executor_concluido" if codigo == 0 else "falha_previa",
            retorno=codigo,
        )
        return 0 if codigo == 0 else 1

    except ErroJob as erro:
        emitir(
            "configuracao_invalida",
            erro_codigo=str(erro),
        )
        return 2

    except subprocess.TimeoutExpired:
        emitir(
            "tempo_limite",
            limite_segundos=LIMITE_EXECUCAO,
        )
        return 1

    except Exception as erro:
        emitir(
            "falha_executor",
            erro_tipo=type(erro).__name__,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())