"""Testa isolamento de credenciais e o acionamento somente em leitura."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import prever_osm_github as cli


class PreviaGithubTests(unittest.TestCase):
    def setUp(self):
        temporaria = tempfile.TemporaryDirectory()
        self.addCleanup(temporaria.cleanup)
        self.pasta = Path(temporaria.name)
        self.fonte = self.pasta / "fonte.json"
        self.fonte.write_bytes(b'{"elements":[]}')
        self.sha = hashlib.sha256(self.fonte.read_bytes()).hexdigest()
        self.env = {
            "DB_HOST": "exemplo.invalid", "DB_PORT": "4000",
            "DB_USER": "conta.leitura", "DB_PASSWORD": "nao-publicar",
            "DB_NAME": "litro_de_ouro",
        }
        self.args = [
            "--arquivo", str(self.fonte), "--sha256", self.sha,
            "--banco", "litro_de_ouro", "--saida", str(self.pasta / "resultado"),
        ]

    def executar(self, processo=None):
        saida = io.StringIO()
        with patch.object(cli.subprocess, "run", processo or Mock(return_value=Mock(returncode=0))) as run:
            with contextlib.redirect_stdout(saida):
                retorno = cli.main(self.args, env=self.env)
        return retorno, saida.getvalue(), run

    def test_invoca_so_dry_run_e_remove_credenciais(self):
        arquivos = []
        def rodar(comando, **kwargs):
            self.assertIn("--dry-run", comando)
            self.assertNotIn("--aplicar", comando)
            self.assertNotIn(self.env["DB_PASSWORD"], comando)
            config = Path(comando[comando.index("--env-file") + 1])
            self.assertEqual(dotenv_values(config, interpolate=False), self.env)
            arquivos.append(config)
            self.assertEqual(kwargs, {"check": False, "timeout": 300})
            return Mock(returncode=0)
        retorno, _, _ = self.executar(Mock(side_effect=rodar))
        self.assertEqual(retorno, 0)
        self.assertFalse(arquivos[0].parent.exists())

    def test_nao_herda_database_url_nem_ca_local(self):
        self.env.update(DATABASE_URL="mysql://privado", DB_SSL_CA="C:/ca-local.pem")
        def rodar(comando, **_kwargs):
            config = Path(comando[comando.index("--env-file") + 1])
            dados = dotenv_values(config, interpolate=False)
            self.assertNotIn("DATABASE_URL", dados)
            self.assertNotIn("DB_SSL_CA", dados)
            return Mock(returncode=0)
        self.assertEqual(self.executar(Mock(side_effect=rodar))[0], 0)

    def test_preserva_senha_com_caracteres_especiais(self):
        self.env["DB_PASSWORD"] = "abc'\\\"${nao_interpolar}\nsegunda-linha"
        def rodar(comando, **_kwargs):
            config = comando[comando.index("--env-file") + 1]
            self.assertEqual(dotenv_values(config, interpolate=False)["DB_PASSWORD"], self.env["DB_PASSWORD"])
            return Mock(returncode=0)
        self.assertEqual(self.executar(Mock(side_effect=rodar))[0], 0)

    def test_ca_opcional_e_removida_com_env(self):
        self.env["OSM_DB_CA_PEM"] = "-----BEGIN CERTIFICATE-----\nexemplo\n-----END CERTIFICATE-----\n"
        certificados = []
        def rodar(comando, **_kwargs):
            dados = dotenv_values(comando[comando.index("--env-file") + 1], interpolate=False)
            ca = Path(dados["DB_SSL_CA"])
            self.assertEqual(ca.read_text(), self.env["OSM_DB_CA_PEM"])
            certificados.append(ca)
            return Mock(returncode=0)
        self.assertEqual(self.executar(Mock(side_effect=rodar))[0], 0)
        self.assertFalse(certificados[0].exists())

    def test_hash_divergente_impede_subprocesso(self):
        self.fonte.write_bytes(b"outra fonte")
        retorno, saida, run = self.executar()
        self.assertEqual(retorno, 1)
        self.assertEqual(json.loads(saida)["erro_codigo"], "sha256_da_fonte_divergente")
        run.assert_not_called()

    def test_hash_invalido_impede_subprocesso(self):
        self.args[self.args.index("--sha256") + 1] = "invalido"
        retorno, _, run = self.executar()
        self.assertEqual(retorno, 1)
        run.assert_not_called()

    def test_fonte_vazia_impede_subprocesso(self):
        self.fonte.write_bytes(b"")
        retorno, _, run = self.executar()
        self.assertEqual(retorno, 1)
        run.assert_not_called()

    def test_banco_diferente_impede_subprocesso(self):
        self.env["DB_NAME"] = "outro_banco"
        retorno, _, run = self.executar()
        self.assertEqual(retorno, 1)
        run.assert_not_called()

    def test_credencial_ausente_impede_subprocesso(self):
        del self.env["DB_HOST"]
        retorno, _, run = self.executar()
        self.assertEqual(retorno, 1)
        run.assert_not_called()

    def test_propaga_falha_do_sincronizador(self):
        retorno, _, _ = self.executar(Mock(return_value=Mock(returncode=2)))
        self.assertEqual(retorno, 2)

    def test_timeout_nao_repete_execucao_nem_expoe_mensagem(self):
        processo = Mock(side_effect=subprocess.TimeoutExpired("detalhe-privado", 300))
        retorno, saida, run = self.executar(processo)
        self.assertEqual(retorno, 1)
        self.assertEqual(run.call_count, 1)
        self.assertNotIn("detalhe-privado", saida)
        self.assertNotIn(self.env["DB_PASSWORD"], saida)


if __name__ == "__main__":
    unittest.main()

