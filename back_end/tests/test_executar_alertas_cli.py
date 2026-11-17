"""CLI com dependências simuladas; sem conexão real ou agendamento."""
from contextlib import redirect_stdout, redirect_stderr
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SPEC = importlib.util.spec_from_file_location(
    "cli_executor_alertas",
    ROOT / "scripts" / "executar_alertas.py",
)

cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


def conexao():
    conn = MagicMock()

    conn.cursor.return_value.__enter__.return_value.fetchone.side_effect = [
        {"banco": "dev"},
        {"pendentes": 0, "mais_antigo": None},
    ]

    return conn


class CLITests(unittest.TestCase):
    def test_padrao_diagnostica_sem_processar(self):
        conn = conexao()
        processar = Mock()
        conectar = Mock(return_value=conn)
        saida = io.StringIO()

        with (
            patch.object(
                cli,
                "dependencias",
                return_value=(conectar, processar),
            ),
            redirect_stdout(saida),
        ):
            self.assertEqual(cli.main(["--banco", "dev"]), 0)

        dados = json.loads(saida.getvalue())

        self.assertEqual(dados["modo"], "diagnostico")
        self.assertEqual(dados["pendentes"], 0)
        self.assertTrue(dados["assinatura_processador_compativel"])

        processar.assert_not_called()
        conectar.assert_called_once_with(read_only=True)

    def test_uma_rodada_nao_habilita_ciclo(self):
        saida = io.StringIO()

        with (
            patch.object(
                cli,
                "dependencias",
                return_value=(
                    Mock(return_value=conexao()),
                    Mock(return_value=0),
                ),
            ),
            patch.object(cli, "instalar_sinais", return_value={}),
            patch.object(cli, "executar_ciclo") as ciclo,
            redirect_stdout(saida),
        ):
            codigo = cli.main(["--banco", "dev", "--uma-rodada"])

        self.assertEqual(codigo, 0)
        self.assertEqual(
            json.loads(saida.getvalue())["modo"],
            "uma_rodada",
        )
        ciclo.assert_not_called()

    def test_continuo_exige_opcao_explicita(self):
        with (
            patch.object(
                cli,
                "dependencias",
                return_value=(Mock(), Mock()),
            ),
            patch.object(cli, "instalar_sinais", return_value={}),
            patch.object(cli, "executar_ciclo", return_value=0) as ciclo,
            redirect_stdout(io.StringIO()),
        ):
            codigo = cli.main(["--banco", "dev", "--continuo"])

        self.assertEqual(codigo, 0)
        ciclo.assert_called_once()

    def test_handlers_sinalizam_e_sao_restaurados(self):
        parar = cli.Event()

        with (
            patch.object(
                cli.signal,
                "getsignal",
                return_value=cli.signal.SIG_DFL,
            ),
            patch.object(cli.signal, "signal") as registrar,
        ):
            anteriores = cli.instalar_sinais(parar)
            handlers = list(registrar.call_args_list)

            self.assertFalse(parar.is_set())
            self.assertTrue(handlers)

            handlers[0].args[1](handlers[0].args[0], None)
            self.assertTrue(parar.is_set())

            cli.restaurar_sinais(anteriores)

            self.assertEqual(
                registrar.call_count,
                len(handlers) * 2,
            )

    def test_banco_obrigatorio_e_modos_exclusivos(self):
        for args in (
            [],
            ["--banco", "dev", "--uma-rodada", "--continuo"],
        ):
            with (
                self.subTest(args=args),
                patch.object(cli, "dependencias") as deps,
                redirect_stderr(io.StringIO()),
            ):
                with self.assertRaises(SystemExit) as capturado:
                    cli.main(args)

                self.assertEqual(capturado.exception.code, 2)
                deps.assert_not_called()

    def test_parametros_invalidos_nao_importam_conector(self):
        with (
            patch.object(cli, "dependencias") as deps,
            redirect_stdout(io.StringIO()),
        ):
            codigo = cli.main([
                "--banco", "dev",
                "--intervalo", "0",
            ])

        self.assertEqual(codigo, 2)
        deps.assert_not_called()

    def test_logs_omitem_mensagem_privada(self):
        saida = io.StringIO()

        conectar = Mock(
            side_effect=RuntimeError("senha-nao-imprimir")
        )

        with (
            patch.object(
                cli,
                "dependencias",
                return_value=(conectar, Mock()),
            ),
            redirect_stdout(saida),
        ):
            codigo = cli.main(["--banco", "dev"])

        self.assertEqual(codigo, 2)
        self.assertNotIn("senha-nao-imprimir", saida.getvalue())
        self.assertEqual(
            json.loads(saida.getvalue())["erro_tipo"],
            "RuntimeError",
        )

    def test_processador_antigo_nao_e_fallback(self):
        antigo = Mock(processar_eventos=Mock())
        antigo.processar_pendentes = None

        with patch.object(
            cli.importlib,
            "import_module",
            side_effect=[Mock(), antigo],
        ):
            with self.assertRaises(cli.ContratoFilaInvalido):
                cli.dependencias()

        antigo.processar_eventos.assert_not_called()

    def test_assinatura_aceita_conexao_e_limite(self):
        def incompativel():
            return 0

        with patch.object(
            cli.importlib,
            "import_module",
            side_effect=[
                Mock(),
                Mock(processar_pendentes=incompativel),
            ],
        ):
            with self.assertRaises(cli.ContratoFilaInvalido):
                cli.dependencias()


if __name__ == "__main__":
    unittest.main()