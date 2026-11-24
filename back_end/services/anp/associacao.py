"""Sugestões não são vínculos. Exige decisões humanas explícitas."""
import csv
from difflib import SequenceMatcher
import hashlib
import io
import json
from pathlib import Path
import re

from .contrato import (
    ErroANP,
    cnpj_valido,
    data_iso,
    normalizar,
    texto,
)

MAX_AUXILIAR = 4 * 1024 * 1024


def ler_auxiliar(caminho):
    with Path(caminho).open("rb") as stream:
        bruto = stream.read(MAX_AUXILIAR + 1)

    if len(bruto) > MAX_AUXILIAR:
        raise ErroANP("Arquivo auxiliar acima de 4 MiB.")

    return bruto, hashlib.sha256(bruto).hexdigest()


def validar_catalogo(dados):
    if not isinstance(dados, list) or len(dados) > 5000:
        raise ErroANP(
            "Catálogo deve ser uma lista com até 5000 postos."
        )

    vistos = set()
    saida = []

    for p in dados:
        if (
            not isinstance(p, dict)
            or type(p.get("id")) is not int
            or not 1 <= p["id"] <= 2147483647
            or p["id"] in vistos
        ):
            raise ErroANP(
                "Identificador duplicado ou inválido no catálogo."
            )

        # Somente informações públicas necessárias à revisão.
        item = {
            k: texto(p.get(k))
            for k in (
                "nome",
                "endereco",
                "bairro",
                "cidade",
                "uf",
                "tipo_posto",
            )
        }

        if (
            not item["nome"]
            or not item["endereco"]
            or any(len(v) > 500 for v in item.values())
        ):
            raise ErroANP(
                "Posto sem nome/endereço ou com texto acima do limite."
            )

        vistos.add(p["id"])
        saida.append(dict(item, id=p["id"]))

    return sorted(saida, key=lambda p: p["id"])


def ler_catalogo(caminho):
    bruto, sha = ler_auxiliar(caminho)

    try:
        dados = json.loads(bruto)
    except (ValueError, UnicodeDecodeError):
        raise ErroANP("JSON de catálogo inválido.") from None

    return validar_catalogo(dados), sha


def ler_vinculos(caminho, catalogo, referencia, uf, municipio):
    bruto, sha = ler_auxiliar(caminho)

    try:
        leitor = csv.DictReader(
            io.StringIO(
                bruto.decode("utf-8-sig"),
                newline="",
            ),
            delimiter=";",
            strict=True,
        )

        exigidos = {
            "cnpj",
            "posto_id",
            "confirmado",
            "revisor",
            "revisado_em",
            "evidencia",
        }

        if (
            not leitor.fieldnames
            or not exigidos.issubset(leitor.fieldnames)
            or len(leitor.fieldnames)
            != len(set(leitor.fieldnames))
        ):
            raise ErroANP("Cabeçalho dos vínculos inválido.")

        linhas = list(leitor)

    except (UnicodeDecodeError, csv.Error):
        raise ErroANP("CSV de vínculos inválido.") from None

    postos = {p["id"]: p for p in catalogo}
    vinculos = {}
    usados = set()

    for numero, v in enumerate(linhas, 2):
        if None in v or any(
            valor is None
            for valor in v.values()
        ):
            raise ErroANP(
                f"Linha {numero} dos vínculos malformada."
            )

        confirmado = v["confirmado"].strip().lower()

        if confirmado in ("", "nao", "não", "pendente"):
            continue

        if confirmado != "sim":
            raise ErroANP(
                f"Linha {numero}: confirmado deve ser "
                "sim, nao ou pendente."
            )

        cnpj = cnpj_valido(v["cnpj"])
        revisado = data_iso(v["revisado_em"])

        if not re.fullmatch(
            r"[1-9][0-9]{0,9}",
            v["posto_id"].strip(),
        ):
            raise ErroANP(
                f"Linha {numero}: posto_id inválido."
            )

        ident = int(v["posto_id"])
        p = postos.get(ident)

        if (
            not cnpj
            or not p
            or cnpj in vinculos
            or ident in usados
            or not revisado
            or revisado > referencia
            or not 1 <= len(v["revisor"].strip()) <= 100
            or not 10 <= len(v["evidencia"].strip()) <= 500
        ):
            raise ErroANP(
                f"Linha {numero}: vínculo ausente, duplicado "
                "ou sem revisão válida."
            )

        if (
            normalizar(p["uf"]) != uf
            or not p["cidade"]
            or (
                municipio
                and normalizar(p["cidade"]) != municipio
            )
        ):
            raise ErroANP(
                f"Linha {numero}: confirme cidade/UF "
                "no catálogo de revisão."
            )

        if p["tipo_posto"] != "Convencional":
            raise ErroANP(
                f"Linha {numero}: revenda ANP não pode "
                "ser associada a eletroposto."
            )

        vinculos[cnpj] = {
            "posto_id": ident,
            "revisor": v["revisor"].strip(),
            "revisado_em": revisado.isoformat(),
            "evidencia": v["evidencia"].strip(),
        }

        usados.add(ident)

    return vinculos, sha


def sugerir_candidatos(registro, catalogo):
    dado = registro["original"]

    nome = normalizar(dado.get("revenda"))
    endereco = normalizar(dado.get("endereco"))

    candidatos = []

    for p in catalogo:
        if p["tipo_posto"] == "Eletroposto":
            continue

        if (
            p["uf"]
            and normalizar(p["uf"]) != registro["uf"]
        ):
            continue

        if (
            p["cidade"]
            and normalizar(p["cidade"]) != registro["municipio"]
        ):
            continue

        similaridade_nome = SequenceMatcher(
            None,
            nome,
            normalizar(p["nome"]),
        ).ratio()

        similaridade_endereco = SequenceMatcher(
            None,
            endereco,
            normalizar(p["endereco"]),
        ).ratio()

        pontos = round(
            (
                similaridade_nome
                + 2 * similaridade_endereco
            ) / 3,
            3,
        )

        if (
            similaridade_endereco >= 0.55
            or similaridade_nome >= 0.75
        ):
            candidatos.append(
                {
                    "posto_id": p["id"],
                    "nome": p["nome"],
                    "endereco": p["endereco"],
                    "similaridade_textual": pontos,
                    "situacao": "sugestao_sem_vinculo",
                }
            )

    return sorted(
        candidatos,
        key=lambda p: (
            -p["similaridade_textual"],
            p["posto_id"],
        ),
    )[:5]