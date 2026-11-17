"""Guardas da preparação inicial, com DDL e servidor simulados."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import preparar_banco_novo as cli


class Banco:
    def __init__(self, nome="novo", tabelas=(), falhar_em=None, versao="8.4.13"):
        self.nome = nome
        self.tabelas = set(tabelas)
        self.falhar_em = falhar_em
        self.versao = versao
        self.sql = []
        self.linhas = []
        self.commits = 0
        self.reverteu = False
        self.fechou = False

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql):
        consulta = " ".join(sql.split())
        self.sql.append(consulta)
        if consulta == "SELECT DATABASE() AS banco":
            self.linhas = [{"banco": self.nome}]
        elif "VERSION() AS versao" in consulta:
            self.linhas = [{"banco": self.nome, "versao": self.versao, "fk": 1}]
        elif consulta.startswith("SHOW VARIABLES"):
            self.linhas = [{"Variable_name": "tidb_enable_check_constraint", "Value": "ON"}]
        elif "information_schema.TABLES" in consulta:
            self.linhas = [{"nome": t} for t in sorted(self.tabelas)]
        elif consulta.startswith("CREATE TABLE"):
            tabela = consulta.split()[2].strip("`")
            if tabela == self.falhar_em:
                raise OSError("detalhe-privado")
            self.tabelas.add(tabela)
        elif consulta.startswith("SELECT COUNT(*)"):
            self.linhas = [{"quantidade": 0}]
        else:
            raise AssertionError("SQL inesperado")

    def fetchone(self):
        return self.linhas[0]

    def fetchall(self):
        return self.linhas

    def commit(self):
        self.commits += 1

    def rollback(self):
        # DDL MySQL confirmado não desaparece com rollback.
        self.reverteu = True

    def close(self):
        self.fechou = True


class PreparoTests(unittest.TestCase):
    def setUp(self):
        self.comandos, self.sha = cli.carregar_base(cli.ROOT / "docker/schema_base.sql")

    def preparar(self, banco, aplicar=False, sha=None):
        return cli.preparar(banco, self.comandos, self.sha, "novo", aplicar, sha)

    def test_previa_nao_cria_tabelas_nem_commit(self):
        banco = Banco()
        r = self.preparar(banco)
        self.assertEqual(r["status"], "ok")
        self.assertFalse(banco.tabelas)
        self.assertEqual(banco.commits, 0)
        self.assertEqual(r["sha256_base"], self.sha)

    def test_aplicar_cria_somente_quatro_tabelas_vazias(self):
        banco = Banco()
        r = self.preparar(banco, True, self.sha)
        self.assertEqual(banco.tabelas, set(cli.TABELAS_BASE))
        self.assertEqual(banco.commits, 4)
        self.assertTrue(r["base_vazia_criada"])
        self.assertFalse(r["dados_ficticios_incluidos"])
        self.assertFalse(r["migracoes_aplicadas"])
        self.assertFalse(any(s.startswith(("INSERT", "UPDATE", "DELETE")) for s in banco.sql))

    def test_banco_divergente_para_antes_de_ddl(self):
        banco = Banco(nome="outro")
        with self.assertRaises(cli.ErroPreparo):
            self.preparar(banco, True, self.sha)
        self.assertEqual(banco.sql, ["SELECT DATABASE() AS banco"])

    def test_qualquer_tabela_ou_view_bloqueia_aplicacao(self):
        for tabelas in (("usuarios",), ("view_externa",), cli.TABELAS_BASE):
            banco = Banco(tabelas=tabelas)
            with self.subTest(tabelas=tabelas), self.assertRaises(cli.ErroPreparo):
                self.preparar(banco, True, self.sha)
            self.assertEqual(banco.commits, 0)

    def test_hash_incorreto_para_antes_de_consultar_banco(self):
        banco = Banco()
        with self.assertRaises(cli.ErroPreparo):
            self.preparar(banco, True, "0" * 64)
        self.assertFalse(banco.sql)

    def test_repeticao_recusa_base_ja_criada(self):
        banco = Banco()
        self.preparar(banco, True, self.sha)
        with self.assertRaises(cli.ErroPreparo):
            self.preparar(banco, True, self.sha)
        self.assertEqual(banco.commits, 4)

    def test_falha_ddl_preserva_indicacao_de_base_parcial(self):
        banco = Banco(falhar_em="registos_preco")
        with self.assertRaises(OSError):
            self.preparar(banco, True, self.sha)
        banco.rollback()
        self.assertEqual(banco.tabelas, {"postos", "usuarios"})

    def test_compatibilidade_usa_caminho_tidb_existente(self):
        banco = Banco(versao="8.0.11-TiDB-v8.5.0")
        r = self.preparar(banco)
        self.assertEqual(r["status"], "ok")
        self.assertTrue(any(s.startswith("SHOW VARIABLES") for s in banco.sql))

    def test_sql_com_seed_e_recusado(self):
        with tempfile.TemporaryDirectory() as pasta:
            p = Path(pasta) / "base.sql"
            p.write_text(";".join(self.comandos) + ";INSERT INTO usuarios VALUES (1);", encoding="utf-8")
            with self.assertRaises(cli.ErroPreparo):
                cli.carregar_base(p)

    def test_hash_igual_com_lf_crlf_e_bom(self):
        texto = (cli.ROOT / "docker/schema_base.sql").read_text(encoding="utf-8-sig")
        with tempfile.TemporaryDirectory() as pasta:
            p = Path(pasta) / "base.sql"
            p.write_bytes(b"\xef\xbb\xbf" + texto.replace("\n", "\r\n").encode("utf-8"))
            comandos, sha = cli.carregar_base(p)
            self.assertEqual(comandos, self.comandos)
            self.assertEqual(sha, self.sha)

    def test_bancos_de_sistema_e_nome_invalido_sao_recusados(self):
        for nome in ("mysql", "information_schema", "sys", "performance_schema", "", " novo", "x\n"):
            with self.subTest(nome=nome), self.assertRaises(cli.argparse.ArgumentTypeError):
                cli.nome_banco(nome)

    def test_main_fecha_conexao_e_nao_divulga_erro_do_driver(self):
        banco = Banco(falhar_em="registos_preco")
        saida = io.StringIO()
        with patch.object(cli, "get_db_connection", return_value=banco):
            with contextlib.redirect_stdout(saida):
                codigo = cli.main(["--banco", "novo", "--aplicar", "--sha256-base", self.sha])
        r = json.loads(saida.getvalue())
        self.assertEqual(codigo, 1)
        self.assertTrue(r["ddl_pode_ter_sido_aplicado"])
        self.assertTrue(banco.reverteu)
        self.assertTrue(banco.fechou)
        self.assertNotIn("detalhe-privado", saida.getvalue())

    def test_main_previa_pede_conexao_de_leitura(self):
        banco = Banco()
        with patch.object(cli, "get_db_connection", return_value=banco) as conectar:
            with contextlib.redirect_stdout(io.StringIO()):
                codigo = cli.main(["--banco", "novo"])
        self.assertEqual(codigo, 0)
        conectar.assert_called_once_with(read_only=True, time_zone="+00:00")

    def test_recusa_banco_existente_sem_indicar_ddl_iniciado(self):
        banco = Banco(tabelas=("usuarios",))
        saida = io.StringIO()
        with patch.object(cli, "get_db_connection", return_value=banco):
            with contextlib.redirect_stdout(saida):
                codigo = cli.main(["--banco", "novo", "--aplicar", "--sha256-base", self.sha])
        self.assertEqual(codigo, 1)
        self.assertFalse(json.loads(saida.getvalue())["ddl_pode_ter_sido_aplicado"])
        self.assertTrue(banco.fechou)

    def test_relatorio_existente_bloqueia_antes_de_conectar(self):
        with tempfile.TemporaryDirectory() as pasta:
            p = Path(pasta) / "previa.json"
            p.write_text("preservar", encoding="utf-8")
            with patch.object(cli, "get_db_connection") as conectar:
                with contextlib.redirect_stdout(io.StringIO()):
                    codigo = cli.main(["--banco", "novo", "--relatorio", str(p)])
            self.assertNotEqual(codigo, 0)
            conectar.assert_not_called()
            self.assertEqual(p.read_text(), "preservar")

    def test_configuracao_separada_e_passada_ao_conector(self):
        with tempfile.TemporaryDirectory() as pasta:
            p = Path(pasta) / "banco.env"
            p.write_text(
                'DB_HOST=banco.invalid\nDB_PORT=4000\nDB_USER=usuario\n'
                'DB_PASSWORD=senha-ficticia\nDB_NAME=novo\n', encoding="utf-8",
            )
            with patch.object(cli, "get_db_connection", return_value=Banco()) as conectar:
                with contextlib.redirect_stdout(io.StringIO()):
                    codigo = cli.main(["--banco", "novo", "--env-file", str(p)])
            self.assertEqual(codigo, 0)
            config = conectar.call_args.kwargs["config"]
            self.assertEqual(config.host, "banco.invalid")
            self.assertEqual(config.port, 4000)
            self.assertEqual(config.database, "novo")

    def test_arquivo_de_configuracao_ausente_nao_conecta(self):
        with tempfile.TemporaryDirectory() as pasta:
            p = Path(pasta) / "ausente.env"
            with patch.object(cli, "get_db_connection") as conectar:
                with contextlib.redirect_stdout(io.StringIO()):
                    codigo = cli.main(["--banco", "novo", "--env-file", str(p)])
            self.assertEqual(codigo, 1)
            conectar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
