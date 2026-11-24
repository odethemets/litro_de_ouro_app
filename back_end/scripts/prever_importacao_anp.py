"""Reconstitui preparação ANP e gera prévia local; não tem modo de escrita."""
import argparse
from datetime import date
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.anp.associacao import (
    ler_auxiliar,
    ler_catalogo,
    ler_vinculos,
)
from services.anp.contrato import ErroANP
from services.anp.fontes import ler_arquivo
from services.anp.preparacao import preparar
from services.anp.previa_importacao import prever_importacao


def _objeto(pares):
    resultado = {}

    for chave, valor in pares:
        if chave in resultado:
            raise ErroANP("JSON com chaves repetidas.")

        resultado[chave] = valor

    return resultado


def ler_json(caminho):
    bruto, _ = ler_auxiliar(caminho)

    def constante(_):
        raise ErroANP("JSON contém número não finito.")

    try:
        return json.loads(
            bruto,
            object_pairs_hook=_objeto,
            parse_constant=constante,
        )
    except (ValueError, UnicodeDecodeError):
        raise ErroANP("Arquivo JSON inválido.") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument("--plano", required=True)
    parser.add_argument("--sha256-plano", required=True)
    parser.add_argument("--arquivo-fonte", required=True)
    parser.add_argument("--catalogo-json")
    parser.add_argument("--vinculos")

    parser.add_argument(
        "--snapshot-json",
        help="Auxiliar offline, não comprova estado vivo do banco.",
    )

    parser.add_argument(
        "--encoding",
        choices=("utf-8-sig", "cp1252"),
        default="utf-8-sig",
    )

    parser.add_argument(
        "--data-referencia",
        required=True,
        type=date.fromisoformat,
    )

    parser.add_argument(
        "--saida",
        required=True,
        help="Diretório novo, inexistente.",
    )

    args = parser.parse_args(argv)

    try:
        pasta = Path(args.saida)

        if pasta.exists():
            raise ErroANP(
                "Saída já existe; preserve a revisão anterior."
            )

        plano = ler_json(args.plano)

        # Validar hash/estrutura antes de usar os campos.
        prever_importacao(
            plano,
            sha256_plano_esperado=args.sha256_plano,
            referencia=args.data_referencia,
        )

        fonte = ler_arquivo(
            args.arquivo_fonte,
            args.encoding,
        )

        if fonte["sha256"] != plano["fonte"]["sha256"]:
            raise ErroANP(
                "Os bytes da fonte divergem da preparação."
            )

        catalogo = []
        sha_catalogo = None
        vinculos = {}
        sha_vinculos = None
        recorte = plano["recorte"]

        if args.catalogo_json:
            catalogo, sha_catalogo = ler_catalogo(
                args.catalogo_json
            )

        if args.vinculos:
            if not args.catalogo_json:
                raise ErroANP(
                    "Vínculos exigem catálogo local."
                )

            vinculos, sha_vinculos = ler_vinculos(
                args.vinculos,
                catalogo,
                args.data_referencia,
                recorte["uf"],
                recorte["municipio"],
            )

        reconstruido = preparar(
            fonte,
            inicio=date.fromisoformat(
                plano["periodo"]["inicio"]
            ),
            fim=date.fromisoformat(
                plano["periodo"]["fim"]
            ),
            referencia=args.data_referencia,
            fonte_url=plano["url_fonte_declarada"],
            uf=recorte["uf"],
            municipio=recorte["municipio"],
            catalogo=catalogo,
            vinculos=vinculos,
            sha_catalogo=sha_catalogo,
            sha_vinculos=sha_vinculos,
        )

        if reconstruido["sha256_plano"] != args.sha256_plano:
            raise ErroANP(
                "A reconstrução diverge; confira fonte, catálogo e vínculos."
            )

        snapshot = (
            ler_json(args.snapshot_json)
            if args.snapshot_json
            else None
        )

        previa = prever_importacao(
            reconstruido,
            sha256_plano_esperado=args.sha256_plano,
            referencia=args.data_referencia,
            snapshot=snapshot,
        )

        pasta.mkdir(parents=True, exist_ok=False)

        try:
            (pasta / "previa.json").write_text(
                json.dumps(
                    previa,
                    ensure_ascii=False,
                    indent=2,
                    allow_nan=False,
                ) + "\n",
                encoding="utf-8",
            )
        except BaseException:
            shutil.rmtree(pasta)
            raise

        print(
            json.dumps(
                {
                    "status": "ok",
                    "fase": previa["fase"],
                    "apto_importacao": False,
                    "resumo": previa["resumo"],
                    "sha256_previa": previa["sha256_previa"],
                },
                ensure_ascii=False,
            )
        )

        return 0

    except (ErroANP, OSError) as erro:
        mensagem = (
            str(erro)
            if isinstance(erro, ErroANP)
            else "Falha nos arquivos locais."
        )
    except Exception:
        mensagem = (
            "Preparação incompatível; confira os arquivos "
            "sem divulgar credenciais."
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


if __name__ == "__main__":
    raise SystemExit(main())