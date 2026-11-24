"""Relatórios completos, com neutralização de fórmulas na apresentação CSV."""
import csv
import hashlib
import json
from pathlib import Path
import shutil

from .contrato import ErroANP
from .preparacao import hash_json


def texto_csv(valor):
    if valor is None:
        return ""

    s = str(valor)

    if (
        s.lstrip().startswith(("=", "+", "-", "@"))
        or s.startswith(("\t", "\r", "\n"))
    ):
        return "'" + s

    return s


def _csv(pasta, nome, campos, linhas):
    with (pasta / nome).open(
        "x",
        encoding="utf-8-sig",
        newline="",
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=campos,
            delimiter=";",
            quoting=csv.QUOTE_ALL,
        )

        writer.writeheader()

        writer.writerows(
            {
                k: texto_csv(linha.get(k))
                for k in campos
            }
            for linha in linhas
        )


def salvar_relatorios(plano, destino):
    conteudo = {
        k: v
        for k, v in plano.items()
        if k != "sha256_plano"
    }

    if plano.get("sha256_plano") != hash_json(conteudo):
        raise ErroANP(
            "O plano mudou após o cálculo do hash."
        )

    pasta = Path(destino)

    # Nunca sobrescreve uma revisão anterior.
    pasta.mkdir(parents=True, exist_ok=False)

    try:
        (pasta / "plano.json").write_text(
            json.dumps(
                plano,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            ) + "\n",
            encoding="utf-8",
        )

        campos = (
            "linha_id",
            "situacao",
            "motivos",
            "avisos",
            "uf",
            "municipio",
            "cnpj",
            "cnpj_original",
            "cep",
            "cep_original",
            "revenda",
            "endereco",
            "numero",
            "bairro",
            "bandeira",
            "produto_original",
            "codigo",
            "unidade_original",
            "unidade",
            "preco_venda_original",
            "preco",
            "data_coleta",
            "posto_id",
            "arquivo_lido",
            "sha256_arquivo",
            "aba_lida",
            "linha_lida",
            "arquivo_origem_declarado",
            "aba_origem_declarada",
            "linha_origem_declarada",
            "duplicata_de",
        )

        linhas = []

        for reg in plano["registros"]:
            original = reg["original"]

            linha = {
                k: original.get(k)
                for k in (
                    "revenda",
                    "endereco",
                    "numero",
                    "bairro",
                    "bandeira",
                    "produto_original",
                    "unidade_original",
                    "preco_venda_original",
                )
            }

            linha.update(
                {
                    k: v
                    for k, v in reg.items()
                    if k not in (
                        "original",
                        "motivos",
                        "avisos",
                    )
                }
            )

            linha.update(
                motivos=" | ".join(reg["motivos"]),
                avisos=" | ".join(reg["avisos"]),
                cnpj_original=original.get("cnpj"),
                cep_original=original.get("cep"),
                arquivo_lido=plano["fonte"]["arquivo"],
                sha256_arquivo=plano["fonte"]["sha256"],
                arquivo_origem_declarado=original.get(
                    "arquivo_origem"
                ),
                aba_origem_declarada=original.get(
                    "aba_origem"
                ),
                linha_origem_declarada=original.get(
                    "linha_origem"
                ),
            )

            linhas.append(linha)

        _csv(
            pasta,
            "auditoria.csv",
            campos,
            linhas,
        )

        _csv(
            pasta,
            "pendencias.csv",
            campos,
            (
                r
                for r in linhas
                if r["situacao"] == "pendente"
            ),
        )

        _csv(
            pasta,
            "aguardando_vinculo.csv",
            campos,
            (
                r
                for r in linhas
                if r["situacao"] == "aguardando_vinculo"
            ),
        )

        _csv(
            pasta,
            "proposta_revisada.csv",
            campos,
            (
                r
                for r in linhas
                if r["situacao"] == "revisado_para_proposta"
            ),
        )

        candidatos = []

        for assoc in plano["associacoes_para_revisao"]:
            for candidato in assoc["candidatos"]:
                candidatos.append(
                    dict(
                        assoc,
                        **candidato,
                        nome_catalogo=candidato["nome"],
                        endereco_catalogo=candidato["endereco"],
                        endereco_fonte=assoc["endereco"],
                    )
                )

        _csv(
            pasta,
            "candidatos.csv",
            (
                "identidade_fonte",
                "cnpj_original",
                "cnpj_validado",
                "revenda",
                "endereco_fonte",
                "numero",
                "municipio",
                "posto_id",
                "nome_catalogo",
                "endereco_catalogo",
                "similaridade_textual",
                "situacao",
            ),
            candidatos,
        )

        # Endereço igual não confirma vínculo automaticamente.
        identidades = {}

        for assoc in plano["associacoes_para_revisao"]:
            if assoc["cnpj_validado"]:
                identidades.setdefault(
                    assoc["cnpj_validado"],
                    assoc,
                )

        _csv(
            pasta,
            "vinculos_para_revisar.csv",
            (
                "cnpj",
                "posto_id",
                "confirmado",
                "revisor",
                "revisado_em",
                "evidencia",
                "revenda",
                "endereco",
            ),
            (
                {
                    "cnpj": cnpj,
                    "confirmado": "pendente",
                    "revenda": assoc["revenda"],
                    "endereco": assoc["endereco"],
                }
                for cnpj, assoc in sorted(identidades.items())
            ),
        )

        resumo = {
            k: plano[k]
            for k in (
                "fase",
                "apto_importacao",
                "fonte",
                "periodo",
                "recorte",
                "resumo",
                "sha256_plano",
            )
        }

        (pasta / "resumo.json").write_text(
            json.dumps(
                resumo,
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )

        hashes = {
            arquivo.name: hashlib.sha256(
                arquivo.read_bytes()
            ).hexdigest()
            for arquivo in sorted(pasta.iterdir())
        }

        (pasta / "manifesto.json").write_text(
            json.dumps(
                {"sha256_arquivos": hashes},
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )

    except BaseException:
        # Remove somente a pasta criada por esta execução.
        shutil.rmtree(pasta)
        raise

    return resumo