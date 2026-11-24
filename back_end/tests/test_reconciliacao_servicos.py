"""Regressão TiDB e reconciliação simulada; não acessa banco ou rede."""
import copy
from pathlib import Path
import sys
from typing import Any
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import reconciliar_migracao_servicos as cli
from services.contrato_migracoes import MigrationError, load_migrations
from services.validacao_migracoes import _column, _index
from services.validacao_servicos import (
    CHECK_ESPERADO, COLUNAS, INDICES, normalizar_check, validar_estrutura,
)

CLAUSULA = (
    "(`estado` in "
    "(_utf8mb4'pendente',_utf8mb4'aprovada',_utf8mb4'rejeitada'))"
)
DDL = (
    "CREATE TABLE `solicitacoes_servicos` ("
    "CONSTRAINT `ck_ss_estado` CHECK (" + CLAUSULA + ")) ENGINE=InnoDB"
)


class CursorEstrutura:
    def __init__(self):
        self.checks = [{"clausula": CLAUSULA}]
        self.ddl = DDL
        self.rows = []
        self.log = []
        self.fks = [
            {"origem": o, "destino": d, "campo": c, "exclusao": e}
            for o, d, c, e in (
                ("usuario_id", "usuarios", "id", "SET NULL"),
                ("posto_id", "postos", "id", "CASCADE"),
                (
                    "combustivel_codigo",
                    "combustiveis",
                    "codigo",
                    "NO ACTION",
                ),
                ("revisado_por", "usuarios", "id", "SET NULL"),
            )
        ]

    def execute(self, sql, params=None):
        self.log.append(sql)

        if "KEY_COLUMN_USAGE" in sql:
            self.rows = self.fks
        elif "CHECK_CONSTRAINTS" in sql:
            # Reproduz o problema observado no TiDB.
            self.rows = [] if "TABLE_CONSTRAINTS" in sql else self.checks
        elif sql == "SHOW CREATE TABLE solicitacoes_servicos":
            self.rows = [{
                "Table": "solicitacoes_servicos",
                "Create Table": self.ddl,
            }]
        else:
            raise AssertionError("SQL inesperado no teste")

    def fetchall(self):
        return copy.deepcopy(self.rows)

    def fetchone(self):
        return copy.deepcopy(self.rows[0]) if self.rows else None


def estrutura() -> dict[str, Any]:
    tabela = "solicitacoes_servicos"
    return {
        "tables": {tabela: "InnoDB"},
        "columns": {
            (tabela, nome): {
                "tipo": tipo,
                "nulo": "YES" if nulo else "NO",
                "collation": "ascii_bin",
            }
            for nome, (tipo, nulo) in COLUNAS.items()
        },
        "indexes": [
            {
                "tabela": tabela,
                "indice": nome,
                "coluna": campo,
                "ordem": ordem,
                "nao_unico": 0 if unico else 1,
            }
            for nome, campos, unico in INDICES
            for ordem, campo in enumerate(campos, 1)
        ],
    }


