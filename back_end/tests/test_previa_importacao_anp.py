"""Prévia ANP com dados sintéticos; nenhum acesso a banco/provedor."""
from copy import deepcopy
from datetime import date
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.anp.contrato import ErroANP
from services.anp.preparacao import hash_json, preparar
from services.anp.fontes import ler_arquivo
from services.anp.associacao import ler_catalogo, ler_vinculos
from services.anp.previa_importacao import prever_importacao
from scripts.prever_importacao_anp import ler_json, main

HOJE = date(2026, 11, 24)

URL = (
    "https://www.gov.br/anp/pt-br/assuntos/"
    "precos-e-defesa-da-concorrencia/precos/arquivos-lpc/"
    "2026/revendas_lpc_2026_11_15-2026_11_21.xlsx"
)


def plano():
    dados = dict(
        uf="PB",
        municipio="JOAO PESSOA",
        cnpj="11222333000181",
        revenda="REVENDA FICTICIA",
        endereco="RUA EXEMPLO",
        numero="123",
        bairro="CENTRO",
        cep="58010000",
        bandeira="SEM BANDEIRA",
        produto_original="GASOLINA COMUM",
        preco_venda_original="6,19",
        unidade_original="R$ / litro",
        data_coleta="2026-11-16",
    )

    fonte = dict(
        arquivo="sintetico.csv",
        sha256="a" * 64,
        bytes=100,
        formato="csv",
        abas_lidas=[],
        registros=[
            dict(
                dados=dados,
                aba_lida="",
                linha_lida=2,
            )
        ],
    )

    catalogo = [
        dict(
            id=1,
            nome="FICTICIO",
            endereco="RUA EXEMPLO 123",
            bairro="CENTRO",
            cidade="JOAO PESSOA",
            uf="PB",
            tipo_posto="Convencional",
        )
    ]

    vinculos = {
        dados["cnpj"]: dict(
            posto_id=1,
            revisor="REVISOR FICTICIO",
            revisado_em="2026-11-24",
            evidencia=(
                "Evidência sintética da fixture; "
                "não é revisão real."
            ),
        )
    }

    return preparar(
        fonte,
        inicio=date(2026, 11, 15),
        fim=date(2026, 11, 21),
        referencia=HOJE,
        fonte_url=URL,
        catalogo=catalogo,
        vinculos=vinculos,
    )


def selar(p):
    p["sha256_plano"] = hash_json(
        {
            k: v
            for k, v in p.items()
            if k != "sha256_plano"
        }
    )

    return p


def snapshot(**extras):
    return dict(
        dict(
            versao=1,
            data_referencia=HOJE.isoformat(),
            precos=[],
            importacoes=[],
        ),
        **extras,
    )


def previa(p, estado=None):
    return prever_importacao(
        p,
        sha256_plano_esperado=p["sha256_plano"],
        referencia=HOJE,
        snapshot=estado,
    )


