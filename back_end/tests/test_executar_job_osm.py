"""Testes do executor sem rede ou banco reais."""
from argparse import Namespace
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import executar_job_osm as job


def ambiente_banco():
    return {
        "DB_HOST": "banco.exemplo.invalid",
        "DB_PORT": "4000",
        "DB_USER": "consulta_osm",
        "DB_PASSWORD": "senha-ficticia:$' com espaco",
        "DB_NAME": "catalogo_teste",
    }


class JobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.pasta = Path(self.temp.name)

    def executar(
        self,
        argumentos,
        ambiente,
        retorno=0,
        falha=None,
    ):
        saida = io.StringIO()

        with patch.dict(os.environ, ambiente, clear=True):
            with patch.object(job.subprocess, "run") as rodar:
                rodar.return_value = Namespace(returncode=retorno)
                rodar.side_effect = falha

                with contextlib.redirect_stdout(saida):
                    codigo = job.main(argumentos)

        return codigo, json.loads(saida.getvalue()), rodar

    def test_somente_fonte_isola_credenciais(self):
        origem = {
            **ambiente_banco(),
            "DATABASE_URL": "mysql://detalhe-privado",
            "OSM_DB_CA_PEM": "detalhe-privado",
        }
        antes = dict(origem)

        with patch.object(job, "tls_context") as tls:
            filho = job.preparar_ambiente(
                origem,
                None,
                self.pasta,
            )

        self.assertEqual(origem, antes)
        tls.assert_not_called()

        for campo in (*job.CAMPOS_BANCO, "DATABASE_URL"):
            self.assertEqual(filho[campo], "")

        self.assertNotIn("OSM_DB_CA_PEM", filho)
        self.assertEqual(filho["OSM_SYNC_APPLY"], "false")

    def test_banco_preserva_senha_e_usa_tls_do_sistema(self):
        origem = ambiente_banco()

        with patch.object(job, "tls_context") as tls:
            filho = job.preparar_ambiente(
                origem,
                "catalogo_teste",
                self.pasta,
            )

        self.assertEqual(
            filho["DB_PASSWORD"],
            origem["DB_PASSWORD"],
        )
        self.assertEqual(filho["DB_SSL_CA"], "")

        config = tls.call_args.args[0]
        self.assertEqual(config.database, "catalogo_teste")
        self.assertEqual(config.port, 4000)
        self.assertIsNone(config.ca_file)

    def test_banco_divergente_bloqueia_antes_do_tls(self):
        with patch.object(job, "tls_context") as tls:
            with self.assertRaises(job.ErroJob):
                job.preparar_ambiente(
                    ambiente_banco(),
                    "outro",
                    self.pasta,
                )

        tls.assert_not_called()

    def test_configuracao_incompleta_e_url_sao_recusadas(self):
        mudancas = (
            {"DB_PORT": ""},
            {"DATABASE_URL": "mysql://privado"},
        )

        for mudanca in mudancas:
            with self.subTest(mudanca=mudanca):
                with self.assertRaises(job.ErroJob):
                    job.preparar_ambiente(
                        {**ambiente_banco(), **mudanca},
                        "catalogo_teste",
                        self.pasta,
                    )

    def test_ca_customizada_exclusiva(self):
        origem = {
            **ambiente_banco(),
            "OSM_DB_CA_PEM": "PEM-ficticio",
        }

        with patch.object(job, "tls_context") as tls:
            filho = job.preparar_ambiente(
                origem,
                "catalogo_teste",
                self.pasta,
            )

            caminho = Path(filho["DB_SSL_CA"])

            self.assertEqual(
                caminho.read_text(encoding="utf-8"),
                "PEM-ficticio\n",
            )
            self.assertEqual(
                tls.call_args.args[0].ca_file,
                str(caminho),
            )
            self.assertNotIn("OSM_DB_CA_PEM", filho)

            if os.name == "posix":
                self.assertEqual(
                    caminho.stat().st_mode & 0o777,
                    0o600,
                )

            with self.assertRaises(FileExistsError):
                job.preparar_ambiente(
                    origem,
                    "catalogo_teste",
                    self.pasta,
                )

    def test_ca_privada_ou_grande_e_recusada(self):
        certificados = (
            "-----BEGIN PRIVATE KEY-----",
            "x" * (job.MAX_CA_BYTES + 1),
        )

        for pem in certificados:
            with self.subTest(tamanho=len(pem)):
                with self.assertRaises(job.ErroJob):
                    job.preparar_ambiente(
                        {
                            **ambiente_banco(),
                            "OSM_DB_CA_PEM": pem,
                        },
                        "catalogo_teste",
                        self.pasta,
                    )

    def test_ca_invalida_e_recusada(self):
        origem = {
            **ambiente_banco(),
            "OSM_DB_CA_PEM": "isto-nao-e-um-certificado",
        }

        with self.assertRaises(job.ErroJob):
            job.preparar_ambiente(
                origem,
                "catalogo_teste",
                self.pasta,
            )

    def test_comando_preserva_caminhos_e_limites(self):
        args = Namespace(
            arquivo="pasta com espaco/fonte.json",
            banco=None,
            saida="nova pasta",
        )

        comando = job.montar_comando(args)

        self.assertIn(args.arquivo, comando)
        self.assertIn(args.saida, comando)
        self.assertIn("--somente-fonte", comando)
        self.assertNotIn("--aplicar", comando)
        self.assertNotIn("--banco", comando)
        self.assertEqual(
            comando[-4:],
            ["--tentativas", "2", "--max-espera", "60"],
        )

    def test_sucesso_sem_shell_e_com_tempo_limite(self):
        codigo, resumo, rodar = self.executar(
            ["--saida", "nova"],
            {},
        )

        self.assertEqual(codigo, 0)
        self.assertEqual(
            resumo["status"],
            "executor_concluido",
        )
        self.assertFalse(resumo["gravacao_habilitada"])
        self.assertIn("--joao-pessoa", rodar.call_args.args[0])
        self.assertFalse(rodar.call_args.kwargs["shell"])
        self.assertEqual(
            rodar.call_args.kwargs["timeout"],
            300,
        )

    def test_falha_da_previa_nao_vira_sucesso(self):
        codigo, resumo, _ = self.executar(
            ["--saida", "nova"],
            {},
            retorno=1,
        )

        self.assertEqual(codigo, 1)
        self.assertEqual(resumo["status"], "falha_previa")

    def test_timeout_nao_expoe_comando(self):
        falha = subprocess.TimeoutExpired(
            ["detalhe-privado"],
            300,
        )

        codigo, resumo, _ = self.executar(
            ["--saida", "nova"],
            {},
            falha=falha,
        )

        self.assertEqual(codigo, 1)
        self.assertEqual(resumo["status"], "tempo_limite")
        self.assertNotIn(
            "detalhe-privado",
            json.dumps(resumo),
        )

    def test_configuracao_invalida_nao_inicia_subprocesso(self):
        codigo, resumo, rodar = self.executar(
            ["--saida", "nova", "--banco", "esperado"],
            {},
        )

        self.assertEqual(codigo, 2)
        self.assertEqual(
            resumo["status"],
            "configuracao_invalida",
        )
        rodar.assert_not_called()

    def test_certificado_e_removido_apos_erro(self):
        caminhos = []

        def rodar(*_args, **kwargs):
            caminho = Path(kwargs["env"]["DB_SSL_CA"])
            self.assertTrue(caminho.exists())
            caminhos.append(caminho)
            raise RuntimeError("detalhe-privado")

        origem = {
            **ambiente_banco(),
            "OSM_DB_CA_PEM": "PEM-ficticio",
        }
        saida = io.StringIO()

        with patch.dict(os.environ, origem, clear=True):
            with patch.object(job, "tls_context"):
                with patch.object(
                    job.subprocess,
                    "run",
                    side_effect=rodar,
                ):
                    with contextlib.redirect_stdout(saida):
                        codigo = job.main([
                            "--saida",
                            "nova",
                            "--banco",
                            "catalogo_teste",
                        ])

        self.assertEqual(codigo, 2)
        self.assertFalse(caminhos[0].exists())
        self.assertNotIn("detalhe-privado", saida.getvalue())


if __name__ == "__main__":
    unittest.main()