class CheckTiDBTests(unittest.TestCase):
    def conferir(self, cursor, schema=None):
        validar_estrutura(
            cursor,
            estrutura() if schema is None else schema,
            _column,
            _index,
        )

    def test_tidb_com_join_vazio_e_check_direto_valido(self):
        cursor = CursorEstrutura()
        self.conferir(cursor)

        self.assertFalse(
            any("TABLE_CONSTRAINTS" in sql for sql in cursor.log)
        )
        self.assertIn(
            "SHOW CREATE TABLE solicitacoes_servicos",
            cursor.log,
        )

    def test_mysql_e_tidb_normalizam_sem_mudar_literais(self):
        for clausula in (
            CLAUSULA,
            "estado IN ('pendente','aprovada','rejeitada')",
            "estado IN (_ascii'pendente',_ascii'aprovada',_ascii'rejeitada')",
            (
                "estado IN "
                "(_utf8mb4\\'pendente\\',"
                "_utf8mb4\\'aprovada\\',"
                "_utf8mb4\\'rejeitada\\')"
            ),
        ):
            with self.subTest(clausula=clausula):
                self.assertEqual(
                    normalizar_check(clausula),
                    CHECK_ESPERADO,
                )

    def test_expressao_permissiva_maiusculas_e_espacos_nao_passam(self):
        for clausula in (
            CLAUSULA + " OR TRUE",
            CLAUSULA.replace("pendente", "PENDENTE"),
            CLAUSULA.replace("pendente", "pen dente"),
            CLAUSULA.replace("pendente", "pen(dente)"),
        ):
            with self.subTest(clausula=clausula):
                cursor = CursorEstrutura()
                cursor.checks = [{"clausula": clausula}]

                with self.assertRaises(MigrationError):
                    self.conferir(cursor)

    def test_check_ausente_ou_duplicado_nao_passa(self):
        for checks in ([], [{"clausula": CLAUSULA}] * 2):
            cursor = CursorEstrutura()
            cursor.checks = checks

            with self.assertRaises(MigrationError):
                self.conferir(cursor)

    def test_check_precisa_pertencer_a_tabela_e_estar_enforced(self):
        for ddl in (
            DDL.replace("ck_ss_estado", "outro_check"),
            DDL.replace(") ENGINE", " NOT ENFORCED) ENGINE"),
            DDL.replace("'rejeitada'", "'qualquer'"),
            "",
        ):
            with self.subTest(ddl=ddl):
                cursor = CursorEstrutura()
                cursor.ddl = ddl

                with self.assertRaises(MigrationError):
                    self.conferir(cursor)

    def test_coluna_indice_collation_e_fk_continuam_obrigatorios(self):
        for defeito in ("coluna", "indice", "collation", "fk"):
            schema, cursor = estrutura(), CursorEstrutura()

            if defeito == "coluna":
                schema["columns"].pop(
                    ("solicitacoes_servicos", "motivo")
                )
            elif defeito == "indice":
                schema["indexes"] = []
            elif defeito == "collation":
                schema["columns"][
                    ("solicitacoes_servicos", "estado")
                ]["collation"] = "ascii_general_ci"
            else:
                cursor.fks.pop()

            with (
                self.subTest(defeito=defeito),
                self.assertRaises(MigrationError),
            ):
                self.conferir(cursor, schema)


class ConexaoSimulada:
    def __init__(self, migracoes):
        self.salvo: list[dict[str, Any]] = [
            {
                "versao": m["versao"],
                "sha256": m["sha256"],
                "estado": (
                    "falhou"
                    if m["versao"] == cli.VERSAO
                    else "aplicada"
                ),
                "ultimo_passo": len(m["statements"]),
                "erro_tipo": "MigrationError",
            }
            for m in migracoes
        ]
        self.rows = copy.deepcopy(self.salvo)
        self.log = []
        self.commits = 0
        self.rollbacks = 0
        self.conflito = False

    def cursor(self):
        return CursorHistorico(self)

    def commit(self):
        self.commits += 1
        self.salvo = copy.deepcopy(self.rows)

    def rollback(self):
        self.rollbacks += 1
        self.rows = copy.deepcopy(self.salvo)


class CursorHistorico:
    def __init__(self, conn):
        self.conn = conn
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.conn.log.append(sql)

        if sql.startswith("SELECT versao,"):
            return

        if not sql.startswith("UPDATE schema_migrations"):
            raise AssertionError("SQL de escrita não permitido")

        alvo = self.conn.rows[-1]
        if (
            not self.conn.conflito
            and params == (alvo["versao"], alvo["sha256"])
            and alvo["estado"] == "falhou"
            and alvo["ultimo_passo"] == 1
            and alvo["erro_tipo"] == "MigrationError"
        ):
            alvo.update(estado="aplicada", erro_tipo=None)
            self.rowcount = 1

    def fetchall(self):
        return copy.deepcopy(self.conn.rows)