class PreviaImportacaoANPTests(unittest.TestCase):
    def arquivos_cli(self, pasta):
        original = plano()["registros"][0]["original"]
        arquivo = pasta / "fonte.csv"

        with arquivo.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as f:
            w = csv.DictWriter(
                f,
                fieldnames=list(original),
                delimiter=";",
            )
            w.writeheader()
            w.writerow(original)

        catalogo = pasta / "catalogo.json"

        catalogo.write_text(
            json.dumps(
                [
                    dict(
                        id=1,
                        nome="FICTICIO",
                        endereco="RUA EXEMPLO 123",
                        bairro="CENTRO",
                        cidade="JOAO PESSOA",
                        uf="PB",
                        tipo_posto="Convencional",
                    )
                ]
            ),
            encoding="utf-8",
        )

        vinculos = pasta / "vinculos.csv"

        vinculos.write_text(
            "cnpj;posto_id;confirmado;revisor;revisado_em;evidencia\n"
            "11222333000181;1;sim;REVISOR FICTICIO;"
            "2026-11-24;Evidência sintética suficiente\n",
            encoding="utf-8",
        )

        cat, sha_cat = ler_catalogo(catalogo)

        vin, sha_vin = ler_vinculos(
            vinculos,
            cat,
            HOJE,
            "PB",
            "JOAO PESSOA",
        )

        preparado = preparar(
            ler_arquivo(arquivo),
            inicio=date(2026, 11, 15),
            fim=date(2026, 11, 21),
            referencia=HOJE,
            fonte_url=URL,
            catalogo=cat,
            vinculos=vin,
            sha_catalogo=sha_cat,
            sha_vinculos=sha_vin,
        )

        plano_json = pasta / "plano.json"

        plano_json.write_text(
            json.dumps(preparado),
            encoding="utf-8",
        )

        args = [
            "--plano",
            str(plano_json),
            "--sha256-plano",
            preparado["sha256_plano"],
            "--arquivo-fonte",
            str(arquivo),
            "--catalogo-json",
            str(catalogo),
            "--vinculos",
            str(vinculos),
            "--data-referencia",
            "2026-11-24",
            "--saida",
            str(pasta / "saida"),
        ]

        return args, preparado

    def test_cli_reconstroi_fontes_e_vinculos_sem_escrever_banco(self):
        with tempfile.TemporaryDirectory() as t:
            pasta = Path(t)
            args, _ = self.arquivos_cli(pasta)

            self.assertEqual(main(args), 0)

            resultado = json.loads(
                (pasta / "saida/previa.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(
                resultado["resumo"]["observacoes"],
                1,
            )
            self.assertEqual(
                resultado["observacoes"][0]["acao"],
                "aguardando_snapshot",
            )
            self.assertFalse(resultado["apto_importacao"])

    def test_cli_fonte_diferente_nao_produz_previa(self):
        with tempfile.TemporaryDirectory() as t:
            pasta = Path(t)
            args, _ = self.arquivos_cli(pasta)

            with (pasta / "fonte.csv").open("a") as f:
                f.write("\n")

            self.assertEqual(main(args), 2)
            self.assertFalse((pasta / "saida").exists())

    def test_cli_rehash_forgedo_nao_substitui_reconstrucao(self):
        with tempfile.TemporaryDirectory() as t:
            pasta = Path(t)
            args, preparado = self.arquivos_cli(pasta)

            preparado["registros"][0]["avisos"].append(
                "alteracao_nao_presente_na_fonte"
            )

            selar(preparado)

            (pasta / "plano.json").write_text(
                json.dumps(preparado),
                encoding="utf-8",
            )

            args[args.index("--sha256-plano") + 1] = (
                preparado["sha256_plano"]
            )

            self.assertEqual(main(args), 2)
            self.assertFalse((pasta / "saida").exists())

    def test_cli_snapshot_simulado_identifica_candidata(self):
        with tempfile.TemporaryDirectory() as t:
            pasta = Path(t)
            args, _ = self.arquivos_cli(pasta)

            s = pasta / "snapshot.json"
            s.write_text(
                json.dumps(snapshot()),
                encoding="utf-8",
            )

            self.assertEqual(
                main(args + ["--snapshot-json", str(s)]),
                0,
            )

            r = json.loads(
                (pasta / "saida/previa.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(
                r["observacoes"][0]["acao"],
                "candidata_a_importacao_futura",
            )
            self.assertFalse(r["apto_importacao"])

    def test_sem_snapshot_nunca_autoriza_escrita(self):
        r = previa(plano())

        self.assertEqual(
            r["observacoes"][0]["acao"],
            "aguardando_snapshot",
        )
        self.assertIs(r["apto_importacao"], False)

        self.assertFalse(
            any(
                r["politica"][k]
                for k in (
                    "grava_banco",
                    "gera_karma",
                    "cria_postos",
                    "altera_oferta",
                    "gera_eventos_alertas",
                )
            )
        )

    def test_snapshot_vazio_propoe_candidata_mas_nao_autoriza(self):
        r = previa(plano(), snapshot())

        self.assertEqual(
            r["observacoes"][0]["acao"],
            "candidata_a_importacao_futura",
        )
        self.assertFalse(r["apto_importacao"])

    def test_nao_modifica_entradas(self):
        p = plano()
        s = snapshot()
        antes = deepcopy((p, s))

        previa(p, s)

        self.assertEqual((p, s), antes)

    def test_hash_alterado_ou_externo_divergente(self):
        p = plano()
        p["itens_revisados"][0]["preco"] = "5.00"

        with self.assertRaises(ErroANP):
            previa(p)

        with self.assertRaises(ErroANP):
            prever_importacao(
                plano(),
                sha256_plano_esperado="b" * 64,
                referencia=HOJE,
            )

    def test_rehash_nao_legitima_preco_invalido(self):
        for valor in [
            "0.00",
            "25.01",
            "6.191",
            "NaN",
            True,
        ]:
            with self.subTest(valor=valor):
                p = plano()
                p["itens_revisados"][0]["preco"] = valor
                p["registros"][0]["preco"] = valor

                p["registros"][0]["original"][
                    "preco_venda_original"
                ] = str(valor)

                with self.assertRaises(ErroANP):
                    previa(selar(p))

    def test_diesel_glp_e_unidade_incompativel_recusados(self):
        for produto, unidade in [
            ("DIESEL S10", "L"),
            ("DIESEL S500", "L"),
            ("GLP", "L"),
            ("GASOLINA COMUM", "m³"),
        ]:
            with self.subTest(
                produto=produto,
                unidade=unidade,
            ):
                p = plano()

                p["registros"][0]["original"][
                    "produto_original"
                ] = produto

                p["itens_revisados"][0]["unidade"] = unidade
                p["registros"][0]["unidade"] = unidade

                with self.assertRaises(ErroANP):
                    previa(selar(p))

    def test_vinculo_ausente_sem_revisor_ou_futuro(self):
        for campo, valor in [
            (None, None),
            ("revisor", ""),
            ("evidencia", "curta"),
            ("revisado_em", "2026-11-25"),
        ]:
            p = plano()

            if campo is None:
                p["vinculos_revisados"] = {}
            else:
                p["vinculos_revisados"][
                    "11222333000181"
                ][campo] = valor

            with self.assertRaises(ErroANP):
                previa(selar(p))

    def test_item_omitido_linha_duplicada_e_pendencia_recusados(self):
        for mudanca in [
            "omitido",
            "duplicada",
            "pendencia",
        ]:
            p = plano()

            if mudanca == "omitido":
                p["itens_revisados"] = []
            elif mudanca == "duplicada":
                p["registros"].append(
                    deepcopy(p["registros"][0])
                )
            else:
                p["registros"][0]["motivos"] = [
                    "cnpj_invalido"
                ]

            with self.assertRaises(ErroANP):
                previa(selar(p))

    def test_chave_nao_depende_nome_hash_arquivo_ou_ordem(self):
        p = plano()
        a = previa(p)["observacoes"][0]

        p["fonte"].update(
            arquivo="outro.csv",
            sha256="b" * 64,
        )

        b = previa(selar(p))["observacoes"][0]

        self.assertEqual(
            a["chave_observacao"],
            b["chave_observacao"],
        )
        self.assertEqual(
            a["hash_conteudo"],
            b["hash_conteudo"],
        )
        self.assertNotEqual(
            a["linhagens"],
            b["linhagens"],
        )

    def test_importacao_identica_ou_correcao_divergente(self):
        p = plano()
        o = previa(p)["observacoes"][0]

        for valor, acao in [
            (o["hash_conteudo"], "ja_importada"),
            ("b" * 64, "conflito_ledger"),
        ]:
            s = snapshot(
                importacoes=[
                    dict(
                        chave_observacao=o["chave_observacao"],
                        hash_conteudo=valor,
                    )
                ]
            )

            self.assertEqual(
                previa(p, s)["observacoes"][0]["acao"],
                acao,
            )

    def test_preserva_mesmo_dia_ou_mais_recente(self):
        for dia, acao in [
            (
                "2026-11-16",
                "preservar_preco_mesmo_dia_ou_mais_recente",
            ),
            (
                "2026-11-24",
                "preservar_preco_mesmo_dia_ou_mais_recente",
            ),
            (
                "2026-11-15",
                "candidata_a_importacao_futura",
            ),
        ]:
            s = snapshot(
                precos=[
                    dict(
                        posto_id=1,
                        codigo="gasolina_comum",
                        preco="6.20",
                        data_registro=dia,
                    )
                ]
            )

            self.assertEqual(
                previa(plano(), s)["observacoes"][0]["acao"],
                acao,
            )

    def test_snapshot_incompleto_duplicado_ou_futuro_recusado(self):
        preco = dict(
            posto_id=1,
            codigo="gasolina_comum",
            preco="6.20",
            data_registro="2026-11-25",
        )

        for s in [
            {},
            snapshot(versao=True),
            snapshot(data_referencia="2026-11-23"),
            snapshot(precos=[preco]),
            snapshot(
                precos=[
                    dict(
                        preco,
                        data_registro="2026-11-16",
                    )
                ] * 2
            ),
        ]:
            with self.assertRaises(ErroANP):
                previa(plano(), s)

    def test_referencia_explicita_e_preparacao_recente_obrigatorias(self):
        p = plano()

        with self.assertRaises(ErroANP):
            prever_importacao(
                p,
                sha256_plano_esperado=p["sha256_plano"],
                referencia=None,
            )

        p["data_referencia"] = "2026-11-23"

        with self.assertRaises(ErroANP):
            previa(selar(p))

    def test_json_nao_finito_e_chaves_repetidas_recusados(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "invalido.json"

            for texto in [
                '{"a": 1, "a": 2}',
                '{"a": NaN}',
            ]:
                f.write_text(
                    texto,
                    encoding="utf-8",
                )

                with self.assertRaises(ErroANP):
                    ler_json(f)

    def test_cli_falha_sem_criar_ou_sobrescrever_saida(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "invalido.json"

            f.write_text(
                '{"a": 1}',
                encoding="utf-8",
            )

            saida = Path(t) / "saida"

            args = [
                "--plano",
                str(f),
                "--sha256-plano",
                "a" * 64,
                "--arquivo-fonte",
                str(f),
                "--data-referencia",
                "2026-11-24",
                "--saida",
                str(saida),
            ]

            self.assertEqual(main(args), 2)
            self.assertFalse(saida.exists())

            saida.mkdir()

            (saida / "preservar").write_text(
                "original",
                encoding="utf-8",
            )

            self.assertEqual(main(args), 2)

            self.assertEqual(
                (saida / "preservar").read_text(
                    encoding="utf-8"
                ),
                "original",
            )


if __name__ == "__main__":
    unittest.main()