"""Exporta pendências para revisão humana; não conecta ao banco."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re


CAMPOS = (
    "id_externo",
    "categoria",
    "nome_fonte",
    "latitude",
    "longitude",
    "url_osm",
    "candidatos",
    "motivo",
    "decisao",
    "nome_confirmado",
    "evidencia",
    "observacoes",
)


def ler_json(arquivo):
    with Path(arquivo).open("rb") as stream:
        bruto = stream.read(32 * 1024 * 1024 + 1)

    if len(bruto) > 32 * 1024 * 1024:
        raise ValueError("arquivo_acima_do_limite")

    return json.loads(bruto), hashlib.sha256(bruto).hexdigest()


def gerar_linhas(relatorio, fonte):
    catalogo = relatorio.get(
        "catalogo",
        relatorio.get("previa", {}),
    )

    if (
        relatorio.get("status") != "ok"
        or not isinstance(catalogo.get("itens"), list)
    ):
        raise ValueError("relatorio_de_previa_invalido")

    elementos = {
        f"osm:{elemento.get('type')}:{elemento.get('id')}":
        elemento
        for elemento in fonte["elements"]
    }

    linhas = []

    for item in catalogo["itens"]:
        if item["categoria"] not in ("ambiguos", "ignorados"):
            continue

        ident = item["id_externo"]

        correspondencia = re.fullmatch(
            r"osm:(node|way|relation):([1-9][0-9]*)",
            ident,
        )

        if not correspondencia or ident not in elementos:
            raise ValueError(
                "identificador_da_pendencia_invalido"
            )

        elemento = elementos[ident]
        centro = elemento.get("center", elemento)

        linhas.append({
            "id_externo": ident,
            "categoria": item["categoria"],
            "nome_fonte": item.get("nome", ""),
            "latitude": centro.get("lat", ""),
            "longitude": centro.get("lon", ""),
            "url_osm": (
                "https://www.openstreetmap.org/"
                + correspondencia[1]
                + "/"
                + correspondencia[2]
            ),
            "candidatos": json.dumps(
                item.get("candidatos", []),
                ensure_ascii=False,
            ),
            "motivo": item.get("motivo", ""),
            "decisao": "pendente",
            "nome_confirmado": "",
            "evidencia": "",
            "observacoes": "",
        })

    return linhas


def texto_csv(valor):
    # Evita interpretar nomes externos como fórmulas.
    if (
        isinstance(valor, str)
        and valor.lstrip().startswith(("=", "+", "-", "@"))
    ):
        return "'" + valor

    return valor


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument("--relatorio", required=True)
    parser.add_argument("--fonte", required=True)
    parser.add_argument("--saida", required=True)

    args = parser.parse_args(argv)

    try:
        relatorio, rel_sha = ler_json(args.relatorio)
        fonte, fonte_sha = ler_json(args.fonte)

        if relatorio.get("sha256_fonte") != fonte_sha:
            raise ValueError(
                "fonte_nao_corresponde_ao_relatorio"
            )

        linhas = gerar_linhas(relatorio, fonte)

        pasta = Path(args.saida)
        pasta.mkdir(parents=True, exist_ok=False)

        with (pasta / "revisao.csv").open(
            "x",
            encoding="utf-8-sig",
            newline="",
        ) as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=CAMPOS,
                delimiter=";",
            )
            writer.writeheader()

            writer.writerows(
                {
                    chave: texto_csv(valor)
                    for chave, valor in linha.items()
                }
                for linha in linhas
            )

        resumo = {
            "status": "ok",
            "gravacao_habilitada": False,
            "sha256_fonte": fonte_sha,
            "sha256_relatorio": rel_sha,
            "ambiguos": sum(
                linha["categoria"] == "ambiguos"
                for linha in linhas
            ),
            "ignorados": sum(
                linha["categoria"] == "ignorados"
                for linha in linhas
            ),
            "decisoes_preenchidas": 0,
            "decisoes": [
                {
                    "id_externo": linha["id_externo"],
                    "decisao": "pendente",
                }
                for linha in linhas
            ],
        }

        (pasta / "revisao.json").write_text(
            json.dumps(
                resumo,
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )

        print(json.dumps(
            {
                chave: valor
                for chave, valor in resumo.items()
                if chave != "decisoes"
            },
            ensure_ascii=False,
        ))

        return 0

    except Exception as erro:
        print(json.dumps({
            "status": "interrompido",
            "erro_tipo": type(erro).__name__,
            "erro_codigo": (
                str(erro)
                if isinstance(erro, ValueError)
                else None
            ),
        }))

        return 1


if __name__ == "__main__":
    raise SystemExit(main())