class ReconciliacaoTests(unittest.TestCase):
    def setUp(self):
        self.migracoes = load_migrations(ROOT / "migrations")
        self.sha = self.migracoes[-1]["sha256"]
        self.conn = ConexaoSimulada(self.migracoes)

        self.compat = Mock(return_value={"banco": "ensaio"})
        self.validar = Mock()
        self.plano = Mock(
            return_value=[
                {"estado": "aplicada"}
            ] * len(self.migracoes)
        )

        patches = patch.multiple(
            cli,
            compatibility=self.compat,
            inspect_schema=Mock(return_value={}),
            validate_structure=self.validar,
            make_plan=self.plano,
        )
        patches.start()
        self.addCleanup(patches.stop)

    def executar(self, aplicar=False):
        return cli.reconciliar(
            self.conn,
            self.migracoes,
            banco="ensaio",
            sha256=self.sha,
            aplicar=aplicar,
        )

    def test_previa_valida_todas_sem_escrever(self):
        resultado = self.executar()

        self.assertFalse(resultado["historico_atualizado"])
        self.assertEqual(
            self.validar.call_count,
            len(self.migracoes),
        )
        self.assertEqual(self.conn.commits, 0)
        self.assertFalse(
            any(sql.startswith("UPDATE") for sql in self.conn.log)
        )

    def test_aplicacao_so_atualiza_ledger_apos_validacao(self):
        resultado = self.executar(True)

        self.assertTrue(resultado["historico_atualizado"])
        self.assertFalse(resultado["ddl_executado"])
        self.assertEqual(self.conn.commits, 1)
        self.assertEqual(
            self.conn.salvo[-1]["estado"],
            "aplicada",
        )
        self.assertEqual(
            self.validar.call_count,
            len(self.migracoes),
        )
        self.assertTrue(self.plano.called)
        self.assertIn("FOR UPDATE", self.conn.log[0])
        self.assertEqual(len(self.conn.log), 2)

    def test_banco_ou_hash_local_divergente_nao_escreve(self):
        for defeito in ("banco", "hash"):
            with self.subTest(defeito=defeito):
                self.conn = ConexaoSimulada(self.migracoes)
                self.compat.return_value = {"banco": "ensaio"}
                self.sha = self.migracoes[-1]["sha256"]

                if defeito == "banco":
                    self.compat.return_value = {"banco": "outro"}
                else:
                    self.sha = "0" * 64

                with self.assertRaises(MigrationError):
                    self.executar(True)

                self.assertEqual(self.conn.commits, 0)
                self.assertFalse(
                    any(
                        sql.startswith("UPDATE")
                        for sql in self.conn.log
                    )
                )

    def test_estado_passo_tipo_hash_e_historico_invalidos_nao_escrevem(self):
        for campo, valor in (
            ("estado", "em_execucao"),
            ("ultimo_passo", 0),
            ("erro_tipo", "OperationalError"),
            ("sha256", "0" * 64),
            ("ausente", None),
            ("anterior", None),
            ("desconhecida", None),
        ):
            with self.subTest(campo=campo):
                self.conn = ConexaoSimulada(self.migracoes)

                if campo == "ausente":
                    self.conn.rows.pop()
                elif campo == "anterior":
                    self.conn.rows[0]["estado"] = "falhou"
                elif campo == "desconhecida":
                    self.conn.rows.append({
                        "versao": "999_desconhecida"
                    })
                else:
                    self.conn.rows[-1][campo] = valor

                with self.assertRaises(MigrationError):
                    self.executar(True)

                self.assertEqual(self.conn.commits, 0)
                self.assertFalse(
                    any(
                        sql.startswith("UPDATE")
                        for sql in self.conn.log
                    )
                )

    def test_estrutura_invalida_nao_atualiza_historico(self):
        self.validar.side_effect = MigrationError("CHECK inválido")

        with self.assertRaises(MigrationError):
            self.executar(True)

        self.assertFalse(
            any(sql.startswith("UPDATE") for sql in self.conn.log)
        )

    def test_conflito_ou_falha_final_faz_rollback(self):
        for conflito in (True, False):
            with self.subTest(conflito=conflito):
                self.conn = ConexaoSimulada(self.migracoes)
                self.conn.conflito = conflito
                self.plano.side_effect = MigrationError(
                    "conferência falhou"
                )

                with self.assertRaises(MigrationError):
                    self.executar(True)

                self.assertEqual(self.conn.commits, 0)
                self.assertEqual(
                    self.conn.rows[-1]["estado"],
                    "falhou",
                )

    def test_repeticao_de_aplicada_valida_sem_nova_escrita(self):
        self.conn.salvo[-1].update(
            estado="aplicada",
            erro_tipo=None,
        )
        self.conn.rows = copy.deepcopy(self.conn.salvo)

        resultado = self.executar(True)

        self.assertFalse(resultado["historico_atualizado"])
        self.assertEqual(self.conn.commits, 0)
        self.assertTrue(self.plano.called)


if __name__ == "__main__":
    unittest.main()