"""Provas offline de copia e protecoes. Nenhuma conexao de rede e aberta."""
from __future__ import annotations

import copy
import io
import os
import sys
import tempfile
import unittest
import ssl
from contextlib import ExitStack, redirect_stdout
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pymysql
from services.database import DatabaseConfig
from services import database
from services import diagnostico_tidb as diag
from services import transferencia_banco as core
from scripts import transferir_para_tidb as cli
from scripts import usar_destino


def captured():
    data = {
        "postos": [{
            "id": 18,
            "nome": "Posto d'Água\\Centro",
            "latitude": Decimal("-7.11041370"),
        }],
        "usuarios": [{
            "id": 7,
            "senha": "$2b$12$hash_ficticio_preservado",
            "karma": 80,
            "criado_em": datetime(2026, 10, 29, 12, 34, 56),
        }],
        "registos_preco": [{
            "id": 46,
            "posto_id": 18,
            "usuario_id": 7,
            "preco": Decimal("7.00"),
            "data_registro": datetime(2026, 11, 4, 10, 48, 37),
        }],
        "votos_registos": [],
    }

    fields = {
        "postos": ["id", "nome", "latitude"],
        "usuarios": ["id", "senha", "karma", "criado_em"],
        "registos_preco": [
            "id",
            "posto_id",
            "usuario_id",
            "preco",
            "data_registro",
        ],
        "votos_registos": [
            "id",
            "registo_id",
            "usuario_id",
        ],
    }

    result = {
        "gerado_em_utc": "2026-11-07T17:43:07+00:00",
        "tabelas": {},
    }

    for table in core.TABLES:
        columns = fields[table]
        meta = {
            "info": {
                "engine": "InnoDB",
                "collation": "utf8mb4_unicode_ci",
                "proximo_id": 100,
            },
            "columns": [
                {
                    "nome": c,
                    "tipo": "int",
                    "tipo_base": "int",
                    "nulo": "YES",
                    "padrao": None,
                    "extra": "",
                    "collation": None,
                }
                for c in columns
            ],
            "indexes": [],
            "fks": [],
        }

        result["tabelas"][table] = {
            "ddl": (
                "CREATE TABLE "
                + core.q(table)
                + " (id INT PRIMARY KEY)"
            ),
            "meta": meta,
            "columns": columns,
            "rows": data[table],
            "sha256": core.digest(data[table], columns),
            "proximo_id": 100,
        }

    return result


class MemoryConnection:
    def __init__(self, origin=False):
        self.origin = origin
        self.tables = set(core.TABLES) if origin else set()
        self.data = {t: [] for t in core.TABLES}
        self.pending = None
        self.log = []
        self.fail_ddl = self.fail_insert = None
        self.lose_ack = False
        self.closed = False

        self.offline = pymysql.Connection(
            defer_connect=True,
            charset="utf8mb4",
        )
        self.offline.server_status = 0

    def cursor(self):
        return MemoryCursor(self)

    def commit(self):
        if self.pending is not None:
            self.data = self.pending
            self.pending = None

            if self.lose_ack:
                raise OSError("resposta de commit perdida")

    def rollback(self):
        self.pending = None

    def close(self):
        self.closed = True


class MemoryCursor:
    def __init__(self, conn):
        self.conn, self.result = conn, []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def fetchall(self):
        return copy.deepcopy(self.result)

    def mogrify(self, sql, params):
        return self.conn.offline.cursor().mogrify(sql, params)

    def execute(self, sql, params=None):
        n = " ".join(sql.replace("`", "").split())
        self.conn.log.append(n)

        if self.conn.origin:
            raise AssertionError(
                "Nenhuma escrita pode atingir a origem"
            )

        if n.startswith("CREATE TABLE "):
            table = n.split()[2]

            if table == self.conn.fail_ddl:
                raise RuntimeError("DDL parcial simulado")

            self.conn.tables.add(table)

        elif (
            n.startswith("ALTER TABLE ")
            or n.startswith("SET SESSION sql_mode")
        ):
            pass

        elif n == "BEGIN PESSIMISTIC":
            self.conn.pending = copy.deepcopy(self.conn.data)

        elif n.startswith("INSERT INTO "):
            table = n.split()[2]

            if table == self.conn.fail_insert:
                raise RuntimeError("insercao rejeitada")

            fields = sql.split("(", 1)[1].split(")", 1)[0]
            fields = [
                c.strip().strip("`")
                for c in fields.split(",")
            ]

            self.conn.pending[table].append(
                dict(zip(fields, params))
            )

        else:
            raise AssertionError(
                "SQL inesperado no simulador: " + n
            )


