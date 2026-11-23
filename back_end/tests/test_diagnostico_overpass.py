"""Sondas simuladas e configuração restrita; sem rede ou banco."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.fontes_overpass import (
    ALTERNATIVO,
    PERMITIDOS,
    PRINCIPAL,
    TERCEIRO,
    ConfiguracaoOverpassInvalida,
    plano_captura,
    servidores_configurados,
)
from services.diagnostico_rede_overpass import (
    CONSULTA,
    comando_sonda,
    diagnosticar_rede,
    sondar,
    resumo_markdown,
)


def executor_falso(
    *,
    codigo=0,
    http=200,
    ip="193.219.97.30",
    corpo=None,
    retry_after=None,
    stdout=None,
    stderr="",
    chamadas=None,
):
    def executar(argv, **kwargs):
        if chamadas is not None:
            chamadas.append((argv, kwargs))

        arquivo_corpo = Path(
            argv[argv.index("--output") + 1]
        )

        arquivo_corpo.write_text(
            corpo
            if corpo is not None
            else json.dumps({"elements": []})
        )

        headers = [
            "HTTP/2 " + str(http),
        ]

        if retry_after is not None:
            headers.append(
                "Retry-After: " + retry_after
            )

        arquivo_headers = Path(
            argv[
                argv.index("--dump-header") + 1
            ]
        )
        arquivo_headers.write_text(
            "\n".join(headers)
        )

        medidas = {
            "response_code": http,
            "ssl_verify_result": 0,
            "remote_ip": ip,
            "time_total": 0.2,
            "time_namelookup": 0.01,
            "time_connect": 0.02,
            "time_appconnect": 0.05,
            "time_starttransfer": 0.1,
        }

        return subprocess.CompletedProcess(
            argv,
            codigo,
            stdout=(
                json.dumps(medidas)
                if stdout is None
                else stdout
            ),
            stderr=stderr,
        )

    return executar


class ConfiguracaoTests(unittest.TestCase):
    def test_padrao_da_captura_preservado_sem_terceiro_automatico(self):
        urls, ipv4 = plano_captura({})

        self.assertEqual(
            urls,
            (
                PRINCIPAL,
                ALTERNATIVO,
                PRINCIPAL,
            ),
        )
        self.assertFalse(ipv4)

    def test_diagnostico_vazio_testa_tres_candidatos(self):
        self.assertEqual(
            servidores_configurados(
                "",
                diagnostico=True,
            ),
            PERMITIDOS,
        )

        self.assertEqual(
            servidores_configurados(""),
            (PRINCIPAL, ALTERNATIVO),
        )

    def test_ordem_terceiro_e_maximo_tres_tentativas(self):
        urls, ipv4 = plano_captura({
            "OSM_OVERPASS_URLS": ",".join((
                TERCEIRO,
                PRINCIPAL,
                ALTERNATIVO,
            )),
        })

        self.assertEqual(
            urls,
            (
                TERCEIRO,
                PRINCIPAL,
                ALTERNATIVO,
            ),
        )
        self.assertFalse(ipv4)

    def test_um_servidor_explicito_tem_tres_tentativas_limitadas(self):
        self.assertEqual(
            plano_captura({
                "OSM_OVERPASS_URLS": TERCEIRO,
            })[0],
            (TERCEIRO,) * 3,
        )

        self.assertEqual(
            servidores_configurados(
                TERCEIRO + "," + TERCEIRO
            ),
            (TERCEIRO,),
        )

    def test_url_arbitraria_credenciais_e_parametros_sao_rejeitados(self):
        entradas = (
            "http://overpass-api.de/api/interpreter",
            "https://localhost/api/interpreter",
            (
                "https://usuario:TOKEN-FICTICIO"
                "@overpass-api.de/api/interpreter"
            ),
            PRINCIPAL + "?token=TOKEN-FICTICIO",
            PRINCIPAL + "#fragmento",
            PRINCIPAL + ",",
            ",".join([PRINCIPAL] * 4),
            PRINCIPAL + "\n--insecure",
        )

        for valor in entradas:
            with self.subTest(valor=valor):
                with self.assertRaises(
                    ConfiguracaoOverpassInvalida
                ) as erro:
                    servidores_configurados(
                        valor
                    )

                self.assertNotIn(
                    "TOKEN-FICTICIO",
                    str(erro.exception),
                )

    def test_ipv4_explicito_validado_sem_coagir_valores(self):
        self.assertTrue(
            plano_captura({
                "OSM_OVERPASS_IPV4": "true",
            })[1]
        )

        self.assertFalse(
            plano_captura({
                "OSM_OVERPASS_IPV4": "false",
            })[1]
        )

        for valor in (
            "True",
            "1",
            True,
            "TOKEN-FICTICIO",
        ):
            with self.assertRaises(
                ConfiguracaoOverpassInvalida
            ):
                plano_captura({
                    "OSM_OVERPASS_IPV4": valor,
                })


class RedeTests(unittest.TestCase):
    def test_get_ipv4_preserva_tls_limites_e_consulta_minima(self):
        comando = comando_sonda(
            PRINCIPAL,
            "GET",
            "ipv4",
            "corpo",
            "headers",
        )

        self.assertIn("--ipv4", comando)
        self.assertIn("--get", comando)
        self.assertIn(
            "data=" + CONSULTA,
            comando,
        )
        self.assertEqual(
            comando[
                comando.index("--max-time") + 1
            ],
            "12",
        )
        self.assertEqual(
            comando[
                comando.index("--retry") + 1
            ],
            "0",
        )
        self.assertIn("=https", comando)

        for proibido in (
            "--insecure",
            "-k",
            "--location",
            "--proxy",
            "--resolve",
        ):
            self.assertNotIn(
                proibido,
                comando,
            )

    def test_alvo_e_perfil_arbitrarios_nao_geram_comando(self):
        entradas = (
            (
                "https://exemplo.invalid",
                "GET",
                "ipv4",
            ),
            (
                PRINCIPAL,
                "DELETE",
                "automatico",
            ),
            (
                PRINCIPAL,
                "GET",
                "outro",
            ),
        )

        for servidor, metodo, perfil in entradas:
            with self.assertRaises(ValueError):
                comando_sonda(
                    servidor,
                    metodo,
                    perfil,
                    "a",
                    "b",
                )

    def test_sucesso_precisa_json_overpass_e_nao_valida_municipio(self):
        resultado = sondar(
            PRINCIPAL,
            "GET",
            "automatico",
            executar=executor_falso(),
        )

        self.assertTrue(
            resultado[
                "resposta_overpass_reconhecida"
            ]
        )
        self.assertFalse(
            resultado["consulta_municipal"]
        )
        self.assertEqual(
            resultado["categoria"],
            "resposta_minima_valida",
        )

    def test_html_vazio_remark_nan_e_grande_nao_sao_sucesso_http200(self):
        corpos = (
            "<html>bloqueio</html>",
            "",
            (
                '{"elements":[],'
                '"remark":"incompleto"}'
            ),
            '{"elements":[],"n":NaN}',
            "x" * 262145,
            '{"sem_elements":[]}',
        )

        for corpo in corpos:
            resultado = sondar(
                PRINCIPAL,
                "GET",
                "automatico",
                executar=executor_falso(
                    corpo=corpo
                ),
            )

            self.assertFalse(
                resultado[
                    "resposta_overpass_reconhecida"
                ]
            )

    def test_curl7_sem_http_nao_e_falha_do_metodo_ou_sucesso_tls(self):
        resultado = sondar(
            PRINCIPAL,
            "POST",
            "automatico",
            executar=executor_falso(
                codigo=7,
                http=0,
                ip="",
            ),
        )

        self.assertEqual(
            resultado["categoria"],
            "falha_conexao",
        )
        self.assertEqual(
            resultado["status_http"],
            0,
        )
        self.assertFalse(
            resultado[
                "resposta_overpass_reconhecida"
            ]
        )
        self.assertEqual(
            resultado["familia_ip_remota"],
            "indisponivel",
        )

    def test_timeout_com_ip_ipv4_nao_e_explica_por_ipv6(self):
        resultado = sondar(
            ALTERNATIVO,
            "GET",
            "automatico",
            executar=executor_falso(
                codigo=28,
                http=0,
            ),
        )

        self.assertEqual(
            resultado["familia_ip_remota"],
            "IPv4",
        )
        self.assertEqual(
            resultado["categoria"],
            "timeout",
        )
        self.assertFalse(
            resultado[
                "resposta_overpass_reconhecida"
            ]
        )

    def test_502_e_tls_zero_nao_sao_resposta_valida(self):
        resultado = sondar(
            PRINCIPAL,
            "POST",
            "automatico",
            executar=executor_falso(
                http=502
            ),
        )

        self.assertEqual(
            resultado["categoria"],
            "falha_http",
        )
        self.assertFalse(
            resultado[
                "resposta_overpass_reconhecida"
            ]
        )

    def test_metadados_invalidos_nao_imprimem_corpo_ou_stderr(self):
        resultado = sondar(
            PRINCIPAL,
            "GET",
            "automatico",
            executar=executor_falso(
                stdout="TOKEN-FICTICIO",
                stderr="TOKEN-FICTICIO",
            ),
        )

        self.assertEqual(
            resultado["categoria"],
            "metricas_invalidas",
        )
        self.assertNotIn(
            "TOKEN-FICTICIO",
            json.dumps(resultado),
        )

    def test_proxy_aparece_so_como_booleano(self):
        env = {
            "HTTPS_PROXY": (
                "https://usuario:TOKEN-FICTICIO"
                "@exemplo.invalid"
            ),
        }

        resultado = sondar(
            PRINCIPAL,
            "GET",
            "automatico",
            env=env,
            executar=executor_falso(
                corpo="TOKEN-FICTICIO",
                stderr="TOKEN-FICTICIO",
            ),
        )

        self.assertTrue(
            resultado["proxy_configurado"]
        )
        self.assertNotIn(
            "TOKEN-FICTICIO",
            json.dumps(resultado),
        )

    def test_timeout_processo_e_executor_indisponivel_sao_reportados(self):
        entradas = (
            (
                subprocess.TimeoutExpired(
                    "curl",
                    18,
                ),
                "timeout_processo",
            ),
            (
                OSError("TOKEN-FICTICIO"),
                "falha_executor",
            ),
        )

        for erro, categoria in entradas:
            def executar(*args, **kwargs):
                raise erro

            resultado = sondar(
                PRINCIPAL,
                "GET",
                "automatico",
                executar=executar,
            )

            self.assertEqual(
                resultado["categoria"],
                categoria,
            )
            self.assertNotIn(
                "TOKEN-FICTICIO",
                json.dumps(resultado),
            )

    def test_diagnostico_completo_tem_nove_sondas_sem_banco_ou_mudar_env(self):
        chamadas = []
        pausas = []
        env = {}
        antes = dict(env)

        resultado = diagnosticar_rede(
            env,
            executar=executor_falso(
                chamadas=chamadas
            ),
            pausar=pausas.append,
        )

        self.assertEqual(
            resultado["testes_realizados"],
            9,
        )
        self.assertEqual(len(chamadas), 9)
        self.assertEqual(len(pausas), 8)
        self.assertTrue(
            all(pausa == 2 for pausa in pausas)
        )

        argumentos = {
            "capture_output": True,
            "text": True,
            "timeout": 18,
            "check": False,
        }

        self.assertTrue(
            all(
                chamada[1] == argumentos
                for chamada in chamadas
            )
        )
        self.assertEqual(env, antes)

        for chave in (
            "banco_consultado",
            "gravacao_banco_habilitada",
            "consulta_municipal_validada",
            "configuracao_alterada",
        ):
            self.assertFalse(
                resultado[chave]
            )

    def test_sem_resposta_nao_e_rotulado_saudavel(self):
        resultado = diagnosticar_rede(
            {},
            executar=executor_falso(
                codigo=7,
                http=0,
            ),
            pausar=lambda segundos: None,
        )

        self.assertEqual(
            resultado["status"],
            "sem_resposta_minima_valida",
        )

    def test_retryafter_ou_recusa_interrompe_perfis_do_host(self):
        entradas = (
            (429, None),
            (403, None),
            (401, None),
            (503, "120"),
            (503, "TOKEN-FICTICIO"),
        )

        for http, retry_after in entradas:
            def nao_pausar(segundos):
                self.fail("Não deve repetir")

            resultado = diagnosticar_rede(
                {
                    "OSM_OVERPASS_URLS": PRINCIPAL,
                },
                executar=executor_falso(
                    http=http,
                    retry_after=retry_after,
                ),
                pausar=nao_pausar,
            )

            self.assertEqual(
                resultado["testes_realizados"],
                1,
            )
            self.assertTrue(
                resultado["paradas_por_host"]
            )
            self.assertNotIn(
                "TOKEN-FICTICIO",
                json.dumps(resultado),
            )

    def test_certificado_rejeitado_nao_e_contornado_em_ipv4(self):
        def nao_pausar(segundos):
            self.fail("Não deve repetir")

        resultado = diagnosticar_rede(
            {
                "OSM_OVERPASS_URLS": PRINCIPAL,
            },
            executar=executor_falso(
                codigo=60,
                http=0,
            ),
            pausar=nao_pausar,
        )

        self.assertEqual(
            resultado["testes_realizados"],
            1,
        )
        self.assertEqual(
            resultado[
                "paradas_por_host"
            ][0]["motivo"],
            "falha_tls_sem_contorno",
        )

    def test_configuracao_invalida_impede_toda_rede(self):
        def nao_consultar(*args, **kwargs):
            self.fail("Não deve consultar")

        with self.assertRaises(
            ConfiguracaoOverpassInvalida
        ):
            diagnosticar_rede(
                {
                    "OSM_OVERPASS_URLS": (
                        "https://exemplo.invalid"
                    ),
                },
                executar=nao_consultar,
            )

    def test_resumo_nao_afirma_validacao_municipal(self):
        resultado = diagnosticar_rede(
            {},
            executar=executor_falso(),
            pausar=lambda segundos: None,
        )

        resumo = resumo_markdown(resultado)

        self.assertIn(
            "não comprova a consulta municipal",
            resumo,
        )
        self.assertIn(
            "sem resposta HTTP",
            resumo,
        )


class CLITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.pasta = Path(self.tmp.name)

        spec = importlib.util.spec_from_file_location(
            "cli_rede",
            ROOT
            / "scripts/diagnosticar_rede_overpass.py",
        )

        if spec is None or spec.loader is None:
            raise RuntimeError(
                "Não foi possível carregar "
                "o script de diagnóstico."
            )

        self.cli = importlib.util.module_from_spec(
            spec
        )
        spec.loader.exec_module(self.cli)

    def test_cli_com_falhas_salva_relatorio_e_retorna_2(self):
        def executar(env, emitir):
            return diagnosticar_rede(
                env,
                executar=executor_falso(
                    codigo=7,
                    http=0,
                ),
                pausar=lambda segundos: None,
                emitir=emitir,
            )

        destino = self.pasta / "saida"

        with patch(
            "sys.stdout",
            new_callable=io.StringIO,
        ):
            self.assertEqual(
                self.cli.main(
                    ["--saida", str(destino)],
                    {},
                    executar,
                ),
                2,
            )

        resultado = json.loads(
            (destino / "relatorio.json")
            .read_text()
        )

        self.assertEqual(
            resultado["testes_realizados"],
            9,
        )
        self.assertEqual(
            resultado["status"],
            "sem_resposta_minima_valida",
        )

    def test_cli_resposta_minima_valida_nunca_aplica_carga(self):
        def executar(env, emitir):
            return diagnosticar_rede(
                env,
                executar=executor_falso(),
                pausar=lambda segundos: None,
                emitir=emitir,
            )

        destino = self.pasta / "saida"

        with patch(
            "sys.stdout",
            new_callable=io.StringIO,
        ):
            self.assertEqual(
                self.cli.main(
                    ["--saida", str(destino)],
                    {},
                    executar,
                ),
                0,
            )

        resultado = json.loads(
            (destino / "relatorio.json")
            .read_text()
        )

        self.assertFalse(
            resultado[
                "consulta_municipal_validada"
            ]
        )

    def test_saida_existente_nao_e_sobrescrita(self):
        marcador = self.pasta / "preservar"
        marcador.write_text("original")

        def nao_consultar(*args, **kwargs):
            self.fail("Não consultar")

        with patch(
            "sys.stderr",
            new_callable=io.StringIO,
        ):
            self.assertEqual(
                self.cli.main(
                    ["--saida", str(self.pasta)],
                    {},
                    nao_consultar,
                ),
                2,
            )

        self.assertEqual(
            marcador.read_text(),
            "original",
        )

    def test_erro_de_configuracao_sanitizado(self):
        env = {
            "OSM_OVERPASS_URLS": (
                "https://usuario:TOKEN-FICTICIO"
                "@exemplo.invalid"
            ),
        }

        with patch(
            "sys.stderr",
            new_callable=io.StringIO,
        ) as saida:
            self.assertEqual(
                self.cli.main(
                    [
                        "--saida",
                        str(self.pasta / "saida"),
                    ],
                    env,
                ),
                2,
            )

        self.assertIn(
            "servidor_overpass_nao_permitido",
            saida.getvalue(),
        )
        self.assertNotIn(
            "TOKEN-FICTICIO",
            saida.getvalue(),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)