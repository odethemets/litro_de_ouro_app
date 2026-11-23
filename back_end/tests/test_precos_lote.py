"""Contrato HTTP e transacao com conexoes simuladas; nao acessa banco real."""
import copy
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import jwt
from flask import Flask

from app.rotas import precos


class Conexao:
    def __init__(self):
        self.salvo = {
            "precos": [],
            "karma": 0,
            "historico": [],
            "eventos": [],
        }
        self.trabalho = copy.deepcopy(self.salvo)
        self.commits = self.rollbacks = self.fechamentos = self.inicios = 0
        self.consultas = []
        self.recentes = set()
        self.ofertas = {}
        self.usuario = True
        self.posto = {
            "latitude": -7.115,
            "longitude": -34.861,
            "nome": "Posto de teste",
            "tipo_posto": "Posto",
        }
        self.falhar_no_insert = None
        self.falhar_evento = False
        self.commit_incerto = False

    def begin(self):
        self.inicios += 1
        self.trabalho = copy.deepcopy(self.salvo)

    def cursor(self):
        return Cursor(self)

    def commit(self):
        self.commits += 1
        self.salvo = copy.deepcopy(self.trabalho)

        if self.commit_incerto:
            raise RuntimeError("Resposta do commit perdida")

    def rollback(self):
        self.rollbacks += 1
        self.trabalho = copy.deepcopy(self.salvo)

    def close(self):
        self.fechamentos += 1


class Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.resposta = None
        self.lastrowid = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def fetchone(self):
        return self.resposta

    def execute(self, sql, params=()):
        q = " ".join(sql.split()).lower()
        c = self.conn
        c.consultas.append((q, params))
        self.resposta = None

        if q.startswith("select versao_token"):
            self.resposta = {"versao_token": 0}

        elif q.startswith("select id from usuarios"):
            self.resposta = {"id": 7} if c.usuario else None

        elif q.startswith("select latitude"):
            self.resposta = c.posto

        elif "from postos_combustiveis" in q:
            self.resposta = {
                "disponivel": c.ofertas.get(params[1])
            }

        elif q.startswith("select 1 from registos_preco"):
            existe = (
                params[2] in c.recentes
                or any(
                    r[2] == params[2]
                    for r in c.salvo["precos"]
                )
            )
            self.resposta = {"recente": 1} if existe else None

        elif q.startswith("select preco from registos_preco"):
            self.resposta = {"preco": Decimal("6.09")}

        elif q.startswith("insert into registos_preco"):
            if (
                len(c.trabalho["precos"]) + 1
                == c.falhar_no_insert
            ):
                raise RuntimeError("Falha de escrita simulada")

            c.trabalho["precos"].append(params)
            self.lastrowid = 100 + len(c.trabalho["precos"])

        elif q.startswith("select id from historico_karma"):
            self.resposta = next(
                (
                    {"id": n}
                    for n, r in enumerate(c.trabalho["historico"])
                    if r[1] == params[1]
                ),
                None,
            )

        elif q.startswith("update usuarios set karma"):
            c.trabalho["karma"] += params[0]

        elif q.startswith("select karma from usuarios"):
            self.resposta = {"karma": c.trabalho["karma"]}

        elif q.startswith("insert into historico_karma"):
            c.trabalho["historico"].append(params)

        elif q.startswith("insert into eventos_preco"):
            if c.falhar_evento:
                raise RuntimeError("Falha de evento simulada")

            c.trabalho["eventos"].append(params)

        else:
            raise AssertionError("SQL inesperado no teste: " + q)


class PrecosLoteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask("test_precos_lote")
        cls.app.config.update(
            TESTING=True,
            SECRET_KEY="chave-sintetica-apenas-para-testes-de-lote-2026",
        )
        cls.app.register_blueprint(
            precos.precos_bp,
            url_prefix="/precos",
        )
        cls.token = jwt.encode(
            {
                "usuario_id": 7,
                "ver": 0,
                "exp": (
                    datetime.now(timezone.utc)
                    + timedelta(minutes=10)
                ),
            },
            cls.app.config["SECRET_KEY"],
            algorithm="HS256",
        )

    def setUp(self):
        self.conn = Conexao()

        self.db = patch.object(
            precos,
            "get_db_connection",
            return_value=self.conn,
        )
        self.db.start()
        self.addCleanup(self.db.stop)

        self.auth = patch(
            "app.utils.decorator.get_db_connection",
            return_value=Conexao(),
        )
        self.auth.start()
        self.addCleanup(self.auth.stop)

        self.cooldown = patch.object(
            precos,
            "COOLDOWN_MINUTOS",
            15,
        )
        self.cooldown.start()
        self.addCleanup(self.cooldown.stop)

        self.client = self.app.test_client()

    def dados(self):
        return {
            "posto_id": 11,
            "latitude": -7.115,
            "longitude": -34.861,
            "precisao_m": 10,
            "simulada": False,
            "itens": [
                {
                    "tipo_combustivel": "Gasolina Comum",
                    "preco": "6.19",
                    "foto_url": (
                        "https://www.dropbox.com/s/teste/foto.jpg"
                    ),
                },
                {
                    "tipo_combustivel": "Etanol",
                    "preco": "4.29",
                },
            ],
        }

    def enviar(self, dados=None):
        return self.client.post(
            "/precos/lote",
            json=self.dados() if dados is None else dados,
            headers={
                "Authorization": "Bearer " + self.token
            },
        )

    def sem_gravacao(self):
        self.assertEqual(
            self.conn.salvo,
            {
                "precos": [],
                "karma": 0,
                "historico": [],
                "eventos": [],
            },
        )
        self.assertEqual(self.conn.commits, 0)

    def test_rota_exige_autenticacao(self):
        r = self.client.post(
            "/precos/lote",
            json=self.dados(),
        )

        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.conn.inicios, 0)

    def test_dois_precos_karma_e_eventos_compartilham_commit(self):
        r = self.enviar()

        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json["total"], 2)
        self.assertEqual(r.json["karma_ganho"], 10)
        self.assertEqual(len(self.conn.salvo["precos"]), 2)
        self.assertEqual(self.conn.salvo["karma"], 10)
        self.assertEqual(len(self.conn.salvo["historico"]), 2)
        self.assertEqual(len(self.conn.salvo["eventos"]), 2)
        self.assertEqual(self.conn.commits, 1)
        self.assertEqual(self.conn.rollbacks, 0)
        self.assertEqual(self.conn.fechamentos, 1)

        primeiro_insert = next(
            n
            for n, (q, _) in enumerate(self.conn.consultas)
            if q.startswith("insert")
        )
        cooldowns = [
            n
            for n, (q, _) in enumerate(self.conn.consultas)
            if q.startswith("select 1 from registos_preco")
        ]

        self.assertEqual(len(cooldowns), 2)
        self.assertLess(max(cooldowns), primeiro_insert)
        self.assertIn(
            "from usuarios",
            self.conn.consultas[0][0],
        )
        self.assertIn(
            "for update",
            self.conn.consultas[0][0],
        )

    def test_item_recente_recusa_todo_lote_antes_dos_inserts(self):
        self.conn.recentes.add("Etanol")
        r = self.enviar()

        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.json["codigo"], "REGISTRO_RECENTE")
        self.sem_gravacao()

        self.assertFalse(
            any(
                q.startswith("insert")
                for q, _ in self.conn.consultas
            )
        )
        self.assertEqual(self.conn.rollbacks, 1)

    def test_repetir_lote_confirmado_nao_duplica_precos_ou_karma(self):
        self.assertEqual(self.enviar().status_code, 201)
        salvo = copy.deepcopy(self.conn.salvo)

        self.assertEqual(self.enviar().status_code, 429)
        self.assertEqual(self.conn.salvo, salvo)
        self.assertEqual(self.conn.commits, 1)

    def test_falha_no_segundo_insert_reverte_primeiro_karma_e_evento(self):
        self.conn.falhar_no_insert = 2

        self.assertEqual(self.enviar().status_code, 500)
        self.sem_gravacao()
        self.assertEqual(self.conn.rollbacks, 1)

    def test_falha_no_evento_reverte_preco_e_karma(self):
        self.conn.falhar_evento = True

        self.assertEqual(self.enviar().status_code, 500)
        self.sem_gravacao()

    def test_commit_com_resposta_perdida_nao_alega_que_nada_foi_salvo(self):
        self.conn.commit_incerto = True
        r = self.enviar()

        self.assertEqual(r.status_code, 500)
        self.assertIn("atividade", r.json["error"])
        self.assertEqual(len(self.conn.salvo["precos"]), 2)
        self.assertEqual(self.conn.salvo["karma"], 10)

    def test_produto_indisponivel_bloqueia_todo_lote(self):
        self.conn.ofertas["etanol"] = 0
        r = self.enviar()

        self.assertEqual(r.status_code, 409)
        self.sem_gravacao()

    def test_gps_distante_ou_impreciso_nao_grava(self):
        for troca, status in (
            ({"latitude": -8.0}, 403),
            ({"precisao_m": 151}, 422),
            ({"latitude": None}, 400),
        ):
            with self.subTest(troca=troca):
                dados = self.dados()
                dados.update(troca)

                self.assertEqual(
                    self.enviar(dados).status_code,
                    status,
                )
                self.sem_gravacao()

    def test_simulada_e_precisao_invalidas_nao_abrem_transacao(self):
        for troca in (
            {"simulada": True},
            {"simulada": "false"},
            {"precisao_m": True},
        ):
            with self.subTest(troca=troca):
                dados = self.dados()
                dados.update(troca)

                self.assertIn(
                    self.enviar(dados).status_code,
                    (400, 403),
                )

        self.assertEqual(self.conn.inicios, 0)

    def test_precos_invalidos_nao_abrem_transacao(self):
        for preco in (
            True,
            "NaN",
            "Infinity",
            "6.199",
            "0",
            "25.01",
        ):
            with self.subTest(preco=preco):
                dados = self.dados()
                dados["itens"][1]["preco"] = preco

                self.assertEqual(
                    self.enviar(dados).status_code,
                    400,
                )

        self.assertEqual(self.conn.inicios, 0)

    def test_lote_vazio_duplicado_ou_foto_invalida_nao_grava(self):
        for itens in (
            [],
            [self.dados()["itens"][0]] * 2,
            [
                {
                    "tipo_combustivel": "Etanol",
                    "preco": "4.29",
                    "foto_url": "https://exemplo.invalid/foto.jpg",
                }
            ],
        ):
            with self.subTest(itens=itens):
                dados = self.dados()
                dados["itens"] = itens

                self.assertEqual(
                    self.enviar(dados).status_code,
                    400,
                )

        self.sem_gravacao()

    def test_tipo_do_posto_continua_sendo_respeitado(self):
        self.conn.posto["tipo_posto"] = "Eletroposto"

        self.assertEqual(self.enviar().status_code, 400)
        self.sem_gravacao()

        dados = self.dados()
        dados["itens"] = [
            {
                "tipo_combustivel": "Recarga Elétrica (kWh)",
                "preco": "2.50",
            }
        ]

        self.assertEqual(self.enviar(dados).status_code, 201)

    def test_conta_e_posto_ausentes(self):
        self.conn.usuario = False
        self.assertEqual(self.enviar().status_code, 401)

        self.conn.usuario = True
        self.conn.posto = None
        self.assertEqual(self.enviar().status_code, 404)

        self.sem_gravacao()

    def test_limite_de_corpo_antes_da_transacao(self):
        dados = self.dados()
        dados["extra"] = "x" * 17000

        self.assertEqual(self.enviar(dados).status_code, 413)
        self.assertEqual(self.conn.inicios, 0)


if __name__ == "__main__":
    unittest.main()