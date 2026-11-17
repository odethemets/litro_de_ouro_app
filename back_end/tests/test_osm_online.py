"""SQLite exercita DML/rollback; comandos de servidor e validação de schema simulados."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import migrar_banco, sincronizar_osm_online as cli
from services import osm_online as osm
from services.migrations import load_migrations

sqlite3.register_adapter(datetime, lambda d: d.isoformat(" "))
sqlite3.register_converter("timestamp", lambda b: datetime.fromisoformat(b.decode()))


class Cursor:
    def __init__(self, banco):
        self.banco = banco
        self.cursor = banco.db.cursor()
        self.especial = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.cursor.close()

    def execute(self, sql, params=()):
        self.banco.sql.append(sql)
        self.especial = None
        if sql.startswith("SELECT DATABASE()"):
            self.especial = [{"banco": self.banco.nome, "versao": self.banco.versao}]
            return
        if sql.startswith("SET SESSION"):
            return
        if self.banco.falhar_meta and sql.startswith("UPDATE postos SET marca"):
            raise OSError("detalhe-privado")
        sql = sql.replace(" FOR UPDATE", "").replace("%s", "?")
        self.cursor.execute(sql, params)

    def fetchone(self):
        if self.especial is not None:
            return self.especial[0] if self.especial else None
        r = self.cursor.fetchone()
        return dict(r) if r is not None else None

    def fetchall(self):
        return self.especial if self.especial is not None else [dict(r) for r in self.cursor.fetchall()]

    @property
    def rowcount(self):
        return self.cursor.rowcount

    @property
    def lastrowid(self):
        return self.cursor.lastrowid


class Banco:
    def __init__(self, migracoes):
        self.nome = "catalogo"
        self.versao = "8.0.11-TiDB-v8.5.3-serverless"
        self.sql = []
        self.falhar_meta = self.falhar_commit = False
        self.db = sqlite3.connect(":memory:", isolation_level=None, detect_types=sqlite3.PARSE_DECLTYPES)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE postos (id INTEGER PRIMARY KEY, mapbox_id TEXT UNIQUE, nome TEXT,
              endereco TEXT, bairro TEXT, cidade TEXT, uf TEXT, latitude REAL, longitude REAL,
              horario_funcionamento TEXT, tipo_posto TEXT, marca TEXT, marca_origem TEXT);
            CREATE TABLE postos_combustiveis (posto_id INT, combustivel_codigo TEXT,
              disponivel_osm INT, osm_verificado_em TIMESTAMP, disponivel_manual INT,
              manual_atualizado_em TIMESTAMP, manual_atualizado_por INT,
              PRIMARY KEY(posto_id,combustivel_codigo));
            CREATE TABLE schema_migrations (versao TEXT PRIMARY KEY,sha256 TEXT,estado TEXT);
        ''')
        for m in migracoes:
            self.db.execute("INSERT INTO schema_migrations VALUES (?,?,?)", (m["versao"], m["sha256"], "aplicada"))

    def cursor(self):
        return Cursor(self)

    def begin(self):
        self.db.execute("BEGIN IMMEDIATE")

    def rollback(self):
        self.db.rollback()

    def commit(self):
        self.db.commit()
        if self.falhar_commit:
            raise OSError("resposta-do-commit-perdida")

    def close(self):
        self.fechou = True


class OSMTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.pasta = Path(self.temp.name)
        self.migracoes = load_migrations(cli.ROOT / "migrations")
        self.banco = Banco(self.migracoes)
        self.addCleanup(self.banco.db.close)
        self.agora = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
        corpo = {"osm3s": {"timestamp_osm_base": self.agora.isoformat() + "Z"}, "elements": [
            {"type": "area", "id": 3600000001, "tags": {"boundary": "administrative",
                "admin_level": "8", "IBGE:GEOCODIGO": "2507507"}},
            {"type": "node", "id": 10, "lat": -7.11, "lon": -34.86,
             "tags": {"amenity": "fuel", "name": "Posto fonte", "brand": "Shell", "fuel:gasolina_comum": "yes"}},
        ]}
        self.arquivo = self.pasta / "entrada.json"
        self.arquivo.write_text(json.dumps(corpo), encoding="utf-8")
        arquivo_saida = self.pasta / "fonte"
        arquivo_saida.mkdir()
        self.fonte, self.lugares, _ = cli.preparar_fonte(self.arquivo, arquivo_saida)

    def executar(self, aplicar=False, backup=None):
        return osm.sincronizar(self.banco, self.fonte, self.lugares, self.migracoes,
                               "catalogo", aplicar, backup or Mock(), verificar=Mock())

    def test_previa_inclui_metadados_dos_novos_sem_escrever(self):
        r = self.executar()
        self.assertEqual(r["catalogo"]["novos"], 1)
        self.assertEqual(len(r["plano_metadados"]), 2)
        self.assertEqual(self.banco.db.execute("SELECT COUNT(*) FROM postos").fetchone()[0], 0)
        self.assertFalse(any(s.startswith(("UPDATE", "INSERT", "DELETE")) for s in self.banco.sql))

    def test_aplicacao_e_repeticao_idempotente(self):
        backup = Mock()
        r = self.executar(True, backup)
        self.assertEqual(r["catalogo"]["inseridos"], 1)
        self.assertEqual(r["metadados_aplicados"], 2)
        backup.assert_called_once()
        self.assertEqual(backup.call_args.args[0]["postos"], [])
        r = self.executar(True)
        self.assertEqual(r["catalogo"]["existentes"], 1)
        self.assertEqual(r["catalogo"]["inseridos"], 0)
        self.assertEqual(r["metadados_aplicados"], 0)
        self.assertEqual(r["precos_modificados"], 0)

    def test_dados_manuais_preservados(self):
        self.executar(True)
        self.banco.db.execute("UPDATE postos SET marca='Marca manual',marca_origem='manual'")
        self.banco.db.execute("UPDATE postos_combustiveis SET disponivel_manual=0")
        r = self.executar(True)
        self.assertEqual(r["metadados_aplicados"], 0)
        self.assertEqual(self.banco.db.execute("SELECT marca FROM postos").fetchone()[0], "Marca manual")
        self.assertEqual(self.banco.db.execute("SELECT disponivel_manual FROM postos_combustiveis").fetchone()[0], 0)

    def test_oferta_explicita_mais_recente_atualiza_osm(self):
        self.executar(True)
        self.fonte["data_base_utc"] += timedelta(seconds=1)
        self.fonte["elementos"]["osm:node:10"]["ofertas"]["gasolina_comum"] = 0
        self.assertEqual(self.executar(True)["metadados_aplicados"], 1)
        self.assertEqual(self.banco.db.execute("SELECT disponivel_osm FROM postos_combustiveis").fetchone()[0], 0)

    def test_fonte_antiga_nao_regride_oferta(self):
        self.executar(True)
        self.fonte["data_base_utc"] -= timedelta(days=1)
        self.fonte["elementos"]["osm:node:10"]["ofertas"]["gasolina_comum"] = 0
        self.assertEqual(self.executar(True)["metadados_aplicados"], 0)

    def test_mesma_data_conflitante_aborta(self):
        self.executar(True)
        self.fonte["elementos"]["osm:node:10"]["ofertas"]["gasolina_comum"] = 0
        with self.assertRaises(osm.FalhaOSM) as r:
            self.executar(True)
        self.assertEqual(r.exception.codigo, "fontes_conflitantes_na_mesma_data")

    def test_ausencia_de_tag_nao_remove_oferta(self):
        self.executar(True)
        self.fonte["elementos"]["osm:node:10"]["ofertas"] = {}
        self.assertEqual(self.executar(True)["metadados_aplicados"], 0)
        self.assertEqual(self.banco.db.execute("SELECT COUNT(*) FROM postos_combustiveis").fetchone()[0], 1)

    def test_rollback_de_postos_se_metadado_falha(self):
        self.banco.falhar_meta = True
        with self.assertRaises(osm.FalhaOSM):
            self.executar(True)
        self.assertEqual(self.banco.db.execute("SELECT COUNT(*) FROM postos").fetchone()[0], 0)

    def test_backup_falha_antes_de_inserir(self):
        with self.assertRaises(osm.FalhaOSM):
            self.executar(True, Mock(side_effect=OSError("privado")))
        self.assertEqual(self.banco.db.execute("SELECT COUNT(*) FROM postos").fetchone()[0], 0)

    def test_commit_incerto_e_reconsulta_por_repeticao(self):
        self.banco.falhar_commit = True
        with self.assertRaises(osm.FalhaOSM) as r:
            self.executar(True)
        self.assertTrue(r.exception.commit_incerto)
        self.banco.falhar_commit = False
        self.assertEqual(self.executar(True)["catalogo"]["inseridos"], 0)

    def test_banco_errado_para_antes_de_locks_ou_dml(self):
        self.banco.nome = "outro"
        with self.assertRaises(osm.FalhaOSM):
            self.executar(True)
        self.assertEqual(len(self.banco.sql), 1)

    def test_coordenacao_usa_pessimista_e_nao_get_lock(self):
        self.executar(True)
        sql = "\n".join(self.banco.sql)
        self.assertIn("tidb_txn_mode = 'pessimistic'", sql)
        self.assertIn("READ COMMITTED", sql)
        self.assertIn("WHERE versao=%s FOR UPDATE", sql)
        self.assertNotIn("GET_LOCK", sql)

    def test_migracao_pendente_aborta_antes_da_escrita(self):
        with patch.object(osm, "run", return_value={"migracoes": [{"estado": "pendente"}]}):
            with self.assertRaises(osm.ErroOSM):
                osm.validar_migracoes(self.banco, self.migracoes, "catalogo")

    def test_hash_errado_nao_abre_banco(self):
        saida = self.pasta / "hasherrado"
        with patch.object(cli, "get_db_connection") as conectar, patch("builtins.print"):
            r = cli.main(["--arquivo", str(self.arquivo), "--banco", "catalogo",
                          "--env-file", "ausente", "--saida", str(saida), "--aplicar", "--sha256", "0" * 64])
        self.assertEqual(r, 1)
        conectar.assert_not_called()

    def test_pasta_existente_recusa_antes_de_conectar(self):
        with patch.object(cli, "get_db_connection") as conectar, patch("builtins.print"):
            r = cli.main(["--arquivo", str(self.arquivo), "--banco", "catalogo",
                          "--env-file", "ausente", "--saida", str(self.pasta)])
        self.assertEqual(r, 2)
        conectar.assert_not_called()

    def test_data_futura_ou_antiga_recusada(self):
        for d in (self.agora + timedelta(minutes=6), self.agora - timedelta(days=31)):
            with self.assertRaises(osm.ErroOSM):
                osm.validar_data(d, self.agora)

    def test_migrador_recebe_env_separado(self):
        arquivo = self.pasta / "conexao.env"
        arquivo.write_text("DB_HOST=banco.invalid\nDB_PORT=4000\nDB_USER=usuario\nDB_PASSWORD=ficticia\nDB_NAME=catalogo\n")
        conn = Mock()
        with patch.object(migrar_banco, "get_db_connection", return_value=conn) as conectar:
            with patch.object(migrar_banco, "run", return_value={"status": "ok"}) as executar:
                with patch.object(migrar_banco, "emit_report"):
                    r = migrar_banco.main(["--banco", "catalogo", "--env-file", str(arquivo)])
        self.assertEqual(r, 0)
        self.assertEqual(conectar.call_args.kwargs["config"].database, "catalogo")
        self.assertTrue(conectar.call_args.kwargs["read_only"])
        self.assertFalse(executar.call_args.kwargs["apply"])

    def test_cli_integra_transacao_backup_e_manifesto(self):
        arquivo = self.pasta / "conexao.env"
        arquivo.write_text("DB_HOST=banco.invalid\nDB_PORT=4000\nDB_USER=usuario\nDB_PASSWORD=ficticia\nDB_NAME=catalogo\n")
        saida = self.pasta / "aplicacao"
        with patch.object(cli, "get_db_connection", return_value=self.banco):
            with patch.object(osm, "run", return_value={"migracoes": [{"estado": "aplicada"}]}):
                with patch("builtins.print"):
                    codigo = cli.main(["--arquivo", str(self.arquivo), "--banco", "catalogo",
                        "--env-file", str(arquivo), "--saida", str(saida), "--aplicar",
                        "--sha256", self.fonte["sha256"]])
        self.assertEqual(codigo, 0)
        self.assertTrue(self.banco.fechou)
        self.assertTrue((saida / "backup_metadados.json").is_file())
        r = json.loads((saida / "relatorio.json").read_text(encoding="utf-8"))
        self.assertEqual(r["catalogo"]["inseridos"], 1)
        m = json.loads((saida / "manifesto.json").read_text(encoding="utf-8"))
        self.assertEqual(m["status"], "ok")
        import hashlib
        for nome, sha in m["sha256"].items():
            self.assertEqual(hashlib.sha256((saida / nome).read_bytes()).hexdigest(), sha)

    def test_env_divergente_para_antes_de_conectar(self):
        arquivo = self.pasta / "conexao.env"
        arquivo.write_text("DB_HOST=banco.invalid\nDB_PORT=4000\nDB_USER=usuario\nDB_PASSWORD=ficticia\nDB_NAME=outro\n")
        with patch.object(cli, "get_db_connection") as conectar, patch("builtins.print"):
            r = cli.main(["--arquivo", str(self.arquivo), "--banco", "catalogo",
                "--env-file", str(arquivo), "--saida", str(self.pasta / "env_errado")])
        self.assertEqual(r, 1)
        conectar.assert_not_called()

    def test_migrador_env_ausente_para_antes_de_conectar(self):
        with patch.object(migrar_banco, "get_db_connection") as conectar:
            with patch.object(migrar_banco, "emit_report"):
                r = migrar_banco.main(["--banco", "catalogo", "--env-file", str(self.pasta / "ausente")])
        self.assertEqual(r, 1)
        conectar.assert_not_called()

    def test_linha_de_coordenacao_ausente_impede_carga(self):
        self.banco.db.execute("DELETE FROM schema_migrations WHERE versao=?", (osm.VERSAO_LOCK,))
        with self.assertRaises(osm.FalhaOSM) as r:
            self.executar(True)
        self.assertEqual(r.exception.codigo, "registro_de_coordenacao_ausente_ou_divergente")
        self.assertEqual(self.banco.db.execute("SELECT COUNT(*) FROM postos").fetchone()[0], 0)

    def test_alteracao_concorrente_na_oferta_e_recusada(self):
        cursor = Mock(rowcount=0)
        plano = [{"tipo": "oferta", "posto_id": 1, "codigo": "gasolina_comum", "valor": 1, "existe": True}]
        with self.assertRaises(osm.ErroOSM):
            osm.aplicar_metadados(cursor, plano, self.agora)


if __name__ == "__main__":
    unittest.main()