class CopyTests(unittest.TestCase):
    def setUp(self):
        self.capture = captured()
        self.source = MemoryConnection(origin=True)
        self.fresh = MemoryConnection(origin=True)
        self.target = MemoryConnection()

        self.origin_cfg = DatabaseConfig(
            "origem.invalid",
            26841,
            "u",
            "p",
            "defaultdb",
        )

        self.dest_cfg = DatabaseConfig(
            "destino.invalid",
            4000,
            "u",
            "p",
            "ensaio",
        )

        self.stack = ExitStack()
        self.addCleanup(self.stack.close)

        self.stack.enter_context(patch.object(
            core,
            "connect",
            side_effect=[
                self.source,
                self.target,
                self.fresh,
            ],
        ))

        self.snapshot = self.stack.enter_context(patch.object(
            core,
            "snapshot",
            return_value=self.capture,
        ))

        self.stack.enter_context(patch.object(
            core,
            "server",
            side_effect=lambda conn: {
                "banco": "defaultdb" if conn.origin else "ensaio",
                "versao": "8.4.11" if conn.origin else "8.5.0-TiDB",
                "fk": 1,
            },
        ))

        self.stack.enter_context(patch.object(
            core,
            "table_names",
            side_effect=lambda conn: [
                {"nome": t, "tipo": "BASE TABLE"}
                for t in conn.tables
            ],
        ))

        self.stack.enter_context(
            patch.object(core, "check_collations")
        )

        self.stack.enter_context(patch.object(
            core,
            "metadata",
            side_effect=lambda conn, table: (
                self.capture["tabelas"][table]["meta"]
            ),
        ))

        self.stack.enter_context(patch.object(
            core,
            "read_data",
            side_effect=lambda conn, table, columns: copy.deepcopy(
                (
                    conn.pending
                    if conn.pending is not None
                    else conn.data
                )[table]
            ),
        ))

        def fake_rows(conn, sql, params=None):
            if "GET_LOCK" in sql:
                return [{"adquirido": 1}]

            if "RELEASE_LOCK" in sql:
                return [{"liberado": 1}]

            if "SHOW CREATE TABLE" in sql:
                return [{
                    "Create Table": (
                        "CREATE TABLE t (id INT PRIMARY KEY)"
                    ),
                }]

            raise AssertionError(sql)

        self.stack.enter_context(
            patch.object(core, "rows", side_effect=fake_rows)
        )

        self.diagnose = self.stack.enter_context(patch.object(
            diag,
            "diagnose",
            return_value={"status": "ok"},
        ))

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_copy(self, **kwargs):
        return core.transfer(
            self.origin_cfg,
            self.dest_cfg,
            backup_folder=self.tmp.name,
            **kwargs,
        )

    def test_preview_has_no_ddl_dml_or_backup(self):
        result = self.run_copy()

        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["gravacoes_tabelas_aplicacao"])
        self.assertEqual(self.target.log, [])
        self.assertEqual(
            list(Path(self.tmp.name).iterdir()),
            [],
        )
        self.assertFalse(
            self.diagnose.call_args.kwargs["write"]
        )

    def test_copy_preserves_ids_password_hash_dates_prices_karma_and_sql_backup(self):
        result = self.run_copy(
            apply=True,
            expected_database="ensaio",
        )

        self.assertEqual(
            result["commit_dados"],
            "confirmado",
        )

        for table, item in self.capture["tabelas"].items():
            self.assertEqual(
                self.target.data[table],
                item["rows"],
            )

        backup = Path(result["backup_arquivo"]).read_text(
            encoding="utf-8"
        )

        self.assertIn("d\\'Água\\\\Centro", backup)
        self.assertIn("$2b$12$hash_ficticio_preservado", backup)
        self.assertIn("2026-10-29 12:34:56", backup)
        self.assertIn("7.00", backup)
        self.assertTrue(backup.rstrip().endswith("COMMIT;"))
        self.assertEqual(self.source.log, [])

    def test_nonempty_destination_blocked_without_backup(self):
        self.target.tables.add("usuarios")

        with self.assertRaises(core.TransferError):
            self.run_copy(
                apply=True,
                expected_database="ensaio",
            )

        self.assertEqual(self.target.log, [])
        self.assertEqual(
            list(Path(self.tmp.name).iterdir()),
            [],
        )

    def test_wrong_schema_name_blocked(self):
        with self.assertRaises(core.TransferError):
            self.run_copy(
                apply=True,
                expected_database="outro",
            )

        self.assertEqual(self.target.log, [])

    def test_insert_failure_rolls_back_all_data_but_keeps_created_structure(self):
        self.target.fail_insert = "registos_preco"
        state = {}

        with self.assertRaises(RuntimeError):
            self.run_copy(
                apply=True,
                expected_database="ensaio",
                state=state,
            )

        self.assertEqual(
            state["commit_dados"],
            "revertido",
        )
        self.assertTrue(all(
            not rows
            for rows in self.target.data.values()
        ))
        self.assertEqual(
            self.target.tables,
            set(core.TABLES),
        )
        self.assertFalse(any(
            s.startswith("DROP")
            for s in self.target.log
        ))

    def test_partial_ddl_is_not_auto_deleted(self):
        self.target.fail_ddl = "usuarios"

        with self.assertRaises(RuntimeError):
            self.run_copy(
                apply=True,
                expected_database="ensaio",
            )

        self.assertEqual(
            self.target.tables,
            {"postos"},
        )
        self.assertFalse(any(
            s.startswith("DROP")
            for s in self.target.log
        ))
        self.assertEqual(
            len(list(Path(self.tmp.name).glob("*.sql"))),
            1,
        )

    def test_source_change_blocks_commit(self):
        changed = copy.deepcopy(self.capture)
        changed["tabelas"]["usuarios"]["sha256"] = "mudou"
        self.snapshot.side_effect = [
            self.capture,
            changed,
        ]
        state = {}

        with self.assertRaises(core.TransferError):
            self.run_copy(
                apply=True,
                expected_database="ensaio",
                state=state,
            )

        self.assertEqual(
            state["commit_dados"],
            "revertido",
        )
        self.assertTrue(all(
            not value
            for value in self.target.data.values()
        ))

    def test_lost_commit_ack_is_reported_as_unknown_not_as_rolled_back(self):
        self.target.lose_ack = True
        state = {}

        with self.assertRaises(OSError):
            self.run_copy(
                apply=True,
                expected_database="ensaio",
                state=state,
            )

        self.assertEqual(
            state["etapa"],
            "confirmar_commit",
        )
        self.assertEqual(
            state["commit_dados"],
            "nao_confirmado",
        )
        self.assertTrue(self.target.data["usuarios"])

    def test_readback_difference_blocks_commit(self):
        with patch.object(
            core,
            "verify_data",
            side_effect=core.TransferError("divergencia"),
        ):
            with self.assertRaises(core.TransferError):
                self.run_copy(
                    apply=True,
                    expected_database="ensaio",
                )

        self.assertTrue(all(
            not value
            for value in self.target.data.values()
        ))


