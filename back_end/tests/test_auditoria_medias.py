"""Auditoria com SQLite sintético; nenhuma conexão real é usada."""

import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import auditar_medias_iniciais as cli
from services.auditoria_medias import auditar_medias
from services.migrations import MigrationError
from services.referencias_medias import ErroMedias, carregar_medias, carregar_snapshot
from test_medias_iniciais import Banco, csv_snapshot


class AuditoriaMediasTests(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.arquivo = Path(self.pasta.name) / "snapshot.csv"
        self.arquivo.write_bytes(csv_snapshot())
        self.sha = hashlib.sha256(self.arquivo.read_bytes()).hexdigest()
        self.snapshot = carregar_snapshot(self.arquivo, self.sha)
        self.banco = Banco()
        self.addCleanup(self.banco.conn.close)
        p = patch("services.migrations.run", return_value={
            "versao_servidor": "8.0.11-TiDB-v8.5.3",
            "migracoes": [{"estado": "aplicada"}],
        })
        self.preflight = p.start()
        self.addCleanup(p.stop)

    def carregar(self):
        carregar_medias(self.banco, [], self.snapshot, self.sha, banco="ensaio", aplicar=True)
        self.banco.sql.clear()

    def auditar(self):
        return auditar_medias(self.banco, [], banco="ensaio")

    def test_tabela_vazia_nao_vira_carga(self):
        r = self.auditar()
        self.assertEqual(r["total_referencias"], 0)
        self.assertEqual(r["postos_com_referencias"], 0)
        self.assertEqual(self.banco.quantidade(), 0)

    def test_banco_esperado_vazio_e_recusado_antes_de_consultar(self):
        for banco in ("", " ", None):
            with self.subTest(banco=banco), self.assertRaises(ErroMedias):
                auditar_medias(self.banco, [], banco=banco)
        self.preflight.assert_not_called()
        self.assertEqual(self.banco.sql, [])

    def test_auditoria_preserva_dados_e_so_executa_select(self):
        self.carregar()
        r = self.auditar()
        self.assertEqual(r["total_referencias"], 8)
        self.assertEqual(r["postos_com_referencias"], 2)
        self.assertEqual(r["por_combustivel"], {
            "etanol": 2, "gasolina_aditivada": 2, "gasolina_comum": 2, "gnv": 2,
        })
        self.assertEqual(r["por_snapshot_sha256"], {self.sha: 8})
        self.assertFalse(r["gravacao_executada"])
        self.assertTrue(all(q.lstrip().upper().startswith("SELECT") for q in self.banco.sql))
        self.assertEqual(self.banco.quantidade(), 8)

    def test_registro_posterior_e_oferta_manual_negativa_sao_relato_nao_correcao(self):
        self.carregar()
        self.banco.conn.execute("INSERT INTO registos_preco VALUES(99,1,NULL,'Gasolina Comum',6.27,'2026-11-25 10:00:00')")
        self.banco.conn.execute("INSERT INTO postos_combustiveis VALUES(1,'gnv',0,1)")
        self.banco.conn.commit()
        self.banco.sql.clear()
        r = self.auditar()
        self.assertEqual(r["referencias_com_historico_observado"], 1)
        self.assertEqual(r["referencias_com_oferta_indisponivel"], 1)
        self.assertEqual(self.banco.quantidade(), 8)

    def test_tipo_alterado_e_relatado_sem_apagar_referencias(self):
        self.carregar()
        self.banco.conn.execute("UPDATE postos SET tipo_posto='Eletroposto' WHERE id=1")
        self.banco.conn.commit()
        self.assertEqual(self.auditar()["referencias_em_tipo_incompativel"], 4)
        self.assertEqual(self.banco.quantidade(), 8)

    def test_referencia_divergente_e_recusada_sem_reparacao(self):
        self.carregar()
        self.banco.conn.execute("UPDATE referencias_medias_iniciais SET preco=6.21 WHERE posto_id=1 AND combustivel_codigo='gasolina_comum'")
        self.banco.conn.commit()
        with self.assertRaises(ErroMedias):
            self.auditar()
        self.assertEqual(self.banco.conn.execute("SELECT preco FROM referencias_medias_iniciais WHERE posto_id=1 AND combustivel_codigo='gasolina_comum'").fetchone()[0], 6.21)

    def test_banco_divergente_e_migracao_pendente_interrompem_antes_da_leitura(self):
        self.preflight.side_effect = MigrationError("Banco divergente")
        with self.assertRaises(MigrationError):
            self.auditar()
        self.assertEqual(self.banco.sql, [])
        self.preflight.side_effect = None
        self.preflight.return_value["migracoes"] = [{"estado": "pendente"}]
        with self.assertRaises(ErroMedias):
            self.auditar()
        self.assertEqual(self.banco.sql, [])

    def test_posto_ausente_e_detectado(self):
        self.carregar()
        self.banco.conn.execute("DELETE FROM postos WHERE id=1")
        self.banco.conn.commit()
        with self.assertRaises(ErroMedias):
            self.auditar()
        self.assertEqual(self.banco.quantidade(), 8)

    def test_cli_exige_conexao_somente_leitura_e_salva_relatorio_novo(self):
        conn = Mock()
        destino = Path(self.pasta.name) / "auditoria.json"
        resultado = {"status": "ok", "modo": "somente-leitura"}
        saida = io.StringIO()
        with patch.object(cli, "load_migrations", return_value=[]), patch.object(cli, "get_db_connection", return_value=conn) as conectar, patch.object(cli, "auditar_medias", return_value=resultado), contextlib.redirect_stdout(saida):
            self.assertEqual(cli.main(["--banco", "ensaio", "--relatorio", str(destino)]), 0)
        conectar.assert_called_once_with(read_only=True, time_zone="+00:00")
        self.assertEqual(json.loads(destino.read_text()), resultado)
        self.assertEqual(json.loads(saida.getvalue()), resultado)
        conn.commit.assert_not_called()
        conn.close.assert_called_once()

    def test_cli_nao_sobrescreve_relatorio_nem_conecta(self):
        destino = Path(self.pasta.name) / "existente.json"
        destino.write_text("preservar", encoding="utf-8")
        with patch.object(cli, "get_db_connection") as conectar, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["--banco", "ensaio", "--relatorio", str(destino)]), 1)
        conectar.assert_not_called()
        self.assertEqual(destino.read_text(), "preservar")

    def test_cli_nao_expoe_mensagem_do_driver_e_recusa_aplicar(self):
        saida = io.StringIO()
        with patch.object(cli, "load_migrations", return_value=[]), patch.object(cli, "get_db_connection", side_effect=RuntimeError("MARCADOR_SINTETICO_NAO_EXIBIR")), contextlib.redirect_stdout(saida):
            self.assertEqual(cli.main(["--banco", "ensaio"]), 1)
        self.assertNotIn("MARCADOR_SINTETICO_NAO_EXIBIR", saida.getvalue())
        with patch.object(cli, "get_db_connection") as conectar, contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as erro:
            cli.main(["--banco", "ensaio", "--aplicar"])
        self.assertEqual(erro.exception.code, 2)
        conectar.assert_not_called()


if __name__ == "__main__":
    unittest.main()