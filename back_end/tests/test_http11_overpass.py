"""Valida o workflow HTTP1.1 com transporte simulado, sem rede ou banco."""
import builtins
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "back_end"))


def carregar_codigo():
    arquivo = ROOT / ".github/workflows/osm_validar_http11.yml"
    linhas = arquivo.read_text(
        encoding="utf-8-sig"
    ).splitlines()

    inicio = next(
        i for i, linha in enumerate(linhas)
        if linha.strip() == "import json"
    )

    fim = next(
        i for i, linha in enumerate(linhas)
        if linha.strip()
        == "raise SystemExit(0 if validas else 2)"
    )

    return compile(
        textwrap.dedent(
            "\n".join(linhas[inicio:fim + 1])
        ),
        str(arquivo),
        "exec",
    )


class HTTP11Tests(unittest.TestCase):
    def executar_fluxo(
        self,
        respostas: list[dict[str, Any]],
    ) -> dict[str, Any]:
        chamadas = []

        with tempfile.TemporaryDirectory() as temporario:
            pasta = Path(temporario)
            destino = pasta / "saida"
            resumo = pasta / "resumo-github.md"

            env = {
                "OSM_HTTP11_SAIDA": str(destino),
                "GITHUB_STEP_SUMMARY": str(resumo),
            }

            def executar(argv, **opcoes):
                indice = len(chamadas)
                chamadas.append(list(argv))

                self.assertLess(
                    indice,
                    len(respostas),
                )

                resposta = respostas[indice]
                http = resposta.get("http", 200)

                Path(
                    argv[argv.index("--output") + 1]
                ).write_text(
                    resposta.get(
                        "corpo",
                        '{"elements":[]}',
                    ),
                    encoding="utf-8",
                )

                headers = [
                    "HTTP/1.1 " + str(http),
                ]

                if resposta.get("retry_after"):
                    headers.append(
                        "Retry-After: "
                        + resposta["retry_after"]
                    )

                Path(
                    argv[
                        argv.index("--dump-header") + 1
                    ]
                ).write_text(
                    "\n".join(headers),
                    encoding="utf-8",
                )

                medidas = {
                    "response_code": http,
                    "ssl_verify_result": 0,
                    "remote_ip": resposta.get(
                        "ip",
                        "192.0.2.1",
                    ),
                    "http_version": resposta.get(
                        "versao",
                        "1.1",
                    ),
                    "time_connect": 0.1,
                    "time_appconnect": 0.2,
                    "time_starttransfer": (
                        0.3 if http else 0
                    ),
                    "time_total": 0.4,
                    "campo_extra": "VALOR-FICTICIO",
                }

                return subprocess.CompletedProcess(
                    argv,
                    resposta.get("curl", 0),
                    stdout=json.dumps(medidas),
                    stderr="VALOR-FICTICIO",
                )

            importar_original = builtins.__import__

            def importar(nome, *args, **kwargs):
                if nome in (
                    "app",
                    "pymysql",
                    "services.database",
                ):
                    raise AssertionError(
                        "O diagnostico nao deve importar banco"
                    )

                return importar_original(
                    nome,
                    *args,
                    **kwargs,
                )

            codigo = carregar_codigo()

            with (
                patch.dict(
                    os.environ,
                    env,
                    clear=True,
                ),
                patch(
                    "subprocess.run",
                    side_effect=executar,
                ),
                patch("time.sleep") as pausa,
                patch(
                    "builtins.__import__",
                    side_effect=importar,
                ),
                patch(
                    "sys.stdout",
                    new_callable=io.StringIO,
                ) as stdout,
            ):
                with self.assertRaises(
                    SystemExit
                ) as encerramento:
                    exec(codigo, {})

            relatorio = json.loads(
                (destino / "relatorio.json").read_text(
                    encoding="utf-8"
                )
            )

            if not isinstance(relatorio, dict):
                raise AssertionError(
                    "O relatorio precisa ser um objeto JSON"
                )

            texto = (destino / "resumo.md").read_text(
                encoding="utf-8"
            )

            self.assertEqual(
                texto,
                resumo.read_text(encoding="utf-8"),
            )

            self.assertFalse(
                relatorio["banco_consultado"]
            )
            self.assertFalse(
                relatorio["gravacao_banco_habilitada"]
            )
            self.assertFalse(
                relatorio["consulta_municipal_validada"]
            )
            self.assertFalse(
                (destino / "fonte.json").exists()
            )

            for comando in chamadas:
                self.assertIn(
                    "--http1.1",
                    comando,
                )
                self.assertIn(
                    "=https",
                    comando,
                )
                self.assertIn(
                    "--data-urlencode",
                    comando,
                )
                self.assertEqual(
                    comando[
                        comando.index("--request") + 1
                    ],
                    "POST",
                )

                for proibido in (
                    "--insecure",
                    "-k",
                    "--location",
                ):
                    self.assertNotIn(
                        proibido,
                        comando,
                    )

            return {
                "codigo": encerramento.exception.code,
                "relatorio": relatorio,
                "chamadas": chamadas,
                "pausas": pausa.call_count,
                "stdout": stdout.getvalue(),
                "resumo": texto,
            }

    def test_http11_valido_nos_dois_perfis(self):
        resultado = self.executar_fluxo([{}, {}])

        self.assertEqual(
            resultado["codigo"],
            0,
        )
        self.assertEqual(
            resultado["relatorio"]["testes_realizados"],
            2,
        )
        self.assertEqual(
            resultado["relatorio"]["status"],
            "http11_respondeu",
        )
        self.assertNotIn(
            "--ipv4",
            resultado["chamadas"][0],
        )
        self.assertIn(
            "--ipv4",
            resultado["chamadas"][1],
        )
        self.assertEqual(
            resultado["pausas"],
            1,
        )

    def test_automatico_falha_e_ipv4_funciona(self):
        resultado = self.executar_fluxo([
            {
                "curl": 28,
                "http": 0,
                "versao": "0",
                "ip": "2001:db8::1",
            },
            {},
        ])

        self.assertEqual(
            resultado["codigo"],
            0,
        )

        registros = resultado["relatorio"]["resultados"]

        self.assertFalse(
            registros[0][
                "resposta_overpass_reconhecida"
            ]
        )
        self.assertTrue(
            registros[1][
                "resposta_overpass_reconhecida"
            ]
        )
        self.assertEqual(
            registros[1]["perfil"],
            "http11_ipv4",
        )

    def test_timeouts_salvam_relatorio_com_codigo_2(self):
        falha = {
            "curl": 28,
            "http": 0,
            "versao": "0",
        }

        resultado = self.executar_fluxo([
            falha,
            falha,
        ])

        self.assertEqual(
            resultado["codigo"],
            2,
        )
        self.assertEqual(
            resultado["relatorio"]["status"],
            "http11_sem_resposta_valida",
        )

    def test_429_interrompe_sem_repetir(self):
        resultado = self.executar_fluxo([
            {"http": 429},
        ])

        self.assertEqual(
            resultado["codigo"],
            2,
        )
        self.assertEqual(
            len(resultado["chamadas"]),
            1,
        )
        self.assertEqual(
            resultado["pausas"],
            0,
        )

    def test_403_interrompe_sem_tentar_outro_perfil(self):
        resultado = self.executar_fluxo([
            {"http": 403},
        ])

        self.assertEqual(
            len(resultado["chamadas"]),
            1,
        )

    def test_retry_after_interrompe(self):
        resultado = self.executar_fluxo([
            {
                "http": 503,
                "retry_after": "120",
            },
        ])

        self.assertEqual(
            len(resultado["chamadas"]),
            1,
        )
        self.assertEqual(
            resultado["codigo"],
            2,
        )

    def test_falha_tls_nao_e_contornada(self):
        for codigo in (35, 60):
            with self.subTest(codigo=codigo):
                resultado = self.executar_fluxo([
                    {
                        "curl": codigo,
                        "http": 0,
                        "versao": "0",
                    },
                ])

                self.assertEqual(
                    len(resultado["chamadas"]),
                    1,
                )
                self.assertEqual(
                    resultado["codigo"],
                    2,
                )

    def test_http200_html_nao_e_sucesso(self):
        html = {
            "corpo": "<html>indisponivel</html>",
        }

        resultado = self.executar_fluxo([
            html,
            html,
        ])

        self.assertEqual(
            resultado["codigo"],
            2,
        )

    def test_http2_reportado_nao_confirma_perfil_http1(self):
        resultado = self.executar_fluxo([
            {"versao": "2"},
            {"versao": "2"},
        ])

        self.assertEqual(
            resultado["codigo"],
            2,
        )
        self.assertTrue(
            all(
                registro["categoria"]
                == "http1_nao_confirmado"
                for registro in resultado[
                    "relatorio"
                ]["resultados"]
            )
        )

    def test_protocolo_ausente_nao_e_confirmado(self):
        resultado = self.executar_fluxo([
            {"versao": None},
            {"versao": None},
        ])

        self.assertEqual(
            resultado["codigo"],
            2,
        )

    def test_relatorio_nao_expoe_stderr_ou_campos_extras(self):
        resultado = self.executar_fluxo([{}, {}])

        for conteudo in (
            resultado["stdout"],
            resultado["resumo"],
            json.dumps(resultado["relatorio"]),
        ):
            self.assertNotIn(
                "VALOR-FICTICIO",
                conteudo,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)