class StructureTests(unittest.TestCase):
    def test_empty_tidb_table_uses_actual_allocator_when_information_schema_returns_zero(self):
        item = captured()["tabelas"]["votos_registos"]
        item["proximo_id"] = 101

        meta = copy.deepcopy(item["meta"])
        meta["info"]["proximo_id"] = 0

        with (
            patch.object(core, "metadata", return_value=meta),
            patch.object(
                core,
                "rows",
                return_value=[
                    {
                        "COLUMN_NAME": "id",
                        "NEXT_GLOBAL_ROW_ID": 101,
                        "ID_TYPE": "_TIDB_ROWID",
                    },
                    {
                        "COLUMN_NAME": "id",
                        "NEXT_GLOBAL_ROW_ID": 1,
                        "ID_TYPE": "AUTO_INCREMENT",
                    },
                ],
            ),
        ):
            self.assertEqual(
                core.next_id(
                    Mock(),
                    "votos_registos",
                    item,
                ),
                101,
            )

    def test_readonly_start_uses_portable_syntax_and_preserves_verified_tls(self):
        from unittest.mock import MagicMock

        connection = MagicMock()
        cursor = (
            connection.cursor.return_value
            .__enter__.return_value
        )
        cursor.fetchone.return_value = {
            "versao": "8.0.11-TiDB-v8.5.0",
        }

        config = DatabaseConfig(
            "destino.invalid",
            4000,
            "u",
            "p",
            "ensaio",
        )

        with patch.object(
            pymysql,
            "connect",
            return_value=connection,
        ) as connect:
            result = database.get_db_connection(
                config=config,
                read_only=True,
                time_zone="+00:00",
            )

        self.assertIs(result, connection)

        queries = [
            call.args[0]
            for call in cursor.execute.call_args_list
        ]
        self.assertIn(
            "SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ",
            queries,
        )
        self.assertEqual(
            queries[-1],
            "START TRANSACTION",
        )
        self.assertEqual(
            connect.call_args.kwargs["ssl"].verify_mode,
            ssl.CERT_REQUIRED,
        )
        self.assertTrue(
            connect.call_args.kwargs["ssl"].check_hostname
        )

    def test_qualified_foreign_keys_are_rewritten_without_touching_literal_defaults(self):
        ddl = (
            "CREATE TABLE `t` (x varchar(100) DEFAULT "
            "'REFERENCES `old`.`usuarios`', "
            "FOREIGN KEY(x) REFERENCES `old`.`usuarios`(id))"
        )

        result = core.unqualify_references(ddl, "old")

        self.assertIn(
            "DEFAULT 'REFERENCES `old`.`usuarios`'",
            result,
        )
        self.assertIn(
            "REFERENCES `usuarios`(id)",
            result,
        )

    def test_external_reference_is_rejected(self):
        with self.assertRaises(core.TransferError):
            core.unqualify_references(
                "CREATE TABLE `t` "
                "(FOREIGN KEY(x) REFERENCES `other`.`usuarios`(id))",
                "old",
            )

    def test_signature_preserves_collation_but_normalizes_mysql_display_width(self):
        item = captured()["tabelas"]["postos"]["meta"]
        alternative = copy.deepcopy(item)
        alternative["info"]["proximo_id"] = 100000
        alternative["columns"][0]["tipo"] = "int(11)"

        self.assertEqual(
            core.signature(item),
            core.signature(alternative),
        )

        alternative["info"]["collation"] = "utf8mb4_bin"

        self.assertNotEqual(
            core.signature(item),
            core.signature(alternative),
        )

    def test_index_metadata_is_compared_independently_of_server_collation_and_wire_type(self):
        item = captured()["tabelas"]["postos"]["meta"]
        item["indexes"] = [
            {
                "nome": "PRIMARY",
                "coluna": "id",
                "ordem": 1,
                "nao_unico": 0,
                "prefixo": None,
            },
            {
                "nome": "mapbox_id",
                "coluna": "mapbox_id",
                "ordem": 1,
                "nao_unico": 0,
                "prefixo": None,
            },
        ]

        other = copy.deepcopy(item)
        other["indexes"].reverse()

        for r in other["indexes"]:
            r["nao_unico"] = str(r["nao_unico"])
            r["ordem"] = str(r["ordem"])

        self.assertEqual(
            core.signature(item),
            core.signature(other),
        )

    def test_previous_migration_tool_accepts_tidb_numeric_metadata(self):
        from test_infra_banco import FakeDB
        from services import migrations

        db = FakeDB()
        # Este cenário reutiliza o simulador de metadados do catálogo 001/002.
        items = migrations.load_migrations(ROOT / "migrations")[:2]

        migrations.run(
            db,
            items,
            apply=True,
            expected_database="ensaio",
        )

        for r in db.indexes:
            r["nao_unico"] = str(r["nao_unico"])
            r["ordem"] = str(r["ordem"])

        result = migrations.run(db, items)

        self.assertTrue(all(
            r["estado"] == "aplicada"
            for r in result["migracoes"]
        ))

    def test_digest_detects_password_date_decimal_and_id_changes(self):
        for field, value in (
            ("id", 8),
            ("senha", "outro"),
            ("karma", 0),
            ("criado_em", datetime(2020, 1, 1)),
        ):
            item = captured()["tabelas"]["usuarios"]
            changed = copy.deepcopy(item["rows"])
            changed[0][field] = value

            self.assertNotEqual(
                item["sha256"],
                core.digest(changed, item["columns"]),
            )

        self.assertNotEqual(
            core.digest([{"v": Decimal("7.00")}], ["v"]),
            core.digest([{"v": Decimal("7.01")}], ["v"]),
        )

    def test_matching_endpoints_rejected_before_connect(self):
        cfg = DatabaseConfig(
            "mesmo.invalid",
            4000,
            "u",
            "p",
            "db",
        )

        with (
            patch.object(core, "connect") as conn,
            self.assertRaises(core.TransferError),
        ):
            core.transfer(cfg, cfg)

        conn.assert_not_called()

    def test_error_report_does_not_print_driver_message(self):
        report = core.failure(
            pymysql.err.OperationalError(
                1045,
                "SENHA_PRIVADA URL_PRIVADA",
            ),
            "conectar",
        )

        self.assertEqual(report["codigo_mysql"], 1045)
        self.assertNotIn("SENHA_PRIVADA", str(report))

    def test_profiles_do_not_inherit_active_aiven_ca(self):
        env = {
            "DATABASE_URL_DESTINO": (
                "mysql://u:p@destino.invalid:4000/db"
            ),
            "DB_SSL_CA": "CA_PRIVADA_AIVEN",
            "DB_SSL_CA_DESTINO": "",
        }

        with (
            patch.dict(os.environ, env, clear=True),
            patch("dotenv.load_dotenv"),
        ):
            self.assertIsNone(
                core.load_profile("DESTINO").ca_file
            )

    def test_cli_apply_needs_schema_before_any_connection(self):
        with (
            patch.object(cli, "transfer") as run,
            redirect_stdout(io.StringIO()),
        ):
            with (
                patch("sys.stderr", io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                cli.main(["--aplicar"])

        run.assert_not_called()


class DiagnosticTests(unittest.TestCase):
    def test_default_diagnostic_never_creates_or_modifies_tables(self):
        with (
            patch.object(
                diag,
                "connect",
                side_effect=[Mock(), Mock()],
            ),
            patch.object(
                diag,
                "server",
                return_value={
                    "versao": "8.5-TiDB",
                    "banco": "ensaio",
                    "fk": 1,
                },
            ),
            patch.object(
                diag,
                "rows",
                return_value=[{"Value": "ON"}],
            ),
            patch.object(
                diag,
                "check_locks",
                return_value={
                    "exclusao_entre_sessoes": True,
                },
            ),
            patch.object(diag, "execute") as write,
        ):
            report = diag.diagnose(object(), write=False)

        write.assert_not_called()
        self.assertFalse(report["testes_de_escrita"])

    def test_failed_probe_drops_only_tables_it_created(self):
        statements = []

        def execute(conn, sql, params=None):
            statements.append(sql)

            if sql.startswith("CREATE TABLE `__ldo_c_"):
                raise pymysql.err.OperationalError(
                    1235,
                    "funcao indisponivel",
                )

        with (
            patch.object(
                diag,
                "connect",
                side_effect=[Mock(), Mock()],
            ),
            patch.object(
                diag,
                "server",
                return_value={
                    "versao": "8.5-TiDB",
                    "banco": "ensaio",
                    "fk": 1,
                },
            ),
            patch.object(
                diag,
                "rows",
                return_value=[{"Value": "ON"}],
            ),
            patch.object(
                diag,
                "check_locks",
                return_value={},
            ),
            patch.object(
                diag,
                "execute",
                side_effect=execute,
            ),
        ):
            with self.assertRaises(
                pymysql.err.OperationalError
            ):
                diag.diagnose(object(), write=True)

        dropped = [
            s
            for s in statements
            if s.startswith("DROP")
        ]

        self.assertEqual(len(dropped), 1)
        self.assertTrue(
            dropped[0].startswith("DROP TABLE `__ldo_p_")
        )

    def test_get_lock_uses_two_sessions_and_disconnect_without_timeout_zero(self):
        a, b, c = Mock(), Mock(), Mock()
        locks = iter([1, 0, 1, 1, 1])

        def response(conn, sql, params=None):
            if "GET_LOCK" in sql:
                self.assertIn(",1)", sql)
                return [{"resultado": next(locks)}]

            return [{"resultado": 1}]

        with (
            patch.object(
                diag,
                "rows",
                side_effect=response,
            ),
            patch.object(
                diag,
                "connect",
                return_value=c,
            ),
        ):
            result = diag.check_locks(object(), a, b)

        self.assertTrue(
            result["exclusao_entre_sessoes"]
        )
        a.rollback.assert_called_once()
        c.close.assert_called_once()

    def test_nonexclusive_get_lock_is_rejected(self):
        def response(conn, sql, params=None):
            return [{"resultado": 1}]

        with (
            patch.object(
                diag,
                "rows",
                side_effect=response,
            ),
            self.assertRaises(core.TransferError),
        ):
            diag.check_locks(
                object(),
                Mock(),
                Mock(),
            )

    def test_integrity_probe_never_accepts_an_arbitrary_error(self):
        for actual in (
            pymysql.err.OperationalError(2003, "conexao"),
            None,
        ):
            with (
                patch.object(
                    diag,
                    "execute",
                    side_effect=actual,
                ),
                self.assertRaises(core.TransferError),
            ):
                diag.expect_error(
                    Mock(),
                    "INSERT",
                    {1452},
                )

        with patch.object(
            diag,
            "execute",
            side_effect=pymysql.err.IntegrityError(
                1452,
                "fk",
            ),
        ):
            diag.expect_error(
                Mock(),
                "INSERT",
                {1452},
            )

    def test_destination_wrapper_restores_active_configuration_even_on_exit(self):
        cfg = DatabaseConfig(
            "dest.invalid",
            4000,
            "novo",
            "segredo",
            "ensaio",
        )

        env = {
            "DATABASE_URL": "URL_ATIVA_AIVEN",
            "DB_SSL_CA": "CA_ATIVA",
        }

        def child(*args, **kwargs):
            self.assertEqual(
                os.environ["DATABASE_URL"],
                "",
            )
            self.assertEqual(
                os.environ["DB_HOST"],
                "dest.invalid",
            )
            self.assertEqual(
                os.environ["DB_SSL_CA"],
                "",
            )

            raise SystemExit(5)

        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(
                usar_destino,
                "load_profile",
                return_value=cfg,
            ),
            patch.object(
                usar_destino,
                "connect",
                return_value=Mock(),
            ),
            patch.object(
                usar_destino,
                "server",
                return_value={"versao": "8.5-TiDB"},
            ),
            patch.object(
                usar_destino.runpy,
                "run_path",
                side_effect=child,
            ),
        ):
            with self.assertRaises(SystemExit):
                usar_destino.main([
                    "migracoes",
                    "--dry-run",
                ])

            self.assertEqual(
                os.environ["DATABASE_URL"],
                "URL_ATIVA_AIVEN",
            )
            self.assertEqual(
                os.environ["DB_SSL_CA"],
                "CA_ATIVA",
            )
            self.assertNotIn(
                "DB_PASSWORD",
                os.environ,
            )


if __name__ == "__main__":
    unittest.main()
