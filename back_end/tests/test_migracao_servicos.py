"""Integridade da migração nova e normalização estrita dos metadados CHECK."""
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.contrato_migracoes import load_migrations, MigrationError
from services.plano_migracoes import make_plan
from services.validacao_servicos import normalizar_check
from test_infra_banco import FakeDB


class MigracaoServicosTests(unittest.TestCase):
    def test_arquivo_005_e_carregado_sem_reescrever_as_migracoes_anteriores(self):
        migracoes = load_migrations(ROOT / "migrations")

        self.assertEqual(
            migracoes[-1]["versao"],
            "005_solicitacoes_servicos",
        )
        self.assertEqual(len(migracoes[-1]["statements"]), 1)
        self.assertTrue(
            migracoes[-1]["statements"][0].startswith(
                "CREATE TABLE solicitacoes_servicos"
            )
        )
        self.assertFalse(
            any(
                "ALTER TABLE" in s or "INSERT INTO" in s
                for s in migracoes[-1]["statements"]
            )
        )

    def test_check_normaliza_mysql_e_tidb_sem_aceitar_expressao_permissiva(self):
        esperado = "estadoin'pendente','aprovada','rejeitada'"

        for clausula in [
            "(`estado` in ('pendente','aprovada','rejeitada'))",
            "(`estado` in (_utf8mb4\\'pendente\\',_utf8mb4\\'aprovada\\',_utf8mb4\\'rejeitada\\'))",
            "`estado` IN (_ascii'pendente',_ascii'aprovada',_ascii'rejeitada')",
        ]:
            self.assertEqual(normalizar_check(clausula), esperado)

        for invalida in [
            "estado in ('pendente','aprovada','rejeitada') OR TRUE",
            "estado in ('pendente','aprovada')",
            "estado IS NOT NULL",
        ]:
            self.assertNotEqual(normalizar_check(invalida), esperado)

    def test_tabela_005_sem_ledger_nao_e_adotada(self):
        # O simulador fornece base válida;
        # somente 005 é relevante neste caso.
        db = FakeDB()
        db.tables["solicitacoes_servicos"] = "InnoDB"

        with self.assertRaisesRegex(MigrationError, "Estrutura sem registro"):
            make_plan(
                db.cursor(),
                load_migrations(ROOT / "migrations")[-1:],
            )

    def test_migracoes_001_a_004_preservam_os_hashes_ja_publicados(self):
        esperados = {
            "001_catalogo_disponibilidade.sql": "5dac305e16046565a158ec60a250d042ca4c6be90b9ac79bd36b2b83843b9227",
            "002_marcas_postos.sql": "84079120156253a52d07dfa3e9b6b5dc89593d259d2f3acd464ef939169915f7",
            "003_gestao_conta.sql": "22ec2feb47090ae90290b707331163caf51f526817df69bbeaa6fa6215dd70e1",
            "004_atividade_alertas.sql": "1b83ea5eed82149c17fee3e360175b398ebfd15ef57aafea578d0783d56148b4",
        }

        for nome, sha in esperados.items():
            dados = (
                (ROOT / "migrations" / nome)
                .read_text(encoding="utf-8-sig")
                .replace("\r\n", "\n")
                .replace("\r", "\n")
            )
            self.assertEqual(
                hashlib.sha256(dados.encode()).hexdigest(),
                sha,
                nome,
            )


if __name__ == "__main__":
    unittest.main()