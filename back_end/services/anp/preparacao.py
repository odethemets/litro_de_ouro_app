"""Audita linhas e prepara uma proposta; nunca cadastra preço/posto."""
from collections import Counter, defaultdict
import hashlib
import json
from typing import Any
from .associacao import (
    sugerir_candidatos,
    validar_catalogo,
)
from .contrato import (
    ErroANP,
    PRODUTOS,
    cep_valido,
    cnpj_valido,
    data_iso,
    normalizar,
    preco_decimal,
    unidade_compativel,
    validar_periodo,
    validar_url_fonte,
)
from .fontes import (
    identificador_cientifico,
    preservar_original,
)


def hash_json(valor):
    bruto = json.dumps(
        valor,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")

    return hashlib.sha256(bruto).hexdigest()


def preparar(
    fonte,
    *,
    inicio,
    fim,
    referencia,
    fonte_url,
    uf="PB",
    municipio: str | None = "JOAO PESSOA",
    catalogo=None,
    vinculos=None,
    sha_catalogo=None,
    sha_vinculos=None,
) -> dict[str, Any]:
    validar_periodo(inicio, fim, referencia)
    validar_url_fonte(fonte_url, inicio, fim)

    uf = normalizar(uf)
    municipio = normalizar(municipio) if municipio else None

    if uf != "PB":
        raise ErroANP(
            "Este primeiro recorte está limitado à Paraíba (PB)."
        )

    catalogo = validar_catalogo(catalogo or [])
    vinculos = vinculos or {}

    registros = []
    grupos = defaultdict(list)

    for origem in fonte["registros"]:
        dado = preservar_original(origem["dados"])

        linha_id = hash_json(
            [
                fonte["sha256"],
                origem["aba_lida"],
                origem["linha_lida"],
            ]
        )

        uf_original = normalizar(dado.get("uf"))

        reg = {
            "linha_id": linha_id,
            "aba_lida": origem["aba_lida"],
            "linha_lida": origem["linha_lida"],
            "original": dado,
            "uf": (
                "PB"
                if uf_original in ("PB", "PARAIBA")
                else uf_original
            ),
            "municipio": normalizar(dado.get("municipio")),
            "cnpj": None,
            "cep": None,
            "codigo": None,
            "unidade": None,
            "preco": None,
            "data_coleta": None,
            "posto_id": None,
            "motivos": [],
            "avisos": [],
            "situacao": "pendente",
        }

        registros.append(reg)

        if (
            reg["uf"] != uf
            or (
                municipio
                and reg["municipio"] != municipio
            )
        ):
            reg["situacao"] = "fora_recorte"
            continue

        motivos = reg["motivos"]

        if dado.get("tipo_pendencia"):
            motivos.append(
                "pendencia_declarada_na_fonte"
            )

        if any(
            v.lstrip().startswith("=")
            for v in dado.values()
        ):
            motivos.append("formula_na_fonte")

        reg["cnpj"] = cnpj_valido(dado.get("cnpj"))
        reg["cep"] = cep_valido(dado.get("cep"))

        if not reg["cnpj"]:
            motivos.append(
                "cnpj_cientifico_irrecuperavel"
                if identificador_cientifico(dado.get("cnpj"))
                else "cnpj_invalido_ou_ausente"
            )

        if not reg["cep"]:
            motivos.append(
                "cep_cientifico_irrecuperavel"
                if identificador_cientifico(dado.get("cep"))
                else "cep_invalido_ou_ausente"
            )

        for campo in (
            "revenda",
            "endereco",
            "numero",
            "bairro",
        ):
            if (
                not dado.get(campo)
                or "?" in dado[campo]
                or any(
                    ord(c) < 32
                    for c in dado[campo]
                )
            ):
                motivos.append(
                    campo + "_invalido_ou_ausente"
                )

        produto = normalizar(
            dado.get("produto_original")
        )

        if produto in (
            "DIESEL S10",
            "DIESEL S500",
            "OLEO DIESEL S10",
            "OLEO DIESEL S500",
        ):
            motivos.append(
                "variante_diesel_sem_correspondencia_exata"
            )

        elif produto == "GLP":
            motivos.append(
                "glp_13kg_fora_catalogo"
            )

        elif produto not in PRODUTOS:
            motivos.append(
                "produto_sem_correspondencia_exata"
            )

        else:
            reg["codigo"], reg["unidade"] = PRODUTOS[produto]

            if not unidade_compativel(
                dado.get("unidade_original"),
                reg["unidade"],
            ):
                motivos.append(
                    "unidade_incompativel_com_produto"
                )

        reg["preco"] = preco_decimal(
            dado.get("preco_venda_original")
        )

        if reg["preco"] is None:
            motivos.append(
                "preco_invalido_ou_fracao_de_centavo"
            )

        if (
            "preco_venda" in dado
            and preco_decimal(dado["preco_venda"])
            != reg["preco"]
        ):
            motivos.append(
                "preco_normalizado_diverge_do_original"
            )

        coleta = data_iso(
            origem["dados"].get("data_coleta")
        )

        if not coleta:
            motivos.append(
                "data_coleta_invalida"
            )

        elif (
            not inicio <= coleta <= fim
            or coleta > referencia
        ):
            motivos.append(
                "data_coleta_fora_periodo"
            )

        else:
            reg["data_coleta"] = coleta.isoformat()

        if fonte["formato"] == "csv":
            reg["avisos"].append(
                "csv_derivado_sem_verificacao_da_planilha_original"
            )

        modalidade = [
            k
            for k in dado
            if any(
                termo in k
                for termo in (
                    "pagamento",
                    "modalidade",
                    "desconto",
                    "condicao",
                )
            )
        ]

        if any(dado[k] for k in modalidade):
            motivos.append(
                "modalidade_de_preco_exige_revisao"
            )

        if reg["cnpj"] and reg["data_coleta"]:
            grupos[
                (
                    reg["cnpj"],
                    produto,
                    reg["data_coleta"],
                )
            ].append(reg)

    # Conflitos marcam todas as linhas da chave.
    for grupo in grupos.values():
        precos = {
            r["preco"]
            for r in grupo
            if r["preco"] is not None
        }

        if len(precos) > 1:
            for r in grupo:
                r["motivos"].append(
                    "precos_divergentes_mesma_chave"
                )

    por_cnpj = defaultdict(list)

    for r in registros:
        if (
            r["cnpj"]
            and r["situacao"] != "fora_recorte"
        ):
            por_cnpj[r["cnpj"]].append(r)

    for grupo in por_cnpj.values():
        enderecos = {
            (
                r["municipio"],
                normalizar(
                    r["original"].get("endereco")
                ),
                normalizar(
                    r["original"].get("numero")
                ),
            )
            for r in grupo
        }

        if len(enderecos) > 1:
            for r in grupo:
                r["motivos"].append(
                    "enderecos_divergentes_mesmo_cnpj"
                )

    vistos = {}
    revisados = []
    candidatos = []
    identidades_vistas = set()

    postos = {
        p["id"]: p
        for p in catalogo
    }

    for reg in registros:
        if reg["situacao"] == "fora_recorte":
            continue

        # Mantém a referência à origem da duplicata.
        conteudo = {
            k: v
            for k, v in reg["original"].items()
            if k not in (
                "linha_origem",
                "aba_origem",
                "arquivo_origem",
            )
        }

        chave = hash_json(conteudo)

        if chave in vistos:
            reg["situacao"] = "duplicata_exata"
            reg["duplicata_de"] = vistos[chave]
            continue

        vistos[chave] = reg["linha_id"]

        if not reg["motivos"]:
            vinculo = vinculos.get(reg["cnpj"])

            p = (
                postos.get(vinculo["posto_id"])
                if vinculo
                else None
            )

            if (
                p
                and normalizar(p["uf"]) == uf
                and normalizar(p["cidade"])
                == reg["municipio"]
                and p["tipo_posto"] == "Convencional"
            ):
                reg["posto_id"] = p["id"]
                reg["situacao"] = "revisado_para_proposta"

                revisados.append(
                    {
                        k: reg[k]
                        for k in (
                            "linha_id",
                            "cnpj",
                            "posto_id",
                            "codigo",
                            "unidade",
                            "preco",
                            "data_coleta",
                        )
                    }
                )

            else:
                reg["situacao"] = "aguardando_vinculo"
                reg["motivos"].append(
                    "vinculo_humano_confirmado_ausente"
                )

        identidade = hash_json(
            {
                k: reg["original"].get(k)
                for k in (
                    "cnpj",
                    "revenda",
                    "endereco",
                    "numero",
                    "municipio",
                )
            }
        )

        if identidade not in identidades_vistas:
            identidades_vistas.add(identidade)

            candidatos.append(
                {
                    "identidade_fonte": identidade,
                    "cnpj_original": reg["original"].get(
                        "cnpj",
                        "",
                    ),
                    "cnpj_validado": reg["cnpj"],
                    "revenda": reg["original"].get(
                        "revenda",
                        "",
                    ),
                    "endereco": reg["original"].get(
                        "endereco",
                        "",
                    ),
                    "numero": reg["original"].get(
                        "numero",
                        "",
                    ),
                    "municipio": reg["municipio"],
                    "candidatos": sugerir_candidatos(
                        reg,
                        catalogo,
                    ),
                }
            )

    contagens = Counter(
        r["situacao"]
        for r in registros
    )

    motivos = Counter(
        motivo
        for r in registros
        for motivo in set(r["motivos"])
    )

    no_recorte = [
        r
        for r in registros
        if r["situacao"] != "fora_recorte"
    ]

    por_produto = Counter(
        r["original"].get("produto_original", "")
        for r in no_recorte
    )

    plano = {
        "versao": 1,
        "fase": "preparacao_sem_gravacao",
        "apto_importacao": False,
        "fonte": {
            k: fonte[k]
            for k in (
                "arquivo",
                "sha256",
                "bytes",
                "formato",
                "abas_lidas",
            )
        },
        "url_fonte_declarada": fonte_url,
        "autenticidade_fonte": "nao_verificada",
        "periodo": {
            "inicio": inicio.isoformat(),
            "fim": fim.isoformat(),
        },
        "data_referencia": referencia.isoformat(),
        "recorte": {
            "uf": uf,
            "municipio": municipio,
        },
        "sha256_catalogo": (
            sha_catalogo
            or hash_json(catalogo)
        ),
        "sha256_vinculos": sha_vinculos,
        "resumo": {
            "linhas_lidas": len(registros),
            "linhas_recorte": len(no_recorte),
            "por_situacao": dict(
                sorted(contagens.items())
            ),
            "por_motivo": dict(
                sorted(motivos.items())
            ),
            "por_produto": dict(
                sorted(por_produto.items())
            ),
        },
        "politica": {
            "cria_postos": False,
            "altera_oferta_ou_bandeira": False,
            "gera_karma": False,
            "gera_votos_eventos_ou_alertas": False,
            "grava_banco": False,
            "diesel_variantes": "aguardar_catalogo_distinto",
            "precos_usuarios": "preservados",
        },
        "itens_revisados": revisados,
        "vinculos_revisados": vinculos,
        "registros": registros,
        "associacoes_para_revisao": candidatos,
    }

    return dict(
        plano,
        sha256_plano=hash_json(plano),
    )