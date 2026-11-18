"""Testa a recuperação HTTP sem acessar a rede."""

import ast
import io
import json
import subprocess
import tempfile
import textwrap
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


URL = "https://overpass-api.de/api/interpreter"
ALTERNATIVO = "https://overpass.private.coffee/api/interpreter"


def carregar_funcao(ambiente):
    raiz = Path(__file__).resolve().parents[2]
    arquivo = raiz / ".github/workflows/osm_fonte.yml"
    linhas = arquivo.read_text(encoding="utf-8-sig").splitlines()

    inicio = next(
        i for i, linha in enumerate(linhas)
        if linha.lstrip().startswith("def consultar_overpass(")
    )
    recuo = len(linhas[inicio]) - len(linhas[inicio].lstrip())

    referencia = next(
        linha for linha in linhas
        if linha.lstrip().startswith("def rejeitar_constante(")
    )
    if recuo != len(referencia) - len(referencia.lstrip()):
        raise ValueError("Alinhe consultar_overpass com rejeitar_constante.")

    fim = inicio + 1
    while fim < len(linhas):
        linha = linhas[fim]
        if linha.strip():
            atual = len(linha) - len(linha.lstrip())
            if atual <= recuo:
                break
        fim += 1

    codigo = textwrap.dedent("\n".join(linhas[inicio:fim]))
    arvore = ast.parse(codigo)
    exec(compile(arvore, str(arquivo), "exec"), ambiente)
    return ambiente["consultar_overpass"]


class CapturaOverpassTests(unittest.TestCase):
    def setUp(self):
        temporario = tempfile.TemporaryDirectory()
        self.addCleanup(temporario.cleanup)
        self.pasta = Path(temporario.name)
        self.corpo = self.pasta / "resposta.tmp"
        self.relatorio = {}
        self.respostas = []
        self.sobras = []

        processo = SimpleNamespace(
            run=Mock(side_effect=self.responder),
            TimeoutExpired=subprocess.TimeoutExpired,
        )
        self.processo = processo

        self.consultar = carregar_funcao({
            "json": json,
            "subprocess": processo,
            "URL": URL,
            "pasta": self.pasta,
            "temporario": self.corpo,
            "relatorio": self.relatorio,
        })

        pausa = patch("time.sleep")
        self.pausa = pausa.start()
        self.addCleanup(pausa.stop)

        relogio = patch("time.monotonic", return_value=0)
        relogio.start()
        self.addCleanup(relogio.stop)

        saida = patch("sys.stdout", new=io.StringIO())
        saida.start()
        self.addCleanup(saida.stop)

    def responder(self, comando, *args, **kwargs):
        self.sobras.append(self.corpo.exists())
        resposta = self.respostas.pop(0)

        if isinstance(resposta, BaseException):
            raise resposta

        http = resposta.get("http", 200)
        cabecalho = Path(
            comando[comando.index("--dump-header") + 1]
        )
        linhas = [f"HTTP/2 {http}"]
        if "retry_after" in resposta:
            linhas.append("Retry-After: " + resposta["retry_after"])

        cabecalho.write_text("\n".join(linhas), encoding="utf-8")
        self.corpo.write_text(
            resposta.get("corpo", "{}"),
            encoding="utf-8",
        )

        return subprocess.CompletedProcess(
            comando,
            resposta.get("codigo", 0),
            stdout=json.dumps({
                "response_code": http,
                "ssl_verify_result": 0,
                "time_total": 0.1,
            }),
            stderr="",
        )

    def executar(self):
        return self.consultar(
            [
                "curl",
                "--proto", "=https",
                "--max-time", "180",
                "--max-filesize", "1024",
                "--retry", "0",
                "--data-urlencode", "data=CONSULTA_ORIGINAL",
                "--output", str(self.corpo),
                "--write-out", "%{json}",
                URL,
            ],
            capture_output=True,
            text=True,
            timeout=200,
            check=False,
        )

    def test_sucesso_sem_repetir(self):
        self.respostas = [{"http": 200}]
        self.assertEqual(self.executar().returncode, 0)
        self.assertEqual(self.processo.run.call_count, 1)
        self.pausa.assert_not_called()

    def test_502_usa_alternativo_preservando_requisicao(self):
        self.respostas = [{"http": 502}, {"http": 200}]
        self.executar()

        chamada = self.processo.run.call_args
        comando = chamada.args[0]
        self.assertIn(ALTERNATIVO, comando)
        self.assertIn("data=CONSULTA_ORIGINAL", comando)
        self.assertEqual(comando[comando.index("--proto") + 1], "=https")
        self.assertEqual(comando[comando.index("--max-time") + 1], "120")
        self.assertEqual(chamada.kwargs["timeout"], 150)
        self.assertEqual(self.relatorio["servidor"], ALTERNATIVO)
        self.pausa.assert_called_once_with(30)

    def test_tres_falhas_tem_limite(self):
        self.respostas = [{"http": 502}] * 3
        resultado = self.executar()

        self.assertEqual(json.loads(resultado.stdout)["response_code"], 502)
        self.assertEqual(self.processo.run.call_count, 3)
        self.assertEqual(
            [chamada.args[0] for chamada in self.pausa.call_args_list],
            [30, 60],
        )

    def test_400_nao_repete(self):
        self.respostas = [{"http": 400}]
        self.executar()
        self.assertEqual(self.processo.run.call_count, 1)
        self.pausa.assert_not_called()

    def test_timeout_curl_usa_alternativo(self):
        self.respostas = [
            {"http": 0, "codigo": 28},
            {"http": 200},
        ]
        self.executar()
        self.assertEqual(self.processo.run.call_count, 2)
        self.assertEqual(self.relatorio["servidor"], ALTERNATIVO)

    def test_timeout_processo_usa_alternativo(self):
        self.respostas = [
            subprocess.TimeoutExpired("curl", 150),
            {"http": 200},
        ]
        self.executar()
        self.assertEqual(self.processo.run.call_count, 2)
        self.pausa.assert_called_once_with(30)

    def test_retry_after_e_limpeza_de_resposta_anterior(self):
        self.respostas = [
            {"http": 503, "retry_after": "45", "corpo": "resposta incompleta"},
            {"http": 200, "corpo": "resposta nova"},
        ]
        self.executar()
        self.pausa.assert_called_once_with(45)
        self.assertEqual(self.sobras, [False, False])
        self.assertEqual(
            self.corpo.read_text(encoding="utf-8"),
            "resposta nova",
        )

    def test_retry_after_longo_interrompe(self):
        self.respostas = [{"http": 503, "retry_after": "120"}]
        self.executar()
        self.assertEqual(self.processo.run.call_count, 1)
        self.pausa.assert_not_called()

    def test_retry_after_em_data_interrompe(self):
        futuro = datetime.now(timezone.utc) + timedelta(seconds=120)
        self.respostas = [{
            "http": 503,
            "retry_after": format_datetime(futuro, usegmt=True),
        }]
        self.executar()
        self.assertEqual(self.processo.run.call_count, 1)
        self.pausa.assert_not_called()

    def test_orcamento_excedido_interrompe(self):
        self.respostas = [{"http": 502}]
        with patch("time.monotonic", side_effect=[0, 590]):
            self.executar()

        self.assertEqual(self.processo.run.call_count, 1)
        self.pausa.assert_not_called()


if __name__ == "__main__":
    unittest.main()