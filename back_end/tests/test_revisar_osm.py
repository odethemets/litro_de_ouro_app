"""Parser/classificador reais; banco e Overpass simulados."""
from argparse import Namespace
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import revisar_osm as cli
from scripts import importar_postos_osm as importador
from services import osm_service as osm


def resposta(*elementos):
    area = {
        "type": "area",
        "id": 3600000001,
        "tags": {
            "boundary": "administrative",
            "admin_level": "8",
            "IBGE:GEOCODIGO": "2507507",
        },
    }
    return {
        "osm3s": {
            "timestamp_osm_base": "2026-11-05T20:23:06Z",
        },
        "elements": [area, *elementos],
    }


def posto(ident, lat=-7.11, nome="Posto de teste"):
    tags = {"amenity": "fuel"}
    if nome is not None:
        tags["name"] = nome

    return {
        "type": "node",
        "id": ident,
        "lat": lat,
        "lon": -34.86,
        "tags": tags,
    }


# Implementa somente as consultas usadas pelo classificador.
class Banco:
    def __init__(self, nome="dev", registros=None):
        self.nome = nome
        self.registros = copy.deepcopy(registros or [])
        self.sql = []
        self.linhas = []
        self.reverteu = False
        self.fechou = False
        self.commitou = False

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        consulta = " ".join(sql.split())
        self.sql.append(consulta)

        if consulta == "SELECT DATABASE() AS banco":
            self.linhas = [{"banco": self.nome}]

        elif "WHERE mapbox_id = %s" in consulta:
            self.linhas = [
                r for r in self.registros
                if r.get("mapbox_id") == params[0]
            ]

        elif "WHERE latitude BETWEEN" in consulta:
            a, b, c, d = params
            self.linhas = [
                r for r in self.registros
                if a <= r["latitude"] <= b
                and c <= r["longitude"] <= d
            ]

        else:
            raise AssertionError("SQL inesperado no simulador")

    def fetchone(self):
        return copy.deepcopy(self.linhas[0]) if self.linhas else None

    def fetchall(self):
        return copy.deepcopy(self.linhas)

    def rollback(self):
        self.reverteu = True

    def close(self):
        self.fechou = True

    def commit(self):
        self.commitou = True


def argumentos(pasta, arquivo, somente=False):
    return Namespace(
        saida=str(pasta),
        arquivo=str(arquivo) if arquivo else None,
        joao_pessoa=arquivo is None,
        somente_fonte=somente,
        banco=None if somente else "dev",
        tentativas=1,
        max_espera=0,
    )


class RevisaoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.raiz = Path(self.temp.name)
        self.arquivo = self.raiz / "entrada.json"
        self.arquivo.write_text(
            json.dumps(resposta(posto(1))),
            encoding="utf-8",
        )

    def executar(self, corpo=None, banco=None, somente=False):
        if corpo is not None:
            self.arquivo.write_text(
                json.dumps(corpo),
                encoding="utf-8",
            )

        conectar = Mock(return_value=banco or Banco())
        resultado = cli.executar(
            argumentos(self.raiz / "saida", self.arquivo, somente),
            osm,
            importador,
            conectar,
        )
        return resultado, conectar

    def test_somente_fonte_preserva_bytes_hash_e_data(self):
        bruto = json.dumps(resposta(posto(1))).encode("utf-16")
        self.arquivo.write_bytes(bruto)

        resultado, conectar = self.executar(somente=True)

        self.assertEqual(resultado["status"], "ok")
        conectar.assert_not_called()

        pasta = self.raiz / "saida"
        self.assertEqual((pasta / "fonte.json").read_bytes(), bruto)

        manifesto = json.loads(
            (pasta / "manifesto.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            manifesto["sha256"]["fonte.json"],
            hashlib.sha256(bruto).hexdigest(),
        )
        self.assertEqual(
            manifesto["sha256"]["relatorio.json"],
            hashlib.sha256(
                (pasta / "relatorio.json").read_bytes()
            ).hexdigest(),
        )

        relatorio = json.loads(
            (pasta / "relatorio.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            relatorio["data_base_fonte_utc"],
            "2026-11-05T20:23:06+00:00",
        )

    def test_previa_classifica_sem_modificar_cadastro(self):
        registros = [{
            "id": 9,
            "mapbox_id": "osm:node:1",
            "latitude": -7.11,
            "longitude": -34.86,
            "nome": "Cadastro existente",
            "endereco": "Endereço manual",
            "tipo_posto": "Convencional",
        }]
        banco = Banco(registros=registros)

        resultado, conectar = self.executar(
            resposta(
                posto(1),
                posto(2, -7.13),
                posto(3, -7.15, None),
            ),
            banco,
        )

        self.assertEqual(resultado["status"], "ok")
        self.assertEqual(resultado["classificacao"]["existentes"], 1)
        self.assertEqual(resultado["classificacao"]["novos"], 1)
        self.assertEqual(resultado["classificacao"]["ignorados"], 1)
        self.assertEqual(banco.registros, registros)
        self.assertFalse(banco.commitou)
        self.assertTrue(banco.reverteu)
        self.assertTrue(banco.fechou)

        conectar.assert_called_once_with(
            read_only=True,
            time_zone="+00:00",
        )

    def test_manual_compativel_nao_recebe_vinculo_automatico(self):
        registros = [{
            "id": 9,
            "mapbox_id": None,
            "latitude": -7.11,
            "longitude": -34.86,
            "nome": "Posto de teste",
            "endereco": "",
            "tipo_posto": "Convencional",
        }]
        banco = Banco(registros=registros)

        resultado, _ = self.executar(banco=banco)

        self.assertEqual(resultado["status"], "ok")
        self.assertIsNone(banco.registros[0]["mapbox_id"])
        self.assertEqual(resultado["classificacao"]["vinculados"], 0)

    def test_banco_errado_falha_antes_de_classificar(self):
        banco = Banco("outro")

        resultado, _ = self.executar(banco=banco)

        self.assertEqual(resultado["status"], "falha")
        self.assertEqual(banco.sql, ["SELECT DATABASE() AS banco"])
        self.assertTrue(banco.fechou)
        self.assertFalse(banco.commitou)

    def test_fonte_incompleta_nao_chega_ao_banco(self):
        resultado, conectar = self.executar({
            "remark": "timeout",
            "elements": [],
        })

        self.assertEqual(resultado["status"], "falha")
        conectar.assert_not_called()
        self.assertFalse((self.raiz / "saida/fonte.json").exists())

    def test_outro_municipio_e_recusado(self):
        corpo = resposta(posto(1))
        corpo["elements"][0]["tags"]["IBGE:GEOCODIGO"] = "outro"

        resultado, conectar = self.executar(corpo)

        self.assertEqual(resultado["status"], "falha")
        conectar.assert_not_called()

    def test_pasta_existente_nao_e_sobrescrita(self):
        self.executar(somente=True)
        pasta = self.raiz / "saida"
        antes = {p.name: p.read_bytes() for p in pasta.iterdir()}

        with self.assertRaises(FileExistsError):
            self.executar(somente=True)

        depois = {p.name: p.read_bytes() for p in pasta.iterdir()}
        self.assertEqual(antes, depois)

    def test_fonte_online_reutiliza_limites_sem_rede_real(self):
        remoto = SimpleNamespace(
            validar_municipio=osm.validar_municipio,
            buscar_municipio=Mock(
                return_value=(resposta(posto(1)), {})
            ),
        )
        conectar = Mock()

        resultado = cli.executar(
            argumentos(self.raiz / "saida", None, True),
            remoto,
            importador,
            conectar,
        )

        self.assertEqual(resultado["status"], "ok")
        conectar.assert_not_called()
        remoto.buscar_municipio.assert_called_once_with(
            tentativas=1,
            max_espera=0,
        )

    def test_falha_http_nao_expoe_mensagem_nem_consulta_banco(self):
        remoto = SimpleNamespace(
            buscar_municipio=Mock(
                side_effect=osm.OSMIndisponivel(
                    "detalhe-privado",
                    status_http=403,
                )
            )
        )
        conectar = Mock()

        resultado = cli.executar(
            argumentos(self.raiz / "saida", None, True),
            remoto,
            importador,
            conectar,
        )

        self.assertEqual(resultado["status_http"], 403)
        conectar.assert_not_called()

        relatorio = (self.raiz / "saida/relatorio.json").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("detalhe-privado", relatorio)

    def test_cursor_bloqueia_escrita_multiplas_instrucoes_e_travas(self):
        original = Mock()
        cursor = cli.CursorPrevia(original)

        consultas = (
            "INSERT INTO postos VALUES (1)",
            "UPDATE postos SET nome='x'",
            "SELECT 1; DELETE FROM postos",
            "SELECT 1 FOR UPDATE",
            "SELECT 1 FOR SHARE",
            "SELECT 1 LOCK IN SHARE MODE",
            "SELECT GET_LOCK('x',0)",
            "SELECT 1 INTO OUTFILE '/tmp/x'",
        )

        for sql in consultas:
            with self.subTest(sql=sql), self.assertRaises(ValueError):
                cursor.execute(sql)

        original.execute.assert_not_called()

    def test_json_corrompido_ou_sem_postos_nao_chega_ao_banco(self):
        self.arquivo.write_text("{invalido", encoding="utf-8")

        resultado, conectar = self.executar()

        self.assertEqual(resultado["status"], "falha")
        conectar.assert_not_called()

        self.arquivo.write_text(
            json.dumps(resposta()),
            encoding="utf-8",
        )
        resultado = cli.executar(
            argumentos(self.raiz / "outra", self.arquivo),
            osm,
            importador,
            conectar,
        )

        self.assertEqual(resultado["status"], "falha")
        conectar.assert_not_called()


if __name__ == "__main__":
    unittest.main()