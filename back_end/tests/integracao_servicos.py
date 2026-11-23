"""Integração real só no schema vazio ldo_validacao_servicos do stack descartável.

Nunca executar no TiDB online. O override Docker dedicado fornece o destino.
Dropbox é simulado; TLS, DDL, FKs, locks, commit e rollback são reais.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import io
import os
from pathlib import Path
import secrets
import sys
import unittest
from typing import Any
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jwt
from PIL import Image
from werkzeug.test import TestResponse

from app import create_app
from app.rotas import servicos
from services.database import get_db_connection, load_config
from services.migrations import load_migrations, run, split_sql

ROOT = Path(__file__).resolve().parents[1]
BANCO = "ldo_validacao_servicos"


class CursorFalho:
    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        self.cursor.__enter__()
        return self

    def __exit__(self, *args):
        return self.cursor.__exit__(*args)

    def __getattr__(self, nome):
        return getattr(self.cursor, nome)

    def execute(self, sql, params=None):
        normalizado = " ".join(sql.split())

        if "UPDATE solicitacoes_servicos SET estado=" in normalizado:
            raise RuntimeError(
                "Falha de teste após alterar a oferta"
            )

        return self.cursor.execute(sql, params)


class ConexaoFalha:
    def __init__(self, conn, commit_perdido=False):
        self.conn = conn
        self.commit_perdido = commit_perdido

    def __getattr__(self, nome):
        return getattr(self.conn, nome)

    def cursor(self):
        if self.commit_perdido:
            return self.conn.cursor()

        return CursorFalho(self.conn.cursor())

    def commit(self):
        self.conn.commit()

        if self.commit_perdido:
            raise RuntimeError(
                "Resposta de commit perdida no teste"
            )


class IntegracaoServicos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = load_config()

        if (
            os.getenv("LDO_DOCKER_LOCAL") != "1"
            or os.getenv("DATABASE_URL", "")
            or config.host != "db"
            or config.database != BANCO
        ):
            raise RuntimeError(
                "Este teste exige o stack Docker descartável de serviços."
            )

        conn = get_db_connection()

        try:
            with conn.cursor() as c:
                c.execute(
                    "SELECT DATABASE() AS banco,VERSION() AS versao"
                )
                info = c.fetchone()

                if info is None:
                    raise RuntimeError(
                        "Não foi possível identificar o banco de testes."
                    )

                if (
                    info["banco"] != BANCO
                    or "tidb" in info["versao"].lower()
                ):
                    raise RuntimeError(
                        "Destino real/inesperado recusado."
                    )

                c.execute("SHOW TABLES")

                if c.fetchall():
                    raise RuntimeError(
                        "O banco descartável deve estar vazio."
                    )

                for sql in split_sql(
                    (ROOT / "docker/schema_base.sql").read_text()
                ):
                    c.execute(sql)

            conn.commit()

            relatorio = run(
                conn,
                load_migrations(ROOT / "migrations"),
                apply=True,
                expected_database=BANCO,
            )

            assert all(
                m["estado"] == "aplicada"
                for m in relatorio["migracoes"]
            )
        finally:
            conn.close()

        cls.app = create_app()
        cls.app.config["TESTING"] = True

        img = Image.new("RGB", (30, 20), "green")
        f = io.BytesIO()
        img.save(f, "JPEG")
        img.close()
        cls.jpeg = f.getvalue()

    def sql(self, sql, params=()):
        conn = get_db_connection()

        try:
            with conn.cursor() as c:
                c.execute(sql, params)
                itens = c.fetchall() if c.description else []
                id = c.lastrowid

            conn.commit()
            return itens, id
        finally:
            conn.close()

    def setUp(self):
        self.usuarios = []

        for i in range(3):
            _, id = self.sql(
                """
                INSERT INTO usuarios(nome,email,email_verificado)
                VALUES (%s,%s,1)
                """,
                (
                    "Pessoa de teste",
                    secrets.token_hex(8) + "@example.invalid",
                ),
            )
            self.usuarios.append(id)

        _, self.posto = self.sql(
            """
            INSERT INTO postos(
                nome,endereco,latitude,longitude,tipo_posto
            )
            VALUES (
                '[TESTE] Serviços',
                'Endereço fictício',
                -7.11,
                -34.86,
                'Convencional'
            )
            """
        )

        self.env = patch.dict(
            os.environ,
            {
                "ADMIN_USUARIO_IDS": ",".join(
                    map(str, self.usuarios[1:])
                ),
            },
        )
        self.env.start()

        self.upload = patch.object(
            servicos.fotos_servicos,
            "guardar",
            side_effect=lambda _: secrets.token_hex(16) + ".jpg",
        )
        self.guardar = self.upload.start()

        self.limpeza = patch.object(
            servicos.fotos_servicos,
            "remover",
            return_value=True,
        )
        self.remover = self.limpeza.start()

    def tearDown(self):
        self.limpeza.stop()
        self.upload.stop()
        self.env.stop()

    def corpo(self, resposta: TestResponse) -> dict[str, Any]:
        dados = resposta.get_json()

        if not isinstance(dados, dict):
            raise AssertionError(
                "A resposta da API deve conter um objeto JSON."
            )

        return dados

    def catalogo(
        self,
        resposta: TestResponse,
    ) -> list[dict[str, Any]]:
        dados = resposta.get_json()

        if not isinstance(dados, list) or any(
            not isinstance(item, dict)
            for item in dados
        ):
            raise AssertionError(
                "O catálogo deve conter uma lista de objetos JSON."
            )

        return dados

    def headers(self, indice=0):
        t = jwt.encode(
            {
                "usuario_id": self.usuarios[indice],
                "ver": 0,
                "exp": (
                    datetime.now(timezone.utc)
                    + timedelta(minutes=5)
                ),
            },
            self.app.config["SECRET_KEY"],
            algorithm="HS256",
        )
        return {"Authorization": "Bearer " + t}

    def enviar(self, indice=0, chave=None):
        with self.app.test_client() as client:
            return client.post(
                f"/postos/{self.posto}/servicos/solicitacoes",
                headers=self.headers(indice),
                data={
                    "codigo": "recarga_eletrica",
                    "chave_cliente": chave or "a" * 32,
                    "observacao": "Carregador identificado no posto",
                    "consentimento": "true",
                    "presenca_observada": "true",
                    "simulada": "false",
                    "latitude": "-7.11",
                    "longitude": "-34.86",
                    "precisao_m": "10",
                    "foto": (
                        io.BytesIO(self.jpeg),
                        "foto.jpg",
                    ),
                },
            )

    def decidir(self, id, indice=1, decisao="aprovar"):
        with self.app.test_client() as client:
            return client.post(
                f"/admin/servicos/solicitacoes/{id}/decidir",
                headers=self.headers(indice),
                json={
                    "decisao": decisao,
                    "motivo": "Evidência revisada no teste",
                    "foto_revisada": True,
                },
            )

    def test_fluxo_pendente_aprovado_libera_lote_misto_com_kwh(self):
        r = self.enviar()
        dados = self.corpo(r)

        self.assertEqual(r.status_code, 201, dados)

        corpo = {
            "posto_id": self.posto,
            "itens": [
                {
                    "tipo_combustivel": "Gasolina Comum",
                    "preco": "6.29",
                },
                {
                    "tipo_combustivel": "Recarga Elétrica (kWh)",
                    "preco": "2.20",
                },
            ],
            "latitude": -7.11,
            "longitude": -34.86,
            "precisao_m": 10,
            "simulada": False,
        }

        with self.app.test_client() as c:
            self.assertEqual(
                c.post(
                    "/precos/lote",
                    json=corpo,
                    headers=self.headers(),
                ).status_code,
                400,
            )
            self.assertEqual(
                self.decidir(dados["id"]).status_code,
                200,
            )
            salvo = c.post(
                "/precos/lote",
                json=corpo,
                headers=self.headers(),
            )

        confirmacao = self.corpo(salvo)

        self.assertEqual(salvo.status_code, 201, confirmacao)
        self.assertEqual(confirmacao["karma_ganho"], 10)

        itens, _ = self.sql(
            "SELECT tipo_posto FROM postos WHERE id=%s",
            (self.posto,),
        )
        self.assertEqual(
            itens[0]["tipo_posto"],
            "Convencional",
        )

        itens, _ = self.sql(
            """
            SELECT COUNT(*) AS n
            FROM registos_preco WHERE posto_id=%s
            """,
            (self.posto,),
        )
        self.assertEqual(itens[0]["n"], 2)

    def test_envios_concorrentes_idempotentes_fazem_um_upload(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            respostas = list(
                pool.map(lambda _: self.enviar(), range(2))
            )

        self.assertEqual(
            sorted(r.status_code for r in respostas),
            [200, 201],
        )
        self.assertEqual(
            len({self.corpo(r)["id"] for r in respostas}),
            1,
        )
        self.guardar.assert_called_once()

    def test_catalogo_e_cadastro_individual_usam_a_oferta_aprovada(self):
        id = self.corpo(self.enviar())["id"]
        url = (
            "/postos?combustiveis=recarga_eletrica"
            "&referencia=recarga_eletrica"
        )
        corpo = {
            "posto_id": self.posto,
            "tipo_combustivel": "Recarga Elétrica (kWh)",
            "preco": "2.29",
            "latitude": -7.11,
            "longitude": -34.86,
            "precisao_m": 10,
            "simulada": False,
        }

        with self.app.test_client() as c:
            self.assertNotIn(
                self.posto,
                [p["id"] for p in self.catalogo(c.get(url))],
            )
            self.assertEqual(
                c.post(
                    "/precos",
                    json=corpo,
                    headers=self.headers(),
                ).status_code,
                400,
            )
            self.assertEqual(
                self.decidir(id).status_code,
                200,
            )

            lista = self.catalogo(c.get(url))
            item = next(
                p for p in lista
                if p["id"] == self.posto
            )

            self.assertEqual(
                item["unidade_referencia"],
                "kWh",
            )
            self.assertIsNone(item["preco_referencia"])

            self.assertEqual(
                c.post(
                    "/precos",
                    json=corpo,
                    headers=self.headers(),
                ).status_code,
                201,
            )

            item = next(
                p for p in self.catalogo(c.get(url))
                if p["id"] == self.posto
            )
            self.assertEqual(
                item["preco_referencia"],
                2.29,
            )

            self.sql(
                """
                UPDATE postos_combustiveis
                SET disponivel_manual=0 WHERE posto_id=%s
                """,
                (self.posto,),
            )

            self.assertEqual(
                c.post(
                    "/precos",
                    json=corpo,
                    headers=self.headers(),
                ).status_code,
                409,
            )
            self.assertNotIn(
                self.posto,
                [p["id"] for p in self.catalogo(c.get(url))],
            )

    def test_confirmacao_antiga_nao_contorna_revisao_de_recarga_em_posto_convencional(self):
        with self.app.test_client() as c:
            r = c.post(
                f"/postos/{self.posto}/ofertas/recarga_eletrica/confirmar",
                headers=self.headers(),
                json={
                    "confirmado": True,
                    "simulada": False,
                    "latitude": -7.11,
                    "longitude": -34.86,
                    "precisao_m": 10,
                },
            )
            self.assertEqual(r.status_code, 400)

        self.assertEqual(self.enviar().status_code, 201)

        ofertas, _ = self.sql(
            """
            SELECT posto_id FROM postos_combustiveis
            WHERE posto_id=%s
            """,
            (self.posto,),
        )
        self.assertEqual(ofertas, ())

    def test_decisoes_concorrentes_conservam_uma_decisao(self):
        id = self.corpo(self.enviar())["id"]

        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(
                self.decidir,
                id,
                1,
                "aprovar",
            )
            b = pool.submit(
                self.decidir,
                id,
                2,
                "rejeitar",
            )
            respostas = [a.result(), b.result()]

        self.assertEqual(
            sorted(r.status_code for r in respostas),
            [200, 409],
        )

        rows, _ = self.sql(
            """
            SELECT estado,revisado_por
            FROM solicitacoes_servicos WHERE id=%s
            """,
            (id,),
        )
        ofertas, _ = self.sql(
            """
            SELECT disponivel_manual
            FROM postos_combustiveis WHERE posto_id=%s
            """,
            (self.posto,),
        )

        self.assertEqual(
            bool(ofertas),
            rows[0]["estado"] == "aprovada",
        )
        self.assertIn(
            rows[0]["revisado_por"],
            self.usuarios[1:],
        )

    def test_falha_apos_upsert_faz_rollback_de_oferta_e_decisao(self):
        id = self.corpo(self.enviar())["id"]

        with patch.object(
            servicos,
            "get_db_connection",
            side_effect=lambda: ConexaoFalha(
                get_db_connection()
            ),
        ):
            r = self.decidir(id)

        self.assertEqual(r.status_code, 503)

        rows, _ = self.sql(
            """
            SELECT estado
            FROM solicitacoes_servicos WHERE id=%s
            """,
            (id,),
        )
        self.assertEqual(
            rows[0]["estado"],
            "pendente",
        )

        rows, _ = self.sql(
            """
            SELECT posto_id
            FROM postos_combustiveis WHERE posto_id=%s
            """,
            (self.posto,),
        )
        self.assertEqual(rows, ())

    def test_commit_perdido_preserva_registro_e_comprovante(self):
        with patch.object(
            servicos,
            "get_db_connection",
            side_effect=lambda: ConexaoFalha(
                get_db_connection(),
                True,
            ),
        ):
            r = self.enviar()

        self.assertEqual(r.status_code, 503)
        self.remover.assert_not_called()
        self.assertEqual(self.enviar().status_code, 200)
        self.guardar.assert_called_once()

    def test_exclusao_de_conta_preserva_evidencia_sem_identidade(self):
        id = self.corpo(self.enviar())["id"]

        self.sql(
            "DELETE FROM usuarios WHERE id=%s",
            (self.usuarios[0],),
        )
        rows, _ = self.sql(
            """
            SELECT usuario_id,estado
            FROM solicitacoes_servicos WHERE id=%s
            """,
            (id,),
        )

        self.assertIsNone(rows[0]["usuario_id"])
        self.assertEqual(
            self.decidir(id).status_code,
            200,
        )

    def test_schema_rejeita_estado_e_produto_invalidos(self):
        id = self.corpo(self.enviar())["id"]

        for sql, params in [
            (
                "UPDATE solicitacoes_servicos "
                "SET estado='inexistente' WHERE id=%s",
                (id,),
            ),
            (
                "UPDATE solicitacoes_servicos "
                "SET combustivel_codigo='glp' WHERE id=%s",
                (id,),
            ),
        ]:
            with self.assertRaises(Exception):
                self.sql(sql, params)


if __name__ == "__main__":
    unittest.main(verbosity=2)