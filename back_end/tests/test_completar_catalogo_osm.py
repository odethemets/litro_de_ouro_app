"""Regras de enriquecimento e guardas locais; nao conecta a servicos externos."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import completar_catalogo_osm as cli


def posto(ident=5, externo="osm:node:100", **alteracoes):
    return dict(id=ident, mapbox_id=externo, nome="Posto fonte", latitude=-7.11,
                longitude=-34.86, tipo_posto="Convencional", marca=None, marca_origem=None,
                **alteracoes)


def fonte(marca="Shell", ofertas=None):
    return {"elementos": {"osm:node:100": {"marca": marca, "ofertas": ofertas or {}, "avisos": []}}}


class TagsTests(unittest.TestCase):
    def test_alias_etanol_explicito(self):
        for k in ("fuel:ethanol", "fuel:etanol_comum"):
            self.assertEqual(cli.ofertas_explicitas({k: "yes"})[0], {"etanol": 1})

    def test_ausencia_preserva_desconhecidos(self):
        self.assertEqual(cli.ofertas_explicitas({"amenity": "fuel"})[0], {})

    def test_gasoline_octanagem_e_e10_nao_distinguem_aditivacao(self):
        ofertas, avisos = cli.ofertas_explicitas({"fuel:gasoline": "yes", "fuel:octane_87": "yes", "fuel:e10": "yes"})
        self.assertEqual(ofertas, {})
        self.assertEqual(len(avisos), 3)

    def test_produto_explicito_comum_e_aditivada_separados(self):
        self.assertEqual(cli.ofertas_explicitas({"fuel:gasolina_comum": "yes", "fuel:gasolina_aditivada": "no"})[0],
                         {"gasolina_comum": 1, "gasolina_aditivada": 0})

    def test_cng_e_gnv_mas_ar_comprimido_e_lpg_nao(self):
        self.assertEqual(cli.ofertas_explicitas({"fuel:cng": "yes", "compressed_air": "yes", "fuel:lpg": "yes"})[0], {"gnv": 1})
        self.assertEqual(cli.ofertas_explicitas({"compressed_air": "yes", "fuel:lpg": "yes"})[0], {})

    def test_diesel_subtipo_positivo_confirma_categoria(self):
        self.assertEqual(cli.ofertas_explicitas({"fuel:diesel_s10": "yes", "fuel:diesel_s500": "no"})[0], {"diesel": 1})

    def test_subtipos_negativos_nao_negam_todo_diesel(self):
        self.assertEqual(cli.ofertas_explicitas({"fuel:diesel_s10": "no", "fuel:diesel_s500": "no"})[0], {})

    def test_categoria_negativa_explicita(self):
        self.assertEqual(cli.ofertas_explicitas({"fuel:diesel": "no"})[0], {"diesel": 0})

    def test_conflito_diesel_nao_e_inventado(self):
        ofertas, avisos = cli.ofertas_explicitas({"fuel:diesel": "no", "fuel:diesel_s10": "yes"})
        self.assertEqual(ofertas, {})
        self.assertTrue(avisos)

    def test_conflito_entre_aliases_preserva_desconhecido(self):
        self.assertEqual(cli.ofertas_explicitas({"fuel:ethanol": "yes", "fuel:etanol_comum": "no"})[0], {})

    def test_valores_nao_reconhecidos_nao_viram_sim(self):
        for v in (None, 1, True, "sometimes", ""):
            self.assertEqual(cli.ofertas_explicitas({"fuel:ethanol": v})[0], {})

    def test_eletroposto_explicito_e_conflito(self):
        self.assertEqual(cli.ofertas_explicitas({"amenity": "charging_station"})[0], {"recarga_eletrica": 1})
        self.assertEqual(cli.ofertas_explicitas({"amenity": "charging_station", "fuel:electricity": "no"})[0], {})


class PlanoTests(unittest.TestCase):
    def test_so_id_externo_exato_sem_vinculos_por_nome(self):
        plano, encontrados = cli.planejar(fonte(ofertas={"etanol": 1}), [posto(externo=None)], [])
        self.assertEqual((plano, encontrados), ([], 0))

    def test_marca_e_oferta_sao_operacoes_independentes(self):
        plano, encontrados = cli.planejar(fonte(ofertas={"etanol": 1}), [posto()], [])
        self.assertEqual(encontrados, 1)
        self.assertEqual([p["tipo"] for p in plano], ["marca", "oferta_osm"])

    def test_preserva_marca_existente_e_origem_manual(self):
        for marca, origem in (("Marca revisada", "manual"), ("Marca antiga", "osm"), (None, "manual")):
            p = posto(); p.update(marca=marca, marca_origem=origem)
            self.assertEqual(cli.planejar(fonte(), [p], [])[0], [])

    def test_preserva_estados_existentes_inclusive_nao(self):
        for manual, osm in ((0, None), (1, None), (None, 0), (None, 1), (0, 1)):
            atual = dict(posto_id=5, combustivel_codigo="etanol", disponivel_manual=manual, disponivel_osm=osm)
            plano, _ = cli.planejar(fonte(marca=None, ofertas={"etanol": 1}), [posto()], [atual])
            self.assertEqual(plano, [])

    def test_atualiza_linha_desconhecida_sem_inserir_duplicata(self):
        atual = dict(posto_id=5, combustivel_codigo="etanol", disponivel_manual=None, disponivel_osm=None)
        plano, _ = cli.planejar(fonte(marca=None, ofertas={"etanol": 1}), [posto()], [atual])
        self.assertEqual(len(plano), 1)
        self.assertTrue(plano[0]["existe"])

    def test_oferta_ausente_nao_gera_linhas_falsas(self):
        self.assertEqual(cli.planejar(fonte(marca=None), [posto()], [])[0], [])

    def test_duplicidade_local_bloqueia(self):
        with self.assertRaises(cli.ErroCatalogo):
            cli.planejar(fonte(), [posto(), posto(ident=6)], [])

    def fixtures(self):
        return [dict(id=i, mapbox_id=None, nome=n, latitude=lat, longitude=lon, tipo_posto=t, marca=None, marca_origem=None)
                for i, (n, lat, lon, t, _) in cli.FIXTURES.items()]

    def test_fixtures_sao_opcionais_e_nao_derivadas_dos_precos(self):
        fixtures = self.fixtures()
        self.assertEqual(cli.planejar(fonte(marca=None), fixtures, [])[0], [])
        plano, _ = cli.planejar(fonte(marca=None), fixtures, [], True)
        self.assertEqual(len(plano), 5)
        self.assertTrue(all(p["tipo"] == "oferta_teste" for p in plano))
        self.assertTrue(any(p["posto_id"] == 4 for p in plano))

    def test_fixtures_alteradas_bloqueiam_antes_da_escrita(self):
        for campo, valor in (("nome", "Posto real"), ("latitude", -8), ("mapbox_id", "osm:node:100"), ("tipo_posto", "Eletroposto")):
            fixtures = self.fixtures(); fixtures[0][campo] = valor
            with self.subTest(campo=campo), self.assertRaises(cli.ErroCatalogo):
                cli.planejar(fonte(), fixtures, [], True)


class FonteCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "fonte.json"
        self.corpo = {"osm3s": {"timestamp_osm_base": "2026-11-11T03:05:04Z"}, "elements": [
            {"type": "area", "id": 3600301405, "tags": {"IBGE:GEOCODIGO": "2507507", "boundary": "administrative", "admin_level": "8"}},
            {"type": "node", "id": 100, "lat": -7.11, "lon": -34.86,
             "tags": {"amenity": "fuel", "name": "Posto fonte", "brand": "BR", "fuel:ethanol": "yes"}}]}
        self.escrever()

    def escrever(self):
        self.path.write_text(json.dumps(self.corpo), encoding="utf-8")

    def rodar(self, argumentos):
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            codigo = cli.main(["--arquivo", str(self.path), *argumentos])
        return codigo, json.loads(saida.getvalue())

    def test_fonte_normaliza_bandeira_e_data_utc(self):
        f = cli.carregar_fonte(self.path)
        self.assertEqual(f["elementos"]["osm:node:100"]["marca"], "Petrobras")
        self.assertEqual(str(f["data_base_utc"]), "2026-11-11 03:05:04")

    def test_sha_divergente_bloqueia_antes_de_conectar(self):
        with patch.object(cli, "conectar_local") as conectar:
            codigo, _ = self.rodar(["--sha256", "0" * 64])
            self.assertEqual(codigo, 1); conectar.assert_not_called()

    def test_area_ausente_bloqueia_antes_de_conectar(self):
        self.corpo["elements"].pop(0); self.escrever()
        with patch.object(cli, "conectar_local") as conectar:
            self.assertEqual(self.rodar([])[0], 1); conectar.assert_not_called()

    def test_data_sem_fuso_rejeitada(self):
        self.corpo["osm3s"]["timestamp_osm_base"] = "2026-11-11T03:05:04"; self.escrever()
        with self.assertRaises(cli.ErroCatalogo): cli.carregar_fonte(self.path)

    def test_id_conflitante_rejeitado(self):
        outro = copy.deepcopy(self.corpo["elements"][1]); outro["tags"]["brand"] = "Shell"
        self.corpo["elements"].append(outro); self.escrever()
        with self.assertRaises(cli.ErroCatalogo): cli.carregar_fonte(self.path)

    def test_somente_fonte_nao_consulta_mysql(self):
        with patch.object(cli, "conectar_local") as conectar:
            codigo, r = self.rodar(["--somente-fonte"])
            self.assertEqual(codigo, 0); self.assertFalse(r["mysql_consultado"]); conectar.assert_not_called()

    def test_padrao_e_previa_sem_gravacao(self):
        with patch.object(cli, "conectar_local") as conectar, patch.object(cli, "executar", return_value={"status": "ok"}) as executar:
            self.assertEqual(self.rodar([])[0], 0)
            conectar.assert_called_once_with(False)
            self.assertFalse(executar.call_args.args[2])

    def test_aplicar_exige_todos_guardas_antes_de_conectar(self):
        for argumentos in (["--aplicar"], ["--aplicar", "--banco", "online"], ["--aplicar", "--banco", cli.BANCO, "--sha256", "0" * 64]):
            with patch.object(cli, "conectar_local") as conectar:
                self.assertEqual(self.rodar(argumentos)[0], 1); conectar.assert_not_called()

    def test_configuracao_online_bloqueia_antes_da_conexao(self):
        from services.database import DatabaseConfig
        config = DatabaseConfig("online.example", 3306, "litro_local", "nao-real", cli.BANCO)
        with patch.object(cli, "load_config", return_value=config), patch.object(cli, "get_db_connection") as conectar, patch.dict(os.environ, {"LDO_DOCKER_LOCAL": "1", "DATABASE_URL": ""}):
            with self.assertRaises(cli.ErroCatalogo): cli.conectar_local()
            conectar.assert_not_called()

    def test_conexao_sem_tls_verificado_e_rejeitada(self):
        from services.database import DatabaseConfig
        config = DatabaseConfig("db", 3306, "litro_local", "nao-real", cli.BANCO)
        conn = Mock(_sock=None)
        with patch.object(cli, "load_config", return_value=config), patch.object(cli, "get_db_connection", return_value=conn), patch.dict(os.environ, {"LDO_DOCKER_LOCAL": "1", "DATABASE_URL": ""}):
            with self.assertRaises(cli.ErroCatalogo): cli.conectar_local()
            conn.close.assert_called_once()

    def test_backup_exclusivo_preserva_arquivo_anterior(self):
        destino = Path(self.tmp.name) / "antes.json"
        cli.salvar_backup(destino, {"antes": "preservar"})
        with self.assertRaises(FileExistsError): cli.salvar_backup(destino, {"antes": "sobrescrever"})
        self.assertEqual(json.loads(destino.read_text()), {"antes": "preservar"})

    def test_backup_relativo_e_rejeitado(self):
        with self.assertRaises(cli.ErroCatalogo): cli.salvar_backup("antes.json", {})


if __name__ == "__main__":
    unittest.main()