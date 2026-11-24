"""Prepara revendas individuais ANP para revisão. Não tem modo de gravação."""
import argparse
from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.anp.associacao import (
    ler_catalogo,
    ler_vinculos,
    validar_catalogo,
)
from services.anp.contrato import ErroANP, normalizar
from services.anp.fontes import ler_arquivo
from services.anp.preparacao import hash_json, preparar
from services.anp.relatorios import salvar_relatorios


def consultar_catalogo_banco():
    # Import tardio: sem esta opção, não importa conexão ou app.
    from services.database import get_db_connection

    conn = get_db_connection(
        read_only=True,
        time_zone="+00:00",
    )

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    nome,
                    endereco,
                    bairro,
                    cidade,
                    uf,
                    tipo_posto
                FROM postos
                ORDER BY id
                LIMIT 5001
                """
            )

            return validar_catalogo(cursor.fetchall())

    finally:
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument("--arquivo", required=True)

    parser.add_argument(
        "--saida",
        required=True,
        help="Pasta nova, que ainda não exista.",
    )

    parser.add_argument(
        "--fonte-url",
        required=True,
        help=(
            "URL oficial de revendas; declarada, "
            "sem download automático."
        ),
    )

    parser.add_argument(
        "--periodo-inicio",
        required=True,
        type=date.fromisoformat,
    )

    parser.add_argument(
        "--periodo-fim",
        required=True,
        type=date.fromisoformat,
    )

    parser.add_argument(
        "--data-referencia",
        type=date.fromisoformat,
        default=date.today(),
    )

    parser.add_argument("--uf", default="PB")

    recorte = parser.add_mutually_exclusive_group()

    recorte.add_argument(
        "--municipio",
        default="JOAO PESSOA",
    )

    recorte.add_argument(
        "--toda-uf",
        action="store_true",
    )

    catalogo = parser.add_mutually_exclusive_group()

    catalogo.add_argument(
        "--catalogo-json",
        help=(
            "Snapshot local dos postos, "
            "somente para sugestões/revisão."
        ),
    )

    catalogo.add_argument(
        "--consultar-banco",
        action="store_true",
        help=(
            "SELECT explícito; use credenciais "
            "somente de leitura."
        ),
    )

    parser.add_argument(
        "--vinculos",
        help=(
            "CSV de decisões humanas. "
            "Nunca aceita CNPJ truncado."
        ),
    )

    parser.add_argument(
        "--encoding",
        choices=("utf-8-sig", "cp1252"),
        default="utf-8-sig",
    )

    args = parser.parse_args(argv)

    try:
        if Path(args.saida).exists():
            raise ErroANP(
                "A pasta de saída já existe; escolha outra "
                "para preservar a revisão anterior."
            )

        fonte = ler_arquivo(
            args.arquivo,
            args.encoding,
        )

        municipio = (
            None
            if args.toda_uf
            else normalizar(args.municipio)
        )

        if not args.toda_uf and not municipio:
            raise ErroANP(
                "Município vazio. Use --toda-uf "
                "para o recorte estadual."
            )

        # Valida fonte/período antes da consulta opcional.
        plano = preparar(
            fonte,
            inicio=args.periodo_inicio,
            fim=args.periodo_fim,
            referencia=args.data_referencia,
            fonte_url=args.fonte_url,
            uf=args.uf,
            municipio=municipio,
        )

        postos = []
        sha_catalogo = None

        if args.catalogo_json:
            postos, sha_catalogo = ler_catalogo(
                args.catalogo_json
            )

        elif args.consultar_banco:
            postos = consultar_catalogo_banco()
            sha_catalogo = hash_json(postos)

        vinculos = {}
        sha_vinculos = None

        if args.vinculos:
            if not (
                args.catalogo_json
                or args.consultar_banco
            ):
                raise ErroANP(
                    "Informe um catálogo para conferir "
                    "as decisões de vínculo."
                )

            vinculos, sha_vinculos = ler_vinculos(
                args.vinculos,
                postos,
                args.data_referencia,
                normalizar(args.uf),
                municipio,
            )

        if postos or args.vinculos:
            plano = preparar(
                fonte,
                inicio=args.periodo_inicio,
                fim=args.periodo_fim,
                referencia=args.data_referencia,
                fonte_url=args.fonte_url,
                uf=args.uf,
                municipio=municipio,
                catalogo=postos,
                vinculos=vinculos,
                sha_catalogo=sha_catalogo,
                sha_vinculos=sha_vinculos,
            )

        resumo = salvar_relatorios(
            plano,
            args.saida,
        )

        print(
            json.dumps(
                {
                    "status": "ok",
                    "fase": resumo["fase"],
                    "resumo": resumo["resumo"],
                    "sha256_plano": resumo["sha256_plano"],
                    "apto_importacao": False,
                },
                ensure_ascii=False,
            )
        )

        return 0

    except (ErroANP, OSError) as erro:
        mensagem = (
            str(erro)
            if isinstance(erro, ErroANP)
            else "Não foi possível ler/escrever o arquivo local."
        )

        print(
            json.dumps(
                {
                    "status": "erro",
                    "error": mensagem,
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )

        return 2

    except Exception:
        print(
            json.dumps(
                {
                    "status": "erro",
                    "error": (
                        "Falha na consulta/preparação. "
                        "Confira o ambiente sem divulgar credenciais."
                    ),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )

        return 2


if __name__ == "__main__":
    raise SystemExit(main())