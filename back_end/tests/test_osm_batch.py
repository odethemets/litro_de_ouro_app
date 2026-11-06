"""Testes offline: sem consultas reais à Overpass ou ao MySQL."""

import copy
import io
import json
import os
import ssl
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import URLError


sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1]),
)

from services import osm_service as osm
from scripts import importar_postos_osm as cli


def posto(
    ident,
    lat=-7.11,
    lon=-34.86,
    nome="Posto Teste",
    **tags,
):
    atributos = {
        "amenity": "fuel",
        **tags,
    }

    if nome is not None:
        atributos["name"] = nome

    return {
        "type": "node",
        "id": ident,
        "lat": lat,
        "lon": lon,
        "tags": atributos,
    }


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
        "elements": [area, *elementos],
    }


class Banco:
    def __init__(self, rows=None, falhar=None):
        self.rows = copy.deepcopy(rows or [])
        self.antes = copy.deepcopy(self.rows)
        self.sql = []
        self.lastrowid = 0
        self.rowcount = 0
        self.commitou = False
        self.reverteu = False
        self.fechou = False
        self.falhar = falhar

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, sql, params=()):
        self.sql.append(sql)
        self.resultado = []

        if "GET_LOCK" in sql:
            self.resultado = [{
                "adquirido": 1,
            }]

        elif "WHERE mapbox_id = %s" in sql:
            self.resultado = [
                registro
                for registro in self.rows
                if registro.get("mapbox_id") == params[0]
            ]

        elif sql.startswith("SELECT"):
            a, b, c, d = params

            self.resultado = [
                registro
                for registro in self.rows
                if (
                    a <= registro["latitude"] <= b
                    and c <= registro["longitude"] <= d
                )
            ]

        elif sql.startswith("INSERT"):
            if self.falhar == "insert":
                raise RuntimeError("falha simulada")

            self.lastrowid = max(
                [registro["id"] for registro in self.rows]
                + [0]
            ) + 1

            campos = (
                "mapbox_id",
                "nome",
                "endereco",
                "bairro",
                "cidade",
                "uf",
                "latitude",
                "longitude",
                "horario_funcionamento",
                "tipo_posto",
            )

            self.rows.append(
                dict(
                    zip(campos, params),
                    id=self.lastrowid,
                )
            )

        else:
            raise AssertionError(
                "Escrita não autorizada pelo teste: "
                + sql
            )

    def fetchone(self):
        if self.resultado:
            return copy.deepcopy(
                self.resultado[0]
            )

        return None

    def fetchall(self):
        return copy.deepcopy(self.resultado)

    def commit(self):
        if self.falhar == "commit":
            raise RuntimeError(
                "ack desconhecido"
            )

        self.commitou = True

    def rollback(self):
        self.reverteu = True
        self.rows = copy.deepcopy(self.antes)

    def close(self):
        self.fechou = True


class AutomacaoTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "OSM_OVERPASS_URLS": ",".join(
                    osm.MIRRORS_PADRAO
                ),
                "OSM_USER_AGENT": (
                    "LitroDeOuro/teste "
                    "(https://github.com/"
                    "odethemets/litro_de_ouro_app)"
                ),
            },
        )

        self.env.start()
        self.addCleanup(self.env.stop)

    def test_query_area_sem_bbox(self):
        query = osm.montar_consulta_municipio()

        self.assertIn(
            '"IBGE:GEOCODIGO"="2507507"',
            query,
        )
        self.assertIn(
            '"admin_level"="8"',
            query,
        )
        self.assertIn(
            "(area.municipio)",
            query,
        )
        self.assertIn(
            ".municipio out tags;",
            query,
        )
        self.assertNotIn("-7.", query)

    def test_municipio_ausente_errado_ou_ambiguo(self):
        area = resposta()["elements"][0]

        casos = [
            {"elements": []},
            {
                "elements": [],
                "remark": "timeout",
            },
            {
                "elements": [area, area],
            },
        ]

        for dados in casos:
            with self.assertRaises(
                osm.OSMIndisponivel
            ):
                osm.validar_municipio(dados)

        dados = resposta()
        dados["elements"][0]["tags"][
            "IBGE:GEOCODIGO"
        ] = "0000000"

        with self.assertRaises(
            osm.OSMIndisponivel
        ):
            osm.validar_municipio(dados)

    def test_escopo_municipal_nao_trunca_na_bbox_legada(self):
        with patch.dict(
            os.environ,
            {
                "OSM_AREA_BBOX": (
                    "-7.12,-34.87,-7.10,-34.85"
                )
            },
        ):
            lugares, _ = cli.normalizar_entrada(
                resposta(
                    posto(1, lat=-7.2)
                )
            )

        self.assertEqual(len(lugares), 1)

    def test_http_user_agent_e_tls_padrao(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = (
            b'{"elements":[]}'
        )

        with patch.object(
            osm,
            "urlopen",
            return_value=response,
        ) as abrir:
            osm._consultar_overpass(
                "consulta",
                url=osm.MIRRORS_PADRAO[1],
                timeout=45,
            )

        requisicao = abrir.call_args.args[0]

        self.assertEqual(
            requisicao.full_url,
            osm.MIRRORS_PADRAO[1],
        )
        self.assertIn(
            "LitroDeOuro/teste",
            requisicao.get_header("User-agent"),
        )
        self.assertEqual(
            abrir.call_args.kwargs,
            {"timeout": 45},
        )

    def test_urls_e_header_invalidos(self):
        urls = [
            "http://host/api/interpreter",
            "https://user:senha@host/api/interpreter",
            "https://host/api/interpreter?key=secreto",
            "https://host:444/api/interpreter",
        ]

        for valor in urls:
            with patch.dict(
                os.environ,
                {
                    "OSM_OVERPASS_URLS": valor,
                },
            ):
                with self.assertRaises(ValueError):
                    osm.urls_configuradas()

        with patch.dict(
            os.environ,
            {
                "OSM_USER_AGENT": (
                    "App\r\nHeader: valor"
                ),
            },
        ):
            with self.assertRaises(ValueError):
                osm.user_agent_configurado()

    def test_fallback_respeita_retry_after(self):
        esperas = []

        erro = osm.OSMIndisponivel(
            "ocupado",
            429,
            75,
            True,
        )

        with patch.object(
            osm,
            "_consultar_overpass",
            side_effect=[
                erro,
                resposta(posto(1)),
            ],
        ) as consultar:
            _, meta = osm.buscar_municipio(
                dormir=esperas.append,
            )

        self.assertEqual(esperas, [75])
        self.assertEqual(
            meta["tentativas"],
            2,
        )

        self.assertNotEqual(
            consultar.call_args_list[0].kwargs["url"],
            consultar.call_args_list[1].kwargs["url"],
        )

    def test_nao_contorna_espera_excessiva_nem_erro_permanente(self):
        erros = [
            osm.OSMIndisponivel(
                "cota",
                429,
                600,
                True,
            ),
            osm.OSMIndisponivel(
                "negado",
                403,
                30,
                False,
            ),
        ]

        for erro in erros:
            with patch.object(
                osm,
                "_consultar_overpass",
                side_effect=erro,
            ) as consultar:
                with self.assertRaises(
                    osm.OSMIndisponivel
                ):
                    osm.buscar_municipio(
                        dormir=lambda _: self.fail(
                            "não deveria esperar"
                        ),
                    )

                self.assertEqual(
                    consultar.call_count,
                    1,
                )

    def test_erro_certificado_nao_desativa_tls(self):
        erro = URLError(
            ssl.SSLCertVerificationError(
                1,
                "segredo",
            )
        )

        with patch.object(
            osm,
            "urlopen",
            side_effect=erro,
        ):
            with self.assertRaises(
                osm.OSMIndisponivel
            ) as contexto:
                osm._consultar_overpass("consulta")

        self.assertFalse(
            contexto.exception.transitoria
        )
        self.assertNotIn(
            "segredo",
            str(contexto.exception),
        )

    def test_sem_nome_e_brand_isolada_nao_sao_importados(self):
        lugares, _ = cli.normalizar_entrada(
            resposta(
                posto(1, nome=None),
                posto(
                    2,
                    lat=-7.13,
                    nome=None,
                    brand="Shell",
                ),
            )
        )

        banco = Banco()

        relatorio = cli.executar(
            lugares,
            lambda: banco,
            True,
        )

        self.assertEqual(
            (
                relatorio["ignorados"],
                relatorio["inseridos"],
            ),
            (2, 0),
        )

        self.assertFalse(
            any(
                sql.startswith("INSERT")
                for sql in banco.sql
            )
        )

    def test_novo_nomeado_insert_e_idempotencia(self):
        lugares, _ = cli.normalizar_entrada(
            resposta(posto(1))
        )

        banco = Banco()

        relatorio = cli.executar(
            lugares,
            lambda: banco,
            True,
        )

        self.assertEqual(
            relatorio["inseridos"],
            1,
        )
        self.assertTrue(banco.commitou)

        banco.antes = copy.deepcopy(banco.rows)

        relatorio = cli.executar(
            lugares,
            lambda: banco,
        )

        self.assertEqual(
            (
                relatorio["novos"],
                relatorio["existentes"],
            ),
            (0, 1),
        )

    def test_previa_so_select(self):
        lugares, _ = cli.normalizar_entrada(
            resposta(posto(1))
        )

        banco = Banco()

        cli.executar(
            lugares,
            lambda: banco,
        )

        self.assertTrue(
            all(
                sql.startswith("SELECT")
                for sql in banco.sql
            )
        )
        self.assertFalse(banco.commitou)
        self.assertTrue(banco.reverteu)

    def test_match_manual_nao_vincula(self):
        lugares, _ = cli.normalizar_entrada(
            resposta(posto(1))
        )

        existente = dict(
            lugares[0],
            id=9,
            mapbox_id=None,
        )

        banco = Banco([existente])

        relatorio = cli.executar(
            lugares,
            lambda: banco,
            True,
        )

        self.assertEqual(
            (
                relatorio["existentes"],
                relatorio["vinculados"],
                relatorio["inseridos"],
            ),
            (1, 0, 0),
        )

        self.assertEqual(
            relatorio["itens"][0]["acao"],
            "manter_sem_vincular",
        )
        self.assertIsNone(
            banco.rows[0]["mapbox_id"]
        )

    def test_ambiguo_no_banco_nao_grava(self):
        lugares, _ = cli.normalizar_entrada(
            resposta(posto(1))
        )

        existente = dict(
            lugares[0],
            id=9,
            mapbox_id=None,
            nome="Outro nome",
        )

        banco = Banco([existente])

        relatorio = cli.executar(
            lugares,
            lambda: banco,
            True,
        )

        self.assertEqual(
            (
                relatorio["ambiguos"],
                relatorio["inseridos"],
            ),
            (1, 0),
        )

    def test_pares_proximos_ambos_ignorados_sem_depender_da_ordem(self):
        lugares, _ = cli.normalizar_entrada(
            resposta(
                posto(1),
                posto(
                    2,
                    nome="Outro objeto",
                ),
            )
        )

        for entrada in [
            lugares,
            list(reversed(lugares)),
        ]:
            banco = Banco()

            relatorio = cli.executar(
                entrada,
                lambda: banco,
                True,
            )

            self.assertEqual(
                (
                    relatorio["ambiguos"],
                    relatorio["inseridos"],
                ),
                (2, 0),
            )

    def test_transacao_reverte_e_nao_altera_historicos(self):
        lugares, _ = cli.normalizar_entrada(
            resposta(posto(1))
        )

        for falha in ["insert", "commit"]:
            banco = Banco(falhar=falha)

            with self.assertRaises(RuntimeError):
                cli.executar(
                    lugares,
                    lambda: banco,
                    True,
                )

            self.assertTrue(
                banco.reverteu and banco.fechou
            )
            self.assertEqual(banco.rows, [])

            self.assertFalse(
                any(
                    "UPDATE" in sql
                    or "DELETE" in sql
                    or "registos_preco" in sql
                    for sql in banco.sql
                )
            )

    def test_teste_conexao_e_somente_fonte_nao_abrem_mysql(self):
        modos = [
            ["--teste-conexao"],
            [
                "--joao-pessoa",
                "--somente-fonte",
            ],
        ]

        for modo in modos:
            with (
                patch.object(
                    osm,
                    "testar_conexao",
                    return_value={
                        "tentativas": 1,
                    },
                ),
                patch.object(
                    osm,
                    "buscar_municipio",
                    return_value=(
                        resposta(posto(1)),
                        {},
                    ),
                ),
                redirect_stdout(io.StringIO()),
            ):
                codigo = cli.main(
                    modo,
                    get_conn=lambda: self.fail(
                        "MySQL proibido"
                    ),
                )

            self.assertEqual(codigo, 0)

    def test_json_municipal_salvo_permite_previa_offline(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "fonte.json"
            relatorio = Path(pasta) / "report.json"

            cli.salvar_json(
                arquivo,
                resposta(posto(1)),
            )

            banco = Banco()

            with (
                patch.object(
                    osm,
                    "urlopen",
                    side_effect=AssertionError(
                        "rede proibida"
                    ),
                ),
                redirect_stdout(io.StringIO()),
            ):
                codigo = cli.main(
                    [
                        "--arquivo",
                        str(arquivo),
                        "--dry-run",
                        "--relatorio",
                        str(relatorio),
                    ],
                    lambda: banco,
                )

            self.assertEqual(codigo, 0)

            dados = json.loads(
                relatorio.read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(
                dados["novos"],
                1,
            )

    def test_json_sem_area_so_permite_previa(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "fonte.json"

            cli.salvar_json(
                arquivo,
                {
                    "elements": [posto(1)],
                },
            )

            with redirect_stdout(io.StringIO()):
                codigo = cli.main(
                    [
                        "--arquivo",
                        str(arquivo),
                        "--aplicar",
                    ],
                    lambda: self.fail(
                        "MySQL proibido"
                    ),
                )

            self.assertNotEqual(codigo, 0)

    def test_fonte_sem_area_nao_chega_ao_banco_e_grava_falha(self):
        with tempfile.TemporaryDirectory() as pasta:
            relatorio = Path(pasta) / "report.json"

            with (
                patch.object(
                    osm,
                    "buscar_municipio",
                    return_value=(
                        {"elements": []},
                        {},
                    ),
                ),
                redirect_stdout(io.StringIO()),
            ):
                codigo = cli.main(
                    [
                        "--joao-pessoa",
                        "--aplicar",
                        "--relatorio",
                        str(relatorio),
                    ],
                    lambda: self.fail(
                        "MySQL proibido"
                    ),
                )

            self.assertEqual(codigo, 2)

            dados = json.loads(
                relatorio.read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(
                dados["status"],
                "falha_fonte",
            )

    def test_falha_db_nao_expoe_segredos(self):
        segredo_ficticio = "senha-ultrassecreta"

        with tempfile.TemporaryDirectory() as pasta:
            relatorio = Path(pasta) / "report.json"
            saida = io.StringIO()

            with (
                patch.object(
                    osm,
                    "buscar_municipio",
                    return_value=(
                        resposta(posto(1)),
                        {},
                    ),
                ),
                redirect_stdout(saida),
            ):
                def falhar():
                    raise RuntimeError(
                        segredo_ficticio
                    )

                codigo = cli.main(
                    [
                        "--joao-pessoa",
                        "--aplicar",
                        "--relatorio",
                        str(relatorio),
                    ],
                    falhar,
                )

            self.assertEqual(codigo, 3)

            conteudo = relatorio.read_text(
                encoding="utf-8"
            )

            self.assertNotIn(
                segredo_ficticio,
                saida.getvalue() + conteudo,
            )

            self.assertIn(
                "nao_confirmada",
                json.loads(conteudo)["gravacao"],
            )


if __name__ == "__main__":
    unittest.main()