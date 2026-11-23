"""Compara conectividade Overpass em até nove sondas."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.diagnostico_rede_overpass import (
    diagnosticar_rede,
    resumo_markdown,
)
from services.fontes_overpass import (
    ConfiguracaoOverpassInvalida,
)


def main(
    argv=None,
    env=None,
    diagnosticar=diagnosticar_rede,
):
    env = os.environ if env is None else env

    parser = argparse.ArgumentParser(
        description=__doc__
    )
    parser.add_argument(
        "--saida",
        required=True,
    )

    args = parser.parse_args(argv)
    pasta = Path(args.saida)

    try:
        pasta.mkdir(
            parents=True,
            exist_ok=False,
        )

        dados = diagnosticar(
            env,
            emitir=lambda registro: print(
                json.dumps(
                    registro,
                    ensure_ascii=False,
                ),
                flush=True,
            ),
        )

        resumo = resumo_markdown(dados)

        (pasta / "relatorio.json").write_text(
            json.dumps(
                dados,
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )

        (pasta / "resumo.md").write_text(
            resumo,
            encoding="utf-8",
        )

        if env.get("GITHUB_STEP_SUMMARY"):
            try:
                with Path(
                    env["GITHUB_STEP_SUMMARY"]
                ).open(
                    "a",
                    encoding="utf-8",
                ) as stream:
                    stream.write(resumo)
            except OSError:
                # O artefato mantém o resultado.
                pass

        print(
            json.dumps(
                {
                    chave: dados[chave]
                    for chave in (
                        "status",
                        "testes_realizados",
                        "banco_consultado",
                        "consulta_municipal_validada",
                    )
                },
                ensure_ascii=False,
            )
        )

        return (
            0
            if dados["status"]
            == "ha_resposta_minima_valida"
            else 2
        )

    except FileExistsError:
        codigo = "pasta_saida_ja_existe"
    except ConfiguracaoOverpassInvalida as erro:
        codigo = str(erro)
    except Exception:
        codigo = "falha_no_diagnostico_rede"

    print(
        json.dumps({
            "status": "interrompido",
            "codigo": codigo,
        }),
        file=sys.stderr,
    )

    return 2


if __name__ == "__main__":
    raise SystemExit(main())