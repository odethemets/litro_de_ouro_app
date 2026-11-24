"""Garantias offline ANP; fixtures sintéticas, sem serviços externos."""
import csv
from datetime import date, datetime
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import cast
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.anp.associacao import (
    ler_catalogo,
    ler_vinculos,
    validar_catalogo,
)
from services.anp.contrato import (
    ErroANP,
    cep_valido,
    cnpj_valido,
    data_iso,
    preco_decimal,
    validar_url_fonte,
)
from services.anp.fontes import COLUNAS, ler_arquivo
from services.anp.preparacao import hash_json, preparar
from services.anp.relatorios import salvar_relatorios

URL = (
    "https://www.gov.br/anp/pt-br/assuntos/"
    "precos-e-defesa-da-concorrencia/precos/arquivos-lpc/"
    "2026/revendas_lpc_2026_11_08-2026_11_14.xlsx"
)

INICIO = date(2026, 11, 8)
FIM = date(2026, 11, 14)
HOJE = date(2026, 11, 23)

TEM_OPENPYXL = importlib.util.find_spec("openpyxl") is not None


def linha(**extras):
    dado = dict(
        zip(
            COLUNAS,
            (
                "PB",
                "JOÃO PESSOA",
                "11222333000181",
                "REVENDA FICTICIA",
                "RUA EXEMPLO",
                "123",
                "CENTRO",
                "58010000",
                "RAIZEN",
                "GASOLINA COMUM",
                "6,19",
                "R$ / litro",
                "2026-11-09",
            ),
        )
    )

    return dict(dado, **extras)


def fonte(*linhas):
    return {
        "arquivo": "fixture.csv",
        "sha256": "a" * 64,
        "bytes": 123,
        "formato": "csv",
        "abas_lidas": [],
        "registros": [
            {
                "dados": dado,
                "aba_lida": "",
                "linha_lida": i,
            }
            for i, dado in enumerate(linhas, 2)
        ],
    }


def plano(*linhas, **kwargs):
    return preparar(
        fonte(*linhas),
        inicio=INICIO,
        fim=FIM,
        referencia=HOJE,
        fonte_url=URL,
        **kwargs,
    )


def posto(**extras):
    return dict(
        {
            "id": 7,
            "nome": "REVENDA FICTICIA",
            "endereco": "RUA EXEMPLO 123",
            "bairro": "CENTRO",
            "uf": "PB",
            "cidade": "JOAO PESSOA",
            "tipo_posto": "Convencional",
        },
        **extras,
    )


class PreparacaoANPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def csv(
        self,
        linhas,
        nome="entrada.csv",
        sep=";",
        preambulo=(),
        encoding="utf-8-sig",
    ):
        p = self.pasta / nome

        campos = list(
            dict.fromkeys(
                k
                for r in linhas
                for k in r
            )
        )

        with p.open(
            "w",
            encoding=encoding,
            newline="",
        ) as stream:
            writer = csv.writer(
                stream,
                delimiter=sep,
            )

            writer.writerows(preambulo)
            writer.writerow(campos)

            writer.writerows(
                [
                    r.get(k, "")
                    for k in campos
                ]
                for r in linhas
            )

        return p

    def vinculos(self, **extras):
        dado = dict(
            {
                "cnpj": "11222333000181",
                "posto_id": "7",
                "confirmado": "sim",
                "revisor": "REVISOR TESTE",
                "revisado_em": "2026-11-22",
                "evidencia": (
                    "Endereço conferido na fonte de teste."
                ),
            },
            **extras,
        )

        return self.csv(
            [dado],
            "vinculos.csv",
        )

    def ler_vinculo(self, **extras):
        return ler_vinculos(
            self.vinculos(**extras),
            [posto()],
            HOJE,
            "PB",
            "JOAO PESSOA",
        )

    def test_cnpj_checksum_mascara_e_zero_nao_inventado(self):
        self.assertEqual(
            cnpj_valido("11.222.333/0001-81"),
            "11222333000181",
        )

        for valor in (
            "11222333000180",
            "00000000000000",
            "7.40973e+12",
            "7.40973E-12",
            "123",
            None,
            True,
        ):
            with self.subTest(valor=valor):
                self.assertIsNone(cnpj_valido(valor))

    def test_cep_nao_reconstrui_cientifico(self):
        self.assertEqual(
            cep_valido("58010-000"),
            "58010000",
        )

        for valor in (
            "5.801e+7",
            "5801000",
            "58010x000",
            None,
        ):
            self.assertIsNone(cep_valido(valor))

    def test_precos_exatos_sem_arredondamento(self):
        for valor, esperado in (
            ("6,19", "6.19"),
            ("6.190", "6.19"),
            ("0.01", "0.01"),
            ("25", "25.00"),
        ):
            self.assertEqual(
                preco_decimal(valor),
                esperado,
            )

        for valor in (
            "6.199",
            "NaN",
            "Infinity",
            "1e1",
            "-2",
            "25.01",
            "0",
            "1.234,56",
            True,
        ):
            self.assertIsNone(preco_decimal(valor))

    def test_datas_reais_e_dia_civil(self):
        self.assertEqual(
            data_iso("09/11/2026"),
            date(2026, 11, 9),
        )

        self.assertEqual(
            data_iso(datetime(2026, 11, 9)),
            date(2026, 11, 9),
        )

        self.assertIsNone(data_iso("2026-02-30"))
        self.assertIsNone(data_iso("11/09/26"))

    def test_url_oficial_periodo_e_resumo_bloqueados(self):
        self.assertEqual(
            validar_url_fonte(URL, INICIO, FIM),
            URL,
        )

        invalidas = (
            URL.replace("revendas", "resumo_semanal"),
            URL + "?token=teste",
            URL.replace("gov.br/", "gov.br.evil/"),
            URL.replace("https://", "http://"),
            URL.replace(
                "www.gov.br",
                "usuario@www.gov.br",
            ),
            URL.replace(
                "2026_11_14",
                "2026_11_21",
            ),
        )

        for url in invalidas:
            with self.assertRaises(ErroANP):
                validar_url_fonte(
                    url,
                    INICIO,
                    FIM,
                )

    def test_csv_derivado_linha_hash_e_original_preservados(self):
        p = self.csv(
            [
                linha(
                    preco_venda_original=" 6,19 ",
                    preco_venda="6.19",
                    arquivo_origem="derivado.csv",
                    linha_origem="7049",
                )
            ]
        )

        f = ler_arquivo(p)

        self.assertEqual(
            f["sha256"],
            hashlib.sha256(p.read_bytes()).hexdigest(),
        )

        self.assertEqual(
            f["registros"][0]["linha_lida"],
            2,
        )

        r = preparar(
            f,
            inicio=INICIO,
            fim=FIM,
            referencia=HOJE,
            fonte_url=URL,
        )["registros"][0]

        self.assertEqual(
            r["original"]["linha_origem"],
            "7049",
        )

        self.assertEqual(
            r["original"]["preco_venda_original"],
            " 6,19 ",
        )

        self.assertEqual(r["preco"], "6.19")

        self.assertEqual(
            r["situacao"],
            "aguardando_vinculo",
        )

    def test_csv_virgula_e_preambulo_anp(self):
        p = self.csv(
            [linha()],
            sep=",",
            preambulo=(
                ("ANP",),
                ("Semana",),
                (),
                ("Revendas",),
            ),
        )

        f = ler_arquivo(p)

        self.assertEqual(
            f["registros"][0]["linha_lida"],
            6,
        )

        self.assertEqual(
            f["registros"][0]["dados"][
                "preco_venda_original"
            ],
            "6,19",
        )

    def test_codificacao_explicita_sem_substituir_caracteres(self):
        p = self.csv(
            [linha()],
            encoding="cp1252",
        )

        with self.assertRaises(ErroANP):
            ler_arquivo(p)

        self.assertEqual(
            len(
                ler_arquivo(
                    p,
                    "cp1252",
                )["registros"]
            ),
            1,
        )

    def test_resumo_nacional_sem_identidade_recusado(self):
        p = self.csv(
            [
                {
                    "ESTADO": "PARAIBA",
                    "PRODUTO": "GASOLINA COMUM",
                    "PRECO MEDIO": "6.19",
                }
            ]
        )

        with self.assertRaisesRegex(
            ErroANP,
            "individuais",
        ):
            ler_arquivo(p)

    def test_cabecalho_duplicado_ou_campo_sem_nome_recusado(self):
        p = self.csv([linha()])
        bruto = p.read_text(encoding="utf-8-sig")

        bruto = bruto.replace(
            ";cnpj;",
            ";cnpj;cnpj;",
        ).replace(
            ";11222333000181;",
            ";11222333000181;11222333000181;",
        )

        p.write_text(
            bruto,
            encoding="utf-8",
        )

        with self.assertRaises(ErroANP):
            ler_arquivo(p)

        p = self.csv([linha()])

        with p.open(
            "a",
            encoding="utf-8",
        ) as stream:
            stream.write(
                ";".join(linha().values())
                + ";campo_sem_cabecalho\n"
            )

        with self.assertRaisesRegex(
            ErroANP,
            "sem cabeçalho",
        ):
            ler_arquivo(p)

    def test_limites_bytes_linhas_celulas(self):
        p = self.csv([linha()])

        with patch(
            "services.anp.fontes.MAX_BYTES",
            5,
        ), self.assertRaises(ErroANP):
            ler_arquivo(p)

        with patch(
            "services.anp.fontes.MAX_LINHAS",
            0,
        ), self.assertRaises(ErroANP):
            ler_arquivo(p)

        p = self.csv(
            [
                linha(
                    revenda="a" * 2001,
                )
            ]
        )

        with self.assertRaises(ErroANP):
            ler_arquivo(p)

    @unittest.skipUnless(
        TEM_OPENPYXL,
        "Instale requirements-anp.txt para verificar XLSX.",
    )
    def test_xlsx_original_multiplas_abas_e_proveniencia(self):
        from openpyxl import Workbook

        livro = Workbook()

        folha_resumo = livro.worksheets[0]
        folha_resumo.title = "Resumo"
        folha_resumo.append(["Preço médio"])

        folha = livro.create_sheet("Revendas")
        folha.append(["ANP"])
        folha.append(list(COLUNAS))

        dado: dict[str, str | datetime] = dict(linha()) # pyright: ignore[reportAssignmentType]
        dado["data_coleta"] = datetime(2026, 11, 9)

        folha.append(list(dado.values()))

        # Formatação após a tabela não cria um dado novo.
        folha.cell(
            2,
            len(COLUNAS) + 3,
        ).number_format = "@"

        p = self.pasta / "original.xlsx"

        livro.save(p)
        livro.close()

        fonte_lida = ler_arquivo(p)

        self.assertEqual(
            fonte_lida["abas_lidas"],
            ["Revendas"],
        )

        r = preparar(
            fonte_lida,
            inicio=INICIO,
            fim=FIM,
            referencia=HOJE,
            fonte_url=URL,
        )["registros"][0]

        self.assertEqual(
            r["data_coleta"],
            "2026-11-09",
        )
        self.assertEqual(r["linha_lida"], 3)
        self.assertEqual(r["avisos"], [])

    @unittest.skipUnless(
        TEM_OPENPYXL,
        "Instale requirements-anp.txt para verificar XLSX.",
    )
    def test_xlsx_formula_nao_usa_cache_como_valor(self):
        from openpyxl import Workbook

        livro = Workbook()
        folha = livro.worksheets[0]

        folha.append(list(COLUNAS))

        folha.append(
            list(
                linha(
                    preco_venda_original="=6+1",
                ).values()
            )
        )

        p = self.pasta / "formula.xlsx"

        livro.save(p)
        livro.close()

        f = ler_arquivo(p)

        r = preparar(
            f,
            inicio=INICIO,
            fim=FIM,
            referencia=HOJE,
            fonte_url=URL,
        )["registros"][0]

        self.assertIn(
            "formula_na_fonte",
            r["motivos"],
        )
        self.assertIsNone(r["preco"])

    def test_xlsx_compactacao_e_conteudo_invalido_recusados(self):
        from zipfile import ZipFile

        p = self.pasta / "teste.xlsx"
        p.write_bytes(b"nao e xlsx")

        with self.assertRaises(ErroANP):
            ler_arquivo(p)

        with ZipFile(p, "w") as pacote:
            pacote.writestr(
                "file",
                b"x" * 100,
            )

        with patch(
            "services.anp.fontes.MAX_DESCOMPACTADO",
            4,
        ), self.assertRaises(ErroANP):
            ler_arquivo(p)

    def test_cabecalho_original_anp_e_identificadores_textuais(self):
        original = {
            "ESTADO": "PARAÍBA",
            "MUNICÍPIO": "JOAO PESSOA",
            "CNPJ": "11222333000181",
            "RAZÃO": "REVENDA FICTICIA",
            "ENDEREÇO": "RUA EXEMPLO",
            "NÚMERO": "123",
            "BAIRRO": "CENTRO",
            "CEP": "58010000",
            "BANDEIRA": "RAIZEN",
            "PRODUTO": "GNV",
            "PREÇO DE REVENDA": "4,19",
            "UNIDADE DE MEDIDA": "R$ / m³",
            "DATA DA COLETA": "09/11/2026",
        }

        f = ler_arquivo(
            self.csv([original])
        )

        r = preparar(
            f,
            inicio=INICIO,
            fim=FIM,
            referencia=HOJE,
            fonte_url=URL,
        )["registros"][0]

        self.assertEqual(
            (
                r["cnpj"],
                r["cep"],
                r["codigo"],
                r["preco"],
            ),
            (
                "11222333000181",
                "58010000",
                "gnv",
                "4.19",
            ),
        )

    def test_pendencia_preexistente_nao_e_descartada(self):
        r = plano(
            linha(
                tipo_pendencia="conferir_documento_original",
            )
        )["registros"][0]

        self.assertEqual(
            r["situacao"],
            "pendente",
        )
        self.assertIn(
            "pendencia_declarada_na_fonte",
            r["motivos"],
        )
        self.assertEqual(
            r["original"]["tipo_pendencia"],
            "conferir_documento_original",
        )

    def test_recorte_pb_joao_pessoa_sem_alterar_municipios(self):
        p = plano(
            linha(),
            linha(municipio="CAMPINA GRANDE"),
            linha(uf="PE", municipio="RECIFE"),
        )

        self.assertEqual(
            p["resumo"]["linhas_recorte"],
            1,
        )

        p = plano(
            linha(municipio="CAMPINA GRANDE"),
            municipio=None,
        )

        self.assertEqual(
            p["resumo"]["linhas_recorte"],
            1,
        )

        with self.assertRaises(ErroANP):
            plano(linha(), uf="PE")

    def test_periodo_futuro_curto_e_coleta_fora_semana(self):
        for inicio, fim, referencia in (
            (INICIO, INICIO, HOJE),
            (FIM, INICIO, HOJE),
            (INICIO, FIM, INICIO),
        ):
            with self.assertRaises(ErroANP):
                preparar(
                    fonte(linha()),
                    inicio=inicio,
                    fim=fim,
                    referencia=referencia,
                    fonte_url=URL,
                )

        for data in (
            "2026-11-15",
            "2026-02-30",
        ):
            self.assertEqual(
                plano(
                    linha(data_coleta=data)
                )["registros"][0]["situacao"],
                "pendente",
            )

    def test_glp_e_diesel_nao_se_convertem_em_diesel_generico(self):
        for produto in (
            "GLP",
            "DIESEL S10",
            "DIESEL S500",
            "DIESEL",
            "RECARGA ELETRICA",
        ):
            r = plano(
                linha(
                    produto_original=produto,
                )
            )["registros"][0]

            self.assertIsNone(r["codigo"])

            self.assertEqual(
                r["situacao"],
                "pendente",
            )

    def test_gnv_metro_cubico_e_combustiveis_suportados(self):
        produtos = (
            ("GASOLINA COMUM", "gasolina_comum", "L"),
            ("ETANOL", "etanol", "L"),
            (
                "GASOLINA ADITIVADA",
                "gasolina_aditivada",
                "L",
            ),
            ("GNV", "gnv", "m³"),
        )

        for produto, codigo, unidade in produtos:
            r = plano(
                linha(
                    produto_original=produto,
                    unidade_original=(
                        "R$ / m³"
                        if codigo == "gnv"
                        else "R$ / litro"
                    ),
                )
            )["registros"][0]

            self.assertEqual(
                (
                    r["codigo"],
                    r["unidade"],
                ),
                (
                    codigo,
                    unidade,
                ),
            )

            self.assertEqual(
                r["situacao"],
                "aguardando_vinculo",
            )

        self.assertIn(
            "unidade_incompativel_com_produto",
            plano(
                linha(produto_original="GNV")
            )["registros"][0]["motivos"],
        )

    def test_cnpj_corrompido_nunca_vira_vinculo(self):
        r = plano(
            linha(
                cnpj="7.40973e+12",
                cep="5.8037e+07",
            )
        )["registros"][0]

        self.assertIsNone(r["cnpj"])
        self.assertIsNone(r["posto_id"])

        self.assertIn(
            "cnpj_cientifico_irrecuperavel",
            r["motivos"],
        )

    def test_preco_original_normalizado_e_modalidade_conferidos(self):
        r = plano(
            linha(preco_venda="6.20")
        )["registros"][0]

        self.assertIn(
            "preco_normalizado_diverge_do_original",
            r["motivos"],
        )

        r = plano(
            linha(
                forma_pagamento="CARTAO",
                numero="12?",
            )
        )["registros"][0]

        self.assertIn(
            "modalidade_de_preco_exige_revisao",
            r["motivos"],
        )
        self.assertIn(
            "numero_invalido_ou_ausente",
            r["motivos"],
        )

    def test_preco_conflitante_bloqueia_ambos_inclusive_unidades_equivalentes(self):
        p = plano(
            linha(),
            linha(
                preco_venda_original="6.29",
                unidade_original="R$/L",
            ),
        )

        self.assertEqual(
            p["itens_revisados"],
            [],
        )

        for r in p["registros"]:
            self.assertIn(
                "precos_divergentes_mesma_chave",
                r["motivos"],
            )

    def test_mesmo_cnpj_endereco_divergente_bloqueia_ambos(self):
        p = plano(
            linha(),
            linha(
                produto_original="ETANOL",
                endereco="OUTRA RUA",
            ),
        )

        self.assertTrue(
            all(
                "enderecos_divergentes_mesmo_cnpj"
                in r["motivos"]
                for r in p["registros"]
            )
        )

    def test_duplicata_exata_preserva_duas_linhagens_e_chave_original(self):
        p = plano(
            linha(linha_origem="6"),
            linha(linha_origem="7"),
        )

        self.assertEqual(
            len(p["registros"]),
            2,
        )

        a, b = p["registros"]

        self.assertEqual(
            b["situacao"],
            "duplicata_exata",
        )
        self.assertEqual(
            b["duplicata_de"],
            a["linha_id"],
        )
        self.assertNotEqual(
            a["linha_id"],
            b["linha_id"],
        )

    def test_endereco_igual_so_sugere_nunca_confirma(self):
        p = plano(
            linha(),
            catalogo=[
                posto(),
                posto(id=8),
            ],
        )

        sugestoes = p["associacoes_para_revisao"][0]["candidatos"]

        self.assertEqual(
            [
                s["posto_id"]
                for s in sugestoes
            ],
            [7, 8],
        )

        self.assertIsNone(
            p["registros"][0]["posto_id"]
        )

        self.assertEqual(
            p["itens_revisados"],
            [],
        )

    def test_vinculo_exige_revisor_evidencia_id_e_cnpj_integros(self):
        invalidos = (
            {"cnpj": "7.40973e+12"},
            {"posto_id": "9"},
            {"revisor": ""},
            {"evidencia": ""},
            {"revisado_em": "2026-11-24"},
            {"posto_id": "True"},
            {"confirmado": "true"},
        )

        for extras in invalidos:
            with self.subTest(
                extras=extras,
            ), self.assertRaises(ErroANP):
                self.ler_vinculo(**extras)

    def test_vinculo_pendente_ignorado_e_duplicata_recusada(self):
        vinculos, _ = self.ler_vinculo(
            confirmado="pendente",
            posto_id="",
        )

        self.assertEqual(vinculos, {})

        p = self.vinculos()

        bruto = p.read_text(
            encoding="utf-8-sig"
        )

        with p.open(
            "a",
            encoding="utf-8",
        ) as stream:
            stream.write(
                bruto.splitlines()[1] + "\n"
            )

        with self.assertRaises(ErroANP):
            ler_vinculos(
                p,
                [posto()],
                HOJE,
                "PB",
                "JOAO PESSOA",
            )

    def test_vinculo_nao_aceita_eletroposto_ou_localidade_desconhecida(self):
        invalidos = (
            posto(tipo_posto="Eletroposto"),
            posto(cidade=""),
            posto(uf="PE"),
        )

        for p in invalidos:
            with self.assertRaises(ErroANP):
                ler_vinculos(
                    self.vinculos(),
                    [p],
                    HOJE,
                    "PB",
                    "JOAO PESSOA",
                )

    def test_proposta_revisada_continua_sem_autorizacao_de_importacao(self):
        vinculos, sha = self.ler_vinculo()

        p = plano(
            linha(),
            catalogo=[posto()],
            vinculos=vinculos,
            sha_vinculos=sha,
        )

        self.assertEqual(
            p["itens_revisados"][0]["posto_id"],
            7,
        )
        self.assertEqual(
            p["itens_revisados"][0]["preco"],
            "6.19",
        )
        self.assertFalse(p["apto_importacao"])

        self.assertFalse(
            any(
                p["politica"][k]
                for k in (
                    "cria_postos",
                    "gera_karma",
                    "altera_oferta_ou_bandeira",
                    "grava_banco",
                )
            )
        )

        self.assertEqual(
            p["registros"][0]["original"]["bandeira"],
            "RAIZEN",
        )

    def test_catalogo_somente_campos_publicos_sem_ids_duplicados(self):
        p = self.pasta / "catalogo.json"

        p.write_text(
            json.dumps(
                [
                    posto(
                        password="valor-ficticio-nao-exportar"
                    )
                ]
            ),
            encoding="utf-8",
        )

        cat, sha = ler_catalogo(p)

        self.assertEqual(len(sha), 64)
        self.assertNotIn("password", cat[0])

        for dados in (
            [posto(), posto()],
            [posto(id=True)],
            {"postos": []},
        ):
            with self.assertRaises(ErroANP):
                validar_catalogo(dados)

    def test_hash_deterministico_e_mudanca_da_fonte_detectada(self):
        a = plano(linha())
        b = plano(linha())

        self.assertEqual(
            a["sha256_plano"],
            b["sha256_plano"],
        )

        self.assertNotEqual(
            a["sha256_plano"],
            plano(
                linha(preco_venda_original="6.20")
            )["sha256_plano"],
        )

        self.assertEqual(
            a["sha256_plano"],
            hash_json(
                {
                    k: v
                    for k, v in a.items()
                    if k != "sha256_plano"
                }
            ),
        )

    def test_relatorios_nao_sobrescrevem_e_formulas_neutralizadas(self):
        p = plano(
            linha(
                revenda='=HYPERLINK("exemplo")'
            )
        )

        pasta = self.pasta / "saida"
        salvar_relatorios(p, pasta)

        with (pasta / "auditoria.csv").open(
            encoding="utf-8-sig",
            newline="",
        ) as stream:
            r = next(
                csv.DictReader(
                    stream,
                    delimiter=";",
                )
            )

        self.assertTrue(
            r["revenda"].startswith("'=")
        )

        armazenado = json.loads(
            (pasta / "plano.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertTrue(
            armazenado["registros"][0]["original"][
                "revenda"
            ].startswith("=")
        )

        antes = (
            pasta / "plano.json"
        ).read_bytes()

        with self.assertRaises(FileExistsError):
            salvar_relatorios(p, pasta)

        self.assertEqual(
            (pasta / "plano.json").read_bytes(),
            antes,
        )

    def test_integridade_relatorio_e_hash_alterado_recusado(self):
        p = plano(linha())
        pasta = self.pasta / "saida"

        salvar_relatorios(p, pasta)

        manifesto = json.loads(
            (pasta / "manifesto.json").read_text(
                encoding="utf-8"
            )
        )

        for arquivo, sha in manifesto[
            "sha256_arquivos"
        ].items():
            self.assertEqual(
                hashlib.sha256(
                    (pasta / arquivo).read_bytes()
                ).hexdigest(),
                sha,
            )

        p["registros"][0]["preco"] = "9.00"

        with self.assertRaises(ErroANP):
            salvar_relatorios(
                p,
                self.pasta / "alterado",
            )

    def test_falha_na_escrita_remove_so_pasta_nova(self):
        marcador = self.pasta / "preservar.txt"

        marcador.write_text(
            "preservar",
            encoding="utf-8",
        )

        pasta = self.pasta / "saida"

        with patch(
            "services.anp.relatorios._csv",
            side_effect=OSError("teste"),
        ), self.assertRaises(OSError):
            salvar_relatorios(
                plano(linha()),
                pasta,
            )

        self.assertFalse(pasta.exists())

        self.assertEqual(
            marcador.read_text(
                encoding="utf-8"
            ),
            "preservar",
        )

    def test_template_nao_preenche_ids_nem_confirmacoes(self):
        pasta = self.pasta / "saida"

        salvar_relatorios(
            plano(
                linha(),
                catalogo=[posto()],
            ),
            pasta,
        )

        with (pasta / "vinculos_para_revisar.csv").open(
            encoding="utf-8-sig"
        ) as stream:
            r = next(
                csv.DictReader(
                    stream,
                    delimiter=";",
                )
            )

        self.assertEqual(
            r["confirmado"],
            "pendente",
        )
        self.assertEqual(r["posto_id"], "")

    def test_cli_offline_nao_importa_database_app_nem_abre_rede(self):
        spec = importlib.util.spec_from_file_location(
            "cli_anp",
            ROOT / "scripts/preparar_anp.py",
        )

        if spec is None:
            raise AssertionError(
                "Não foi possível criar a especificação do script ANP."
            )

        loader = spec.loader

        if loader is None:
            raise AssertionError(
                "O script ANP não possui carregador."
            )

        cli = importlib.util.module_from_spec(spec)
        loader.exec_module(cli)

        p = self.csv([linha()])
        saida = self.pasta / "saida"

        args = [
            "--arquivo",
            str(p),
            "--saida",
            str(saida),
            "--fonte-url",
            URL,
            "--periodo-inicio",
            "2026-11-08",
            "--periodo-fim",
            "2026-11-14",
            "--data-referencia",
            "2026-11-23",
        ]

        import builtins

        original = builtins.__import__

        def restrito(nome, *a, **kw):
            if nome in (
                "services.database",
                "app",
                "pymysql",
            ):
                raise AssertionError(
                    "Import externo inesperado: " + nome
                )

            return original(nome, *a, **kw)

        with patch(
            "builtins.__import__",
            side_effect=restrito,
        ), patch(
            "socket.socket",
            side_effect=AssertionError("rede"),
        ), patch(
            "sys.stdout",
            new_callable=io.StringIO,
        ):
            self.assertEqual(
                cli.main(args),
                0,
            )

        self.assertTrue(
            (saida / "plano.json").exists()
        )

    def test_cli_erro_nao_imprime_credenciais_e_nao_cria_saida(self):
        p = self.csv([linha()])

        args = [
            sys.executable,
            "-B",
            str(ROOT / "scripts/preparar_anp.py"),
            "--arquivo",
            str(p),
            "--saida",
            str(self.pasta / "saida"),
            "--fonte-url",
            "https://usuario:SEGREDO-FICTICIO@www.gov.br/",
            "--periodo-inicio",
            "2026-11-08",
            "--periodo-fim",
            "2026-11-14",
            "--data-referencia",
            "2026-11-23",
        ]

        r = subprocess.run(
            args,
            capture_output=True,
            text=True,
            env=dict(
                os.environ,
                DATABASE_URL="INVALIDA-FICTICIA",
            ),
        )

        self.assertEqual(r.returncode, 2)

        self.assertNotIn(
            "SEGREDO-FICTICIO",
            r.stderr,
        )

        self.assertFalse(
            (self.pasta / "saida").exists()
        )

    def test_consulta_opcional_faz_so_select_e_fecha_conexao(self):
        from types import SimpleNamespace

        spec = importlib.util.spec_from_file_location(
            "cli_select_anp",
            ROOT / "scripts/preparar_anp.py",
        )

        if spec is None:
            raise AssertionError(
                "Não foi possível criar a especificação do script ANP."
            )

        loader = spec.loader

        if loader is None:
            raise AssertionError(
                "O script ANP não possui carregador."
            )

        cli = importlib.util.module_from_spec(spec)
        loader.exec_module(cli)

        chamadas = []
        opcoes = []
        fechadas = []

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def execute(self, sql):
                chamadas.append(sql)

            def fetchall(self):
                return [posto()]

        class Conexao:
            def cursor(self):
                return Cursor()

            def close(self):
                fechadas.append(True)

        def conectar(**kwargs):
            opcoes.append(kwargs)
            return Conexao()

        with patch.dict(
            sys.modules,
            {
                "services.database": SimpleNamespace(
                    get_db_connection=conectar
                )
            },
        ):
            self.assertEqual(
                cli.consultar_catalogo_banco()[0]["id"],
                7,
            )

        self.assertEqual(
            opcoes,
            [
                {
                    "read_only": True,
                    "time_zone": "+00:00",
                }
            ],
        )

        self.assertEqual(len(chamadas), 1)

        self.assertTrue(
            chamadas[0].lstrip().startswith("SELECT")
        )

        self.assertEqual(fechadas, [True])

    def test_cli_catalogo_e_revisao_manual_produzem_proposta_sem_carga(self):
        p = self.csv([linha()])
        cat = self.pasta / "catalogo.json"

        cat.write_text(
            json.dumps([posto()]),
            encoding="utf-8",
        )

        vinculo = self.vinculos()
        saida = self.pasta / "saida"

        r = subprocess.run(
            [
                sys.executable,
                "-B",
                str(ROOT / "scripts/preparar_anp.py"),
                "--arquivo",
                str(p),
                "--saida",
                str(saida),
                "--fonte-url",
                URL,
                "--catalogo-json",
                str(cat),
                "--vinculos",
                str(vinculo),
                "--periodo-inicio",
                "2026-11-08",
                "--periodo-fim",
                "2026-11-14",
                "--data-referencia",
                "2026-11-23",
            ],
            capture_output=True,
            text=True,
        )

        self.assertEqual(
            r.returncode,
            0,
            r.stderr,
        )

        proposta = json.loads(
            (saida / "plano.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(
            len(proposta["itens_revisados"]),
            1,
        )

        self.assertFalse(
            proposta["apto_importacao"]
        )

        self.assertIsNotNone(
            proposta["sha256_vinculos"]
        )

    def test_csv_sem_xlsx_nao_depende_de_openpyxl(self):
        import builtins

        importar = builtins.__import__

        def proibido(nome, *a, **kw):
            if nome.startswith("openpyxl"):
                raise AssertionError(
                    "CSV não deve importar openpyxl"
                )

            return importar(nome, *a, **kw)

        p = self.csv([linha()])

        with patch(
            "builtins.__import__",
            side_effect=proibido,
        ):
            self.assertEqual(
                len(
                    ler_arquivo(p)["registros"]
                ),
                1,
            )

    def test_consulta_opcional_fecha_conexao_tambem_ao_falhar(self):
        from types import SimpleNamespace

        spec = importlib.util.spec_from_file_location(
            "cli_select_falha_anp",
            ROOT / "scripts/preparar_anp.py",
        )

        if spec is None:
            raise AssertionError(
                "Não foi possível criar a especificação do script ANP."
            )

        loader = spec.loader

        if loader is None:
            raise AssertionError(
                "O script ANP não possui carregador."
            )

        cli = importlib.util.module_from_spec(spec)
        loader.exec_module(cli)

        fechadas = []

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def execute(self, sql):
                raise RuntimeError("falha simulada")

        class Conexao:
            def cursor(self):
                return Cursor()

            def close(self):
                fechadas.append(True)

        with patch.dict(
            sys.modules,
            {
                "services.database": SimpleNamespace(
                    get_db_connection=lambda **kw: Conexao()
                )
            },
        ):
            with self.assertRaises(RuntimeError):
                cli.consultar_catalogo_banco()

        self.assertEqual(fechadas, [True])


if __name__ == "__main__":
    unittest.main(verbosity=2)