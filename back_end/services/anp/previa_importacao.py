"""Prévia de elegibilidade ANP. Sem rede, SQL ou autorização de escrita."""
from collections import Counter
from copy import deepcopy
from datetime import date
import re

from .contrato import (
    ErroANP,
    PRODUTOS,
    cnpj_valido,
    data_iso,
    normalizar,
    preco_decimal,
    unidade_compativel,
    validar_url_fonte,
)
from .preparacao import hash_json


def _hash(valor):
    return (
        isinstance(valor, str)
        and re.fullmatch(r"[0-9a-f]{64}", valor) is not None
    )


def _id(valor):
    return type(valor) is int and 1 <= valor <= 2147483647


def _integro(plano, esperado):
    if not isinstance(plano, dict) or not _hash(esperado):
        raise ErroANP("Informe plano e SHA-256 externo da preparação.")

    corpo = {
        k: v
        for k, v in plano.items()
        if k != "sha256_plano"
    }

    if (
        plano.get("sha256_plano") != esperado
        or hash_json(corpo) != esperado
    ):
        raise ErroANP("O plano diverge do hash esperado.")

    if (
        type(plano.get("versao")) is not int
        or plano.get("versao") != 1
        or plano.get("fase") != "preparacao_sem_gravacao"
        or plano.get("apto_importacao") is not False
    ):
        raise ErroANP("Contrato de preparação incompatível.")

    if (
        not isinstance(plano.get("fonte"), dict)
        or not _hash(plano["fonte"].get("sha256"))
    ):
        raise ErroANP("Fonte sem hash válido.")


def _snapshot(dados, referencia):
    if dados is None:
        return None, {}, {}

    if (
        not isinstance(dados, dict)
        or type(dados.get("versao")) is not int
        or dados["versao"] != 1
        or dados.get("data_referencia") != referencia.isoformat()
    ):
        raise ErroANP(
            "Snapshot incompatível ou de outra data de referência."
        )

    precos = dados.get("precos")
    importacoes = dados.get("importacoes")

    if (
        not isinstance(precos, list)
        or not isinstance(importacoes, list)
        or len(precos) > 30000
        or len(importacoes) > 200000
    ):
        raise ErroANP(
            "Listas do snapshot ausentes ou acima do limite."
        )

    atuais, anteriores = {}, {}
    codigos = {p[0] for p in PRODUTOS.values()}

    for p in precos:
        if (
            not isinstance(p, dict)
            or not _id(p.get("posto_id"))
            or p.get("codigo") not in codigos
        ):
            raise ErroANP("Preço atual inválido no snapshot.")

        dia = data_iso(p.get("data_registro"))
        chave = (p["posto_id"], p["codigo"])

        if (
            not isinstance(p.get("data_registro"), str)
            or not dia
            or dia.isoformat() != p["data_registro"]
            or dia > referencia
            or preco_decimal(p.get("preco")) is None
            or chave in atuais
        ):
            raise ErroANP(
                "Preço atual duplicado, futuro ou sem data civil válida."
            )

        atuais[chave] = dia

    for item in importacoes:
        if (
            not isinstance(item, dict)
            or not _hash(item.get("chave_observacao"))
            or not _hash(item.get("hash_conteudo"))
            or item["chave_observacao"] in anteriores
        ):
            raise ErroANP("Ledger simulado inválido ou duplicado.")

        anteriores[item["chave_observacao"]] = item["hash_conteudo"]

    return hash_json(dados), atuais, anteriores


