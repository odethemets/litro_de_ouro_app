"""HTTP Flask/CORS reais; banco simulado."""
import copy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

from flask import Flask
from flask_cors import CORS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.infra_web import (
    Prontidao,
    configurar_web,
    origens_permitidas,
)
from services.contrato_migracoes import load_migrations

ROOT = Path(__file__).resolve().parents[1]


def migs():
    return load_migrations(ROOT / "migrations")


def registros():
    return [
        {
            "versao": m["versao"],
            "sha256": m["sha256"],
            "estado": "aplicada",
        }
        for m in migs()
    ]


class Banco:
    def __init__(self, linhas=None, erro_rollback=False):
        self.linhas = (
            registros()
            if linhas is None
            else copy.deepcopy(linhas)
        )
        self.erro_rollback = erro_rollback
        self.sql = []
        self.reverteu = False
        self.fechou = False

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql):
        if not sql.startswith("SELECT "):
            raise AssertionError(
                "A saúde não pode escrever no banco."
            )
        self.sql.append(sql)

    def fetchall(self):
        return copy.deepcopy(self.linhas)

    def rollback(self):
        self.reverteu = True
        if self.erro_rollback:
            raise OSError("detalhe-privado")

    def close(self):
        self.fechou = True


class InfraTests(unittest.TestCase):
    def cliente(
        self,
        banco=None,
        ambiente=None,
        conectar=None,
    ):
        app = Flask(__name__)
        app.testing = True

        conector = conectar or Mock(
            return_value=banco or Banco()
        )

        configurar_web(
            app,
            ambiente={} if ambiente is None else ambiente,
            conectar=conector,
        )

        @app.route(
            "/recurso",
            methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        )
        def recurso():
            return {"ok": True}

        return app.test_client(), conector, app

    def test_local_preserva_acesso_web(self):
        cliente, _, _ = self.cliente()
        origem = "http://192.168.1.9:8081"

        r = cliente.get(
            "/recurso",
            headers={"Origin": origem},
        )

        self.assertEqual(
            r.headers["Access-Control-Allow-Origin"],
            origem,
        )

    def test_producao_exige_origens(self):
        valores = (
            "",
            "*",
            "https://app.exemplo,*",
            "http://app.exemplo",
        )

        for valor in valores:
            with self.subTest(valor=valor):
                with self.assertRaises(ValueError):
                    origens_permitidas({
                        "APP_ENV": "production",
                        "CORS_ORIGINS": valor,
                    })

    def test_origem_invalida_e_recusada(self):
        valores = (
            "https://app.exemplo/caminho",
            "https://u:s@app.exemplo",
            "https://*.vercel.app",
            "https://app.exemplo?x=1",
            "https://app.exemplo#x",
            "https://app.exemplo:erro",
            "https://app.exemplo,",
            "https://app. exemplo",
        )

        for valor in valores:
            with self.subTest(valor=valor):
                with self.assertRaises(ValueError):
                    origens_permitidas({
                        "CORS_ORIGINS": valor,
                    })

    def test_normaliza_e_deduplica_origens(self):
        resultado = origens_permitidas({
            "CORS_ORIGINS": (
                "https://APP.exemplo:443/,"
                "https://app.exemplo,"
                "http://localhost:8081/"
            ),
        })

        self.assertEqual(
            resultado,
            [
                "https://app.exemplo",
                "http://localhost:8081",
            ],
        )

    def test_perfil_desconhecido_e_recusado(self):
        with self.assertRaises(ValueError):
            origens_permitidas({
                "APP_ENV": "prodution",
            })

    def test_cors_anterior_precisa_ser_substituido(self):
        app = Flask(__name__)
        CORS(app)

        with self.assertRaisesRegex(ValueError, "Substitua"):
            configurar_web(app, ambiente={})

    def test_cors_producao_aceita_somente_origem_exata(self):
        cliente, _, _ = self.cliente(ambiente={
            "APP_ENV": "production",
            "CORS_ORIGINS": "https://app.exemplo",
        })

        permitido = cliente.get(
            "/recurso",
            headers={"Origin": "https://app.exemplo"},
        )

        self.assertEqual(
            permitido.headers["Access-Control-Allow-Origin"],
            "https://app.exemplo",
        )

        for origem in (
            "https://app.exemplo.evil.invalid",
            "https://appXexemplo",
            "http://app.exemplo",
        ):
            with self.subTest(origem=origem):
                r = cliente.get(
                    "/recurso",
                    headers={"Origin": origem},
                )
                self.assertNotIn(
                    "Access-Control-Allow-Origin",
                    r.headers,
                )

    def test_preflight_suporta_jwt_e_metodos_da_conta(self):
        cliente, _, _ = self.cliente(ambiente={
            "CORS_ORIGINS": "https://app.exemplo",
        })

        for metodo in ("POST", "PUT", "PATCH", "DELETE"):
            r = cliente.options(
                "/recurso",
                headers={
                    "Origin": "https://app.exemplo",
                    "Access-Control-Request-Method": metodo,
                    "Access-Control-Request-Headers": (
                        "authorization,content-type"
                    ),
                },
            )

            self.assertIn(
                metodo,
                r.headers["Access-Control-Allow-Methods"],
            )

            cabecalhos = r.headers[
                "Access-Control-Allow-Headers"
            ].lower()

            self.assertIn("authorization", cabecalhos)
            self.assertIn("content-type", cabecalhos)
            self.assertNotIn(
                "Access-Control-Allow-Credentials",
                r.headers,
            )

    def test_mobile_sem_origin_continua_respondendo(self):
        cliente, _, _ = self.cliente(ambiente={
            "APP_ENV": "production",
            "CORS_ORIGINS": "https://app.exemplo",
        })

        r = cliente.get("/recurso")

        self.assertEqual(r.status_code, 200)
        self.assertNotIn(
            "Access-Control-Allow-Origin",
            r.headers,
        )

    def test_live_nao_consulta_banco(self):
        conectar = Mock(
            side_effect=RuntimeError("detalhe-privado")
        )
        cliente, _, _ = self.cliente(conectar=conectar)

        r = cliente.get("/health/live")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json, {"status": "ok"})
        self.assertEqual(
            r.headers["Cache-Control"],
            "no-store",
        )
        conectar.assert_not_called()

    def test_ready_confere_migracoes_e_fecha_conexao(self):
        banco = Banco()
        cliente, conectar, _ = self.cliente(banco=banco)

        r = cliente.get("/health/ready")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json, {"status": "pronto"})
        conectar.assert_called_once_with(
            read_only=True,
            time_zone="+00:00",
        )
        self.assertEqual(len(banco.sql), 1)
        self.assertTrue(banco.reverteu)
        self.assertTrue(banco.fechou)

    def test_migracoes_divergentes_retornam_503(self):
        for tipo in (
            "pendente",
            "ausente",
            "hash",
            "desconhecida",
        ):
            linhas = registros()

            if tipo == "ausente":
                linhas.pop()
            elif tipo == "desconhecida":
                linhas.append({
                    "versao": "999_futura",
                    "sha256": "x",
                    "estado": "aplicada",
                })
            else:
                campo = "estado" if tipo == "pendente" else "sha256"
                linhas[-1][campo] = "divergente"

            with self.subTest(tipo=tipo):
                cliente, _, _ = self.cliente(
                    banco=Banco(linhas)
                )

                r = cliente.get("/health/ready")

                self.assertEqual(r.status_code, 503)
                self.assertEqual(
                    r.json,
                    {"status": "indisponivel"},
                )

    def test_falha_de_banco_nao_expoe_detalhes(self):
        conectar = Mock(
            side_effect=RuntimeError(
                "mysql://usuario:senha@host"
            )
        )
        cliente, _, _ = self.cliente(conectar=conectar)

        r = cliente.get("/health/ready")

        self.assertEqual(r.status_code, 503)
        self.assertNotIn(
            "senha",
            r.get_data(as_text=True),
        )
        self.assertEqual(
            r.headers["Cache-Control"],
            "no-store",
        )

    def test_rollback_falho_ainda_fecha_conexao(self):
        banco = Banco(erro_rollback=True)
        cliente, _, _ = self.cliente(banco=banco)

        self.assertEqual(
            cliente.get("/health/ready").status_code,
            503,
        )
        self.assertTrue(banco.fechou)

    def test_cache_expira_apos_cinco_segundos(self):
        agora = [10]
        banco = Banco()
        conectar = Mock(return_value=banco)

        pronta = Prontidao(
            migs(),
            conectar,
            relogio=lambda: agora[0],
        )

        self.assertTrue(pronta.consultar())

        banco.linhas = []
        agora[0] = 14.9

        self.assertTrue(pronta.consultar())
        conectar.assert_called_once()

        agora[0] = 15

        self.assertFalse(pronta.consultar())
        self.assertEqual(conectar.call_count, 2)

    def test_falha_temporaria_e_reavaliada(self):
        agora = [10]
        conectar = Mock(
            side_effect=[OSError("privado"), Banco()]
        )

        pronta = Prontidao(
            migs(),
            conectar,
            relogio=lambda: agora[0],
        )

        self.assertFalse(pronta.consultar())
        self.assertFalse(pronta.consultar())

        agora[0] = 15

        self.assertTrue(pronta.consultar())
        self.assertIsNone(pronta.erro_tipo)

    def test_sondagens_concorrentes_compartilham_consulta(self):
        conectar = Mock(return_value=Banco())
        pronta = Prontidao(migs(), conectar)

        with ThreadPoolExecutor(max_workers=8) as pool:
            resultados = list(
                pool.map(
                    lambda _: pronta.consultar(),
                    range(16),
                )
            )

        self.assertTrue(all(resultados))
        conectar.assert_called_once()


if __name__ == "__main__":
    unittest.main()