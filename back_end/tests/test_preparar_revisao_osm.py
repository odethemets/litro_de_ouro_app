"""Revisão sem rede/banco; não fabrica nomes nem decisões."""

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts import preparar_revisao_osm as review


class RevisaoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.pasta = Path(self.temp.name)
        self.fonte = self.pasta / "fonte.json"

        self.fonte.write_text(
            json.dumps({
                "elements": [{
                    "type": "node",
                    "id": 1,
                    "lat": -7.1,
                    "lon": -34.8,
                    "tags": {"amenity": "fuel"},
                }]
            }),
            encoding="utf-8",
        )

        self.sha = hashlib.sha256(
            self.fonte.read_bytes()
        ).hexdigest()

        self.item = {
            "id_externo": "osm:node:1",
            "nome": "Posto sem nome",
            "categoria": "ignorados",
            "motivo": "Sem name válido",
            "candidatos": [],
        }

    def executar(self, relatorio, nome="saida"):
        caminho = self.pasta / (nome + ".json")

        caminho.write_text(
            json.dumps(relatorio),
            encoding="utf-8",
        )

        return review.main([
            "--relatorio",
            str(caminho),
            "--fonte",
            str(self.fonte),
            "--saida",
            str(self.pasta / nome),
        ])

    def test_exporta_sem_fabricar_nome_ou_decisao(self):
        relatorio = {
            "status": "ok",
            "sha256_fonte": self.sha,
            "catalogo": {"itens": [self.item]},
        }

        self.assertEqual(self.executar(relatorio), 0)

        with (self.pasta / "saida/revisao.csv").open(
            encoding="utf-8-sig",
            newline="",
        ) as stream:
            linhas = list(csv.DictReader(
                stream,
                delimiter=";",
            ))

        self.assertEqual(len(linhas), 1)
        self.assertEqual(
            linhas[0]["decisao"], "pendente"
        )
        self.assertEqual(
            linhas[0]["nome_confirmado"], ""
        )
        self.assertEqual(
            linhas[0]["url_osm"],
            "https://www.openstreetmap.org/node/1",
        )

    def test_suporta_formato_da_previa_antiga(self):
        self.assertEqual(self.executar({
            "status": "ok",
            "sha256_fonte": self.sha,
            "previa": {"itens": [self.item]},
        }), 0)

    def test_recusa_fonte_diferente(self):
        self.assertEqual(self.executar({
            "status": "ok",
            "sha256_fonte": "0" * 64,
            "catalogo": {"itens": [self.item]},
        }), 1)

        self.assertFalse(
            (self.pasta / "saida").exists()
        )

    def test_nome_externo_nao_vira_formula(self):
        self.assertEqual(
            review.texto_csv("=IMPORTDATA(algo)"),
            "'=IMPORTDATA(algo)",
        )

    def test_nao_reexporta_postos_existentes(self):
        item = {
            **self.item,
            "categoria": "existentes",
        }

        self.assertEqual(
            review.gerar_linhas(
                {
                    "status": "ok",
                    "catalogo": {"itens": [item]},
                },
                {"elements": []},
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()