def prever_importacao(
    plano,
    *,
    sha256_plano_esperado,
    referencia,
    snapshot=None,
):
    """Snapshot é auxiliar offline; o futuro escritor relerá a transação."""
    if type(referencia) is not date:
        raise ErroANP("Data de referência inválida.")

    _integro(plano, sha256_plano_esperado)

    if plano.get("data_referencia") != referencia.isoformat():
        raise ErroANP(
            "Refaça a preparação na data de referência da prévia."
        )

    inicio = data_iso(plano.get("periodo", {}).get("inicio"))
    fim = data_iso(plano.get("periodo", {}).get("fim"))

    if (
        not inicio
        or not fim
        or (fim - inicio).days != 6
        or fim > referencia
    ):
        raise ErroANP("Período inválido na preparação.")

    validar_url_fonte(
        plano.get("url_fonte_declarada"),
        inicio,
        fim,
    )

    itens, registros, vinculos = (
        plano.get(k)
        for k in (
            "itens_revisados",
            "registros",
            "vinculos_revisados",
        )
    )

    if (
        not isinstance(itens, list)
        or len(itens) > 200000
        or not isinstance(registros, list)
        or not isinstance(vinculos, dict)
    ):
        raise ErroANP(
            "Preparação sem registros ou vínculos estruturados."
        )

    por_linha = {}

    for r in registros:
        if (
            not isinstance(r, dict)
            or not _hash(r.get("linha_id"))
            or r["linha_id"] in por_linha
        ):
            raise ErroANP(
                "Identificador de linha inválido ou repetido."
            )

        por_linha[r["linha_id"]] = r

    revisadas = {
        r["linha_id"]
        for r in registros
        if r.get("situacao") == "revisado_para_proposta"
    }

    if (
        len(itens) != len(revisadas)
        or {
            i.get("linha_id")
            for i in itens
            if isinstance(i, dict)
        } != revisadas
    ):
        raise ErroANP("Itens divergem das linhas revisadas.")

    sha_snapshot, atuais, anteriores = _snapshot(
        snapshot,
        referencia,
    )

    por_observacao, destinos = {}, {}

    for item in itens:
        r = por_linha[item["linha_id"]]
        original = r.get("original")

        if (
            not isinstance(original, dict)
            or r.get("motivos") != []
        ):
            raise ErroANP(
                "Linha revisada contém pendência ou não tem original."
            )

        if any(
            item.get(k) != r.get(k)
            for k in (
                "cnpj",
                "posto_id",
                "codigo",
                "unidade",
                "preco",
                "data_coleta",
            )
        ):
            raise ErroANP("Item diverge do registro auditado.")

        produto = PRODUTOS.get(
            normalizar(original.get("produto_original"))
        )

        if (
            not produto
            or produto != (
                item.get("codigo"),
                item.get("unidade"),
            )
            or not unidade_compativel(
                original.get("unidade_original"),
                produto[1],
            )
        ):
            raise ErroANP(
                "Produto/variante sem correspondência exata."
            )

        coleta = data_iso(item.get("data_coleta"))
        preco = preco_decimal(
            original.get("preco_venda_original")
        )
        cnpj = cnpj_valido(item.get("cnpj"))

        if (
            not cnpj
            or cnpj != cnpj_valido(original.get("cnpj"))
            or not _id(item.get("posto_id"))
            or not coleta
            or not inicio <= coleta <= fim
            or item["data_coleta"] != coleta.isoformat()
            or not isinstance(item.get("preco"), str)
            or item["preco"] != preco
        ):
            raise ErroANP(
                "Identidade, data ou preço diverge da fonte."
            )

        v = vinculos.get(cnpj)
        revisado = (
            data_iso(v.get("revisado_em"))
            if isinstance(v, dict)
            else None
        )

        if (
            not isinstance(v, dict)
            or v.get("posto_id") != item["posto_id"]
            or not revisado
            or revisado > referencia
            or not isinstance(v.get("revisor"), str)
            or not 1 <= len(v["revisor"].strip()) <= 100
            or not isinstance(v.get("evidencia"), str)
            or not 10 <= len(v["evidencia"].strip()) <= 500
        ):
            raise ErroANP("Vínculo sem revisão humana válida.")

        if (
            item["posto_id"] in destinos
            and destinos[item["posto_id"]] != cnpj
        ):
            raise ErroANP(
                "Duas revendas apontam ao mesmo posto."
            )

        destinos[item["posto_id"]] = cnpj

        identidade = {
            k: item[k]
            for k in (
                "cnpj",
                "codigo",
                "data_coleta",
            )
        }

        chave = hash_json(identidade)

        conteudo = {
            k: item[k]
            for k in (
                "cnpj",
                "posto_id",
                "codigo",
                "unidade",
                "preco",
                "data_coleta",
            )
        }

        hash_conteudo = hash_json(conteudo)
        anterior = por_observacao.get(chave)

        if (
            anterior
            and anterior["hash_conteudo"] != hash_conteudo
        ):
            raise ErroANP(
                "Mesma observação com conteúdo divergente."
            )

        linhagem = {
            "linha_id": r["linha_id"],
            "arquivo": plano["fonte"]["arquivo"],
            "sha256_arquivo": plano["fonte"]["sha256"],
            "aba_lida": r["aba_lida"],
            "linha_lida": r["linha_lida"],
            "origem_declarada": {
                k: original.get(k, "")
                for k in (
                    "arquivo_origem",
                    "aba_origem",
                    "linha_origem",
                )
            },
        }

        if anterior:
            anterior["linhagens"].append(linhagem)
            continue

        if chave in anteriores:
            acao = (
                "ja_importada"
                if anteriores[chave] == hash_conteudo
                else "conflito_ledger"
            )
        elif snapshot is None:
            acao = "aguardando_snapshot"
        elif atuais.get(
            (item["posto_id"], item["codigo"]),
            date.min,
        ) >= coleta:
            acao = "preservar_preco_mesmo_dia_ou_mais_recente"
        else:
            acao = "candidata_a_importacao_futura"

        por_observacao[chave] = dict(
            conteudo,
            chave_observacao=chave,
            hash_conteudo=hash_conteudo,
            acao=acao,
            revisao=deepcopy(v),
            linhagens=[linhagem],
        )

    observacoes = sorted(
        por_observacao.values(),
        key=lambda x: x["chave_observacao"],
    )

    resultado = {
        "versao": 1,
        "fase": "previa_importacao_sem_gravacao",
        "apto_importacao": False,
        "sha256_plano_preparacao": sha256_plano_esperado,
        "sha256_snapshot": sha_snapshot,
        "data_referencia": referencia.isoformat(),
        "resumo": {
            "linhas_revisadas": len(itens),
            "observacoes": len(observacoes),
            "por_acao": dict(
                sorted(
                    Counter(
                        o["acao"]
                        for o in observacoes
                    ).items()
                )
            ),
        },
        "observacoes": observacoes,
        "bloqueios_escritor": [
            "escritor_e_migracao_de_proveniencia_nao_implementados",
            "revalidar_fonte_vinculos_e_banco_em_transacao",
            "previa_nao_comprova_autenticidade_da_fonte",
        ],
        "politica": {
            "grava_banco": False,
            "gera_karma": False,
            "cria_postos": False,
            "altera_oferta": False,
            "gera_eventos_alertas": False,
            "mesmo_dia_sem_horario": "preservar_preco_existente",
        },
    }

    return dict(
        resultado,
        sha256_previa=hash_json(resultado),
    )