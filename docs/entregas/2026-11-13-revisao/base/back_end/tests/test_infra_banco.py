"""Testes simulados: nenhuma dependencia de banco ou de rede."""
from __future__ import annotations

import ast
import contextlib
import copy
import io
import ssl
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services import database, migrations
from services.admin_reports import emit_report
from scripts import migrar_banco, previa_limpeza_precos


class FakeDB:
    """Modelo de metadados e historico; nao pretende validar sintaxe do servidor."""
    def __init__(self):
        self.tables = {t: "InnoDB" for t in migrations.TABLES[:4]}
        self.columns, self.indexes, self.fks = {}, [], []
        self.ledger, self.fuels, self.log = {}, {}, []
        self.fail_on = None
        self.commits = self.rollbacks = 0
        self.closed = False
        self.version = "8.0.36"
        self.check_enabled = "ON"
        for t in ("postos", "usuarios"):
            self.column(t, "id", "int", False)

    def column(self, table, field, kind, nullable, collation=None):
        self.columns[(table, field)] = {"tabela": table, "coluna": field, "tipo": kind,
                                      "nulo": "YES" if nullable else "NO", "collation": collation}

    def index(self, table, name, fields, unique=False):
        for i, field in enumerate(fields, 1):
            self.indexes.append({"tabela": table, "indice": name, "coluna": field,
                                 "ordem": i, "nao_unico": 0 if unique else 1})

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class FakeCursor:
    def __init__(self, db):
        self.db, self.rows = db, []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def fetchall(self):
        return copy.deepcopy(self.rows)

    def fetchone(self):
        return copy.deepcopy(self.rows[0]) if self.rows else None

    def execute(self, sql, params=None):
        n = " ".join(sql.replace("`", "").split())
        d = self.db
        d.log.append((n, params))
        if d.fail_on and d.fail_on in n:
            raise RuntimeError("falha simulada")
        if n.startswith("SELECT DATABASE() AS banco, VERSION()"):
            self.rows = [{"banco": "ensaio", "versao": d.version, "fk": 1}]
        elif n.startswith("SHOW VARIABLES"):
            self.rows = [{"Variable_name": "tidb_enable_check_constraint", "Value": d.check_enabled}]
        elif "FROM information_schema.TABLES " in n:
            self.rows = [{"tabela": t, "engine": e} for t, e in d.tables.items()]
        elif "FROM information_schema.COLUMNS " in n:
            self.rows = list(d.columns.values())
        elif "FROM information_schema.STATISTICS " in n:
            self.rows = sorted(d.indexes, key=lambda r: (r["tabela"], r["indice"], r["ordem"]))
        elif "FROM information_schema.KEY_COLUMN_USAGE " in n:
            self.rows = d.fks
        elif "FROM information_schema.CHECK_CONSTRAINTS " in n:
            self.rows = [{"nome": "ck_pc_" + field,
                          "clausula": f"(({field} is null) or ({field} in (0,1)))"}
                         for field in ("disponivel_osm", "disponivel_manual")]
        elif n.startswith("SHOW CREATE TABLE postos_combustiveis"):
            self.rows = [{"Table": "postos_combustiveis", "Create Table": "CREATE TABLE t (CHECK (x IN (0,1)))"}]
        elif n.startswith("SELECT codigo,nome,unidade"):
            self.rows = [{"codigo": k, "nome": v[0], "unidade": v[1]} for k, v in d.fuels.items()]
        elif n.startswith("SELECT versao,sha256,estado,ultimo_passo"):
            self.rows = list(d.ledger.values())
        elif n.startswith("CREATE TABLE IF NOT EXISTS schema_migrations"):
            d.tables["schema_migrations"] = "InnoDB"
            for field, kind, nullable in (
                ("versao", "varchar(96)", False), ("sha256", "char(64)", False),
                ("estado", "varchar(16)", False), ("iniciada_em", "datetime", False),
                ("aplicada_em", "datetime", True), ("ultimo_passo", "int unsigned", False),
                ("erro_tipo", "varchar(80)", True),
            ):
                d.column("schema_migrations", field, kind, nullable)
            d.index("schema_migrations", "PRIMARY", ("versao",), True)
        elif n.startswith("INSERT INTO schema_migrations "):
            version, checksum = params
            if version in d.ledger:
                raise RuntimeError("registro ja existe")
            d.ledger[version] = {"versao": version, "sha256": checksum,
                                  "estado": "em_execucao", "ultimo_passo": 0}
        elif n.startswith("UPDATE schema_migrations SET ultimo_passo"):
            step, version = params
            d.ledger[version]["ultimo_passo"] = step
        elif n.startswith("UPDATE schema_migrations SET estado='aplicada'"):
            d.ledger[params[0]]["estado"] = "aplicada"
        elif n.startswith("UPDATE schema_migrations SET estado='falhou'"):
            d.ledger[params[1]]["estado"] = "falhou"
        elif n.startswith("CREATE TABLE combustiveis "):
            d.tables["combustiveis"] = "InnoDB"
            for field, kind in (("codigo", "varchar(32)"), ("nome", "varchar(50)"), ("unidade", "varchar(8)")):
                d.column("combustiveis", field, kind, False, "ascii_bin" if field == "codigo" else "utf8mb4_unicode_ci")
            d.index("combustiveis", "PRIMARY", ("codigo",), True)
        elif n.startswith("INSERT INTO combustiveis "):
            values = sql.split("VALUES", 1)[1].strip()
            d.fuels = {code: (name, unit) for code, name, unit in ast.literal_eval("[" + values + "]")}
        elif n.startswith("CREATE TABLE postos_combustiveis "):
            table = "postos_combustiveis"
            d.tables[table] = "InnoDB"
            fields = {"posto_id": ("int", False), "combustivel_codigo": ("varchar(32)", False),
                      "disponivel_osm": ("tinyint", True), "osm_verificado_em": ("datetime", True),
                      "disponivel_manual": ("tinyint", True), "manual_atualizado_em": ("datetime", True),
                      "manual_atualizado_por": ("int", True)}
            for field, (kind, nullable) in fields.items():
                d.column(table, field, kind, nullable, "ascii_bin" if field == "combustivel_codigo" else None)
            d.index(table, "PRIMARY", ("posto_id", "combustivel_codigo"), True)
            d.index(table, "idx_pc_combustivel", ("combustivel_codigo",))
            d.index(table, "idx_pc_responsavel", ("manual_atualizado_por",))
            d.fks = [{"coluna": a, "tabela_referenciada": b, "coluna_referenciada": c,
                      "exclusao": "RESTRICT", "atualizacao": "RESTRICT"}
                     for a, b, c in (("posto_id", "postos", "id"),
                                     ("combustivel_codigo", "combustiveis", "codigo"),
                                     ("manual_atualizado_por", "usuarios", "id"))]
        elif n.startswith("ALTER TABLE postos ADD COLUMN"):
            d.column("postos", "marca", "varchar(120)", True)
            d.column("postos", "marca_origem", "enum('osm','manual')", True)
        elif n.startswith("ALTER TABLE postos ADD KEY"):
            d.index("postos", "idx_postos_marca", ("marca",))
        else:
            raise AssertionError("SQL nao previsto pelo simulador: " + n)


class ConfigurationTests(unittest.TestCase):
    def test_url_precedence_and_encoded_password(self):
        config = database.config_from_mapping({"DATABASE_URL": "mysql://u:p%40ss%3A%23@host:4000/teste",
                                               "DB_HOST": "ignorado"})
        self.assertEqual((config.port, config.password, config.database), (4000, "p@ss:#", "teste"))
        self.assertNotIn(config.password, repr(config))

    def test_legacy_requires_explicit_parameters(self):
        with self.assertRaises(database.DatabaseConfigError):
            database.config_from_mapping({"DB_HOST": "host", "DB_PASSWORD": "senha"})
        config = database.config_from_mapping(dict(DB_HOST="host", DB_PORT="26841", DB_USER="avnadmin",
                                                   DB_PASSWORD="senha", DB_NAME="defaultdb"))
        self.assertEqual(config.port, 26841)

    def test_invalid_url_and_tls_downgrade(self):
        for url in ("postgres://u:p@host/db", "mysql://u:p@host:0/db", "mysql://u:p@host/",
                    "mysql://u:p@host/db?ssl=false", "mysql://u:p@host/db#segredo"):
            with self.subTest(url=url), self.assertRaises(database.DatabaseConfigError) as error:
                database.config_from_mapping({"DATABASE_URL": url})
            self.assertNotIn(url, str(error.exception))

    def test_tls_verification_and_readonly_transaction(self):
        config = database.DatabaseConfig("host", 4000, "u", "senha", "teste")
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        driver = types.ModuleType("pymysql")
        cursors = types.ModuleType("pymysql.cursors")
        cursors.DictCursor = object
        driver.cursors, driver.connect = cursors, Mock(return_value=conn)
        with patch.dict(sys.modules, {"pymysql": driver, "pymysql.cursors": cursors}):
            self.assertIs(database.get_db_connection(read_only=True, time_zone="+00:00", config=config), conn)
        kwargs = driver.connect.call_args.kwargs
        self.assertEqual(kwargs["ssl"].verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(kwargs["ssl"].check_hostname)
        self.assertFalse(kwargs["autocommit"])
        self.assertIn("READ ONLY", cursor.execute.call_args_list[-1].args[0])

    def test_connection_closed_if_session_setup_fails(self):
        config = database.DatabaseConfig("host", 4000, "u", "p", "teste")
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value.execute.side_effect = RuntimeError
        driver = types.ModuleType("pymysql")
        cursors = types.ModuleType("pymysql.cursors")
        cursors.DictCursor = object
        driver.cursors, driver.connect = cursors, Mock(return_value=conn)
        with patch.dict(sys.modules, {"pymysql": driver, "pymysql.cursors": cursors}), self.assertRaises(RuntimeError):
            database.get_db_connection(config=config)
        conn.close.assert_called_once()


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDB()
        # FakeDB modela somente o catálogo 001/002. O schema completo é
        # verificado em MySQL por integracao_participacao.py.
        self.migrations = migrations.load_migrations(ROOT / "migrations")[:2]

    def test_split_sql_respects_quotes_comments_and_semicolons(self):
        self.assertEqual(migrations.split_sql("-- x\nINSERT INTO t VALUES ('a;b'); /* ; */ SELECT `a;b`;"),
                         ["INSERT INTO t VALUES ('a;b')", "SELECT `a;b`"])
        for text in ("SELECT 'ab", "/* incompleto", "/*! DROP TABLE t */"):
            with self.assertRaises(migrations.MigrationError):
                migrations.split_sql(text)

    def test_dry_run_never_creates_control_or_changes_data(self):
        report = migrations.run(self.db, self.migrations)
        self.assertEqual([m["estado"] for m in report["migracoes"]], ["pendente", "pendente"])
        self.assertTrue(all(sql.startswith(("SELECT", "SHOW")) for sql, _ in self.db.log))
        self.assertEqual(self.db.commits, 0)
        self.assertNotIn("schema_migrations", self.db.tables)

    def test_apply_and_repeat_without_rerunning_ddl(self):
        report = migrations.run(self.db, self.migrations, apply=True, expected_database="ensaio")
        self.assertEqual(len(report["aplicadas_nesta_execucao"]), 2)
        self.assertEqual(self.db.fuels, migrations.FUELS)
        self.db.log.clear()
        again = migrations.run(self.db, self.migrations, apply=True, expected_database="ensaio")
        self.assertEqual(again["aplicadas_nesta_execucao"], [])
        self.assertTrue(all(sql.startswith(("SELECT", "SHOW")) for sql, _ in self.db.log))

    def test_wrong_target_blocks_before_any_ddl(self):
        with self.assertRaises(migrations.MigrationError):
            migrations.run(self.db, self.migrations, apply=True, expected_database="outro")
        self.assertFalse(any(sql.startswith("CREATE") for sql, _ in self.db.log))

    def test_partial_ddl_failure_is_recorded_and_never_auto_resumed(self):
        self.db.fail_on = "CREATE TABLE postos_combustiveis"
        with self.assertRaises(migrations.MigrationError):
            migrations.run(self.db, self.migrations, apply=True, expected_database="ensaio")
        first = self.migrations[0]["versao"]
        self.assertEqual(self.db.ledger[first]["estado"], "falhou")
        self.assertIn("combustiveis", self.db.tables)
        self.db.fail_on = None
        self.db.log.clear()
        with self.assertRaises(migrations.MigrationError):
            migrations.run(self.db, self.migrations, apply=True, expected_database="ensaio")
        self.assertTrue(all(sql.startswith(("SELECT", "SHOW")) for sql, _ in self.db.log))

    def test_checksum_change_blocks_applied_migration(self):
        migrations.run(self.db, self.migrations, apply=True, expected_database="ensaio")
        changed = copy.deepcopy(self.migrations)
        changed[0]["sha256"] = "0" * 64
        with self.assertRaises(migrations.MigrationError):
            migrations.run(self.db, changed)

    def test_untracked_existing_structure_is_not_silently_adopted(self):
        self.db.tables["combustiveis"] = "InnoDB"
        with self.assertRaises(migrations.MigrationError):
            migrations.run(self.db, self.migrations)

    def test_running_migration_is_not_overwritten(self):
        with self.db.cursor() as cursor:
            cursor.execute(migrations.LEDGER_DDL)
        item = self.migrations[0]
        self.db.ledger[item["versao"]] = {"versao": item["versao"], "sha256": item["sha256"],
                                           "estado": "em_execucao", "ultimo_passo": 0}
        with self.assertRaises(migrations.MigrationError):
            migrations.run(self.db, self.migrations, apply=True, expected_database="ensaio")
        self.assertEqual(self.db.ledger[item["versao"]]["estado"], "em_execucao")

    def test_competing_claim_does_not_change_another_execution(self):
        with self.db.cursor() as cursor:
            cursor.execute(migrations.LEDGER_DDL)
        item = self.migrations[0]
        self.db.ledger[item["versao"]] = {"versao": item["versao"], "sha256": item["sha256"],
                                           "estado": "em_execucao", "ultimo_passo": 0}
        self.db.log.clear()
        with self.assertRaises(migrations.MigrationError):
            migrations.apply_one(self.db, item)
        self.assertEqual(self.db.ledger[item["versao"]]["estado"], "em_execucao")
        self.assertFalse(any(sql.startswith(("CREATE", "ALTER", "UPDATE")) for sql, _ in self.db.log))

    def test_schema_drift_blocks_even_with_matching_checksum(self):
        migrations.run(self.db, self.migrations, apply=True, expected_database="ensaio")
        self.db.fks[0]["exclusao"] = "CASCADE"
        with self.assertRaises(migrations.MigrationError):
            migrations.run(self.db, self.migrations)

    def test_check_disabled_or_old_mysql_blocked(self):
        self.db.version = "5.7.25-TiDB-v8.5.0"
        self.db.check_enabled = "OFF"
        with self.assertRaises(migrations.MigrationError):
            migrations.run(self.db, self.migrations)
        self.db.version = "5.7.44"
        with self.assertRaises(migrations.MigrationError):
            migrations.run(self.db, self.migrations)

    def test_damaged_sql_is_rejected_before_database_access(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in migrations.FILES:
                (Path(folder) / name).write_text("DROP TABLE usuarios;", encoding="utf-8")
            with self.assertRaises(migrations.MigrationError):
                migrations.load_migrations(Path(folder))


class PreviewTests(unittest.TestCase):
    def fake_connection(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [{"banco": "ensaio"}, {"quantidade": 15}]
        cursor.fetchall.side_effect = [
            [{"id": 10, "posto_id": 1, "usuario_id": 7, "preco": "6.20"}],
            [{"id": 1, "registo_id": 10}, {"id": 2, "registo_id": 999}],
            [{"id": 7, "karma": 5}, {"id": 8, "karma": 0}, {"id": 9, "karma": None}],
        ]
        return conn, cursor

    def test_preview_lists_votes_and_all_users_without_writes(self):
        conn, cursor = self.fake_connection()
        result = previa_limpeza_precos.build_preview(conn)
        self.assertFalse(result["gravacoes_no_banco"])
        self.assertEqual(result["resumo"]["votos_associados"], 1)
        self.assertEqual(result["resumo"]["votos_sem_preco_correspondente"], 1)
        self.assertEqual(len(result["karma_previsto"]), 3)
        self.assertTrue(all(c.args[0].lstrip().startswith("SELECT") for c in cursor.execute.call_args_list))
        conn.commit.assert_not_called()

    def test_preview_rejects_apply_flag_before_opening_connection(self):
        with patch.object(previa_limpeza_precos, "get_db_connection") as connect:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                previa_limpeza_precos.main(["--aplicar"])
        self.assertEqual(error.exception.code, 2)
        connect.assert_not_called()

    def test_cli_requests_readonly_and_omits_connection_secrets(self):
        with patch.object(previa_limpeza_precos, "get_db_connection", side_effect=RuntimeError("senha_exposta")) as connect:
            with patch.object(previa_limpeza_precos, "emit_report") as emit:
                self.assertEqual(previa_limpeza_precos.main([]), 1)
        self.assertTrue(connect.call_args.kwargs["read_only"])
        self.assertNotIn("senha_exposta", str(emit.call_args))

    def test_migration_default_cli_is_readonly(self):
        db = FakeDB()
        with patch.object(migrar_banco, "get_db_connection", return_value=db) as connect:
            with patch.object(migrar_banco, "emit_report"):
                self.assertEqual(migrar_banco.main([]), 0)
        self.assertTrue(connect.call_args.kwargs["read_only"])
        self.assertTrue(db.closed)

    def test_migration_apply_requires_explicit_database(self):
        with patch.object(migrar_banco, "get_db_connection") as connect:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                migrar_banco.main(["--aplicar"])
        self.assertEqual(error.exception.code, 2)
        connect.assert_not_called()

    def test_report_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "relatorio.json"
            with contextlib.redirect_stdout(io.StringIO()):
                emit_report({"versao": 1}, str(path))
            with self.assertRaises(FileExistsError):
                emit_report({"versao": 2}, str(path))
            self.assertIn('"versao": 1', path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
