"""Autorização real das rotas com banco simulado, sem rede nem TiDB."""
import copy
import io
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, Mock

import jwt
from flask import Flask

from app.rotas import precos, postos, ia
from test_precos_lote import Conexao


class PrecosAdminTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask("precos_admin_testes")
        cls.app.config.update(
            TESTING=True,
            SECRET_KEY=(
                "chave-sintetica-de-teste-administrativo-sem-uso-real"
            ),
        )

        cls.app.register_blueprint(
            precos.precos_bp,
            url_prefix="/precos",
        )
        cls.app.register_blueprint(
            postos.postos_bp,
            url_prefix="/postos",
        )
        cls.app.register_blueprint(
            ia.ia_bp,
            url_prefix="/ia",
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
        self.conn.salvo["karma"] = 37
        self.conn.trabalho = copy.deepcopy(self.conn.salvo)
        self.client = self.app.test_client()

        for remendo in (
            patch.dict(
                os.environ,
                {"ADMIN_USUARIO_IDS": "7"},
            ),
            patch.object(
                precos,
                "get_db_connection",
                return_value=self.conn,
            ),
            patch(
                "app.utils.decorator.get_db_connection",
                return_value=Conexao(),
            ),
            patch.object(
                precos,
                "COOLDOWN_MINUTOS",
                15,
            ),
        ):
            remendo.start()
            self.addCleanup(remendo.stop)

    def pedido(self, lote=False, gps=False):
        itens = [
            {
                "tipo_combustivel": "Gasolina Comum",
                "preco": "6.19",
            },
            {
                "tipo_combustivel": "Etanol",
                "preco": "4.29",
            },
        ]

        dados = {
            "posto_id": 11,
            **({"itens": itens} if lote else itens[0]),
        }

        if gps:
            dados.update(
                latitude=-7.115,
                longitude=-34.861,
                precisao_m=10,
                simulada=False,
            )

        return dados

    def enviar(self, lote=False, dados=None, rota=None):
        return self.client.post(
            rota or (
                "/precos/lote" if lote else "/precos"
            ),
            json=(
                self.pedido(lote)
                if dados is None
                else dados
            ),
            headers={
                "Authorization": "Bearer " + self.token,
            },
        )

    def corpo(self, resposta):
        dados = resposta.get_json()
        self.assertIsInstance(dados, dict)

        if not isinstance(dados, dict):
            raise AssertionError(
                "Resposta JSON não é objeto"
            )

        return dados

    def sem_pontos(self, quantidade):
        salvo = self.conn.salvo

        self.assertEqual(salvo["karma"], 37)
        self.assertEqual(salvo["historico"], [])
        self.assertEqual(
            len(salvo["precos"]),
            quantidade,
        )
        self.assertEqual(
            len(salvo["eventos"]),
            quantidade,
        )

        self.assertFalse(any(
            "update usuarios set karma" in q
            or "insert into historico_karma" in q
            for q, _ in self.conn.consultas
        ))

    def test_permissoes_exigem_token(self):
        resposta = self.client.get(
            "/precos/permissoes"
        )
        self.assertEqual(resposta.status_code, 401)

    def test_permissoes_admin_e_comum_sem_cache(self):
        for configuracao, admin in (
            ("7", True),
            ("9", False),
            ("", False),
        ):
            with (
                self.subTest(configuracao=configuracao),
                patch.dict(
                    os.environ,
                    {"ADMIN_USUARIO_IDS": configuracao},
                ),
            ):
                resposta = self.client.get(
                    "/precos/permissoes",
                    headers={
                        "Authorization": (
                            "Bearer " + self.token
                        ),
                    },
                )

                self.assertEqual(
                    self.corpo(resposta),
                    {
                        "administrativo": admin,
                        "exige_gps": not admin,
                        "karma_por_preco": (
                            0 if admin else 5
                        ),
                    },
                )
                self.assertEqual(
                    resposta.headers["Cache-Control"],
                    "no-store",
                )

    def test_individual_sem_gps_e_sem_pontos_preserva_autoria_evento_e_saldo(self):
        with (
            patch(
                "services.precos_lote.validar_proximidade",
                side_effect=AssertionError(
                    "GPS não deve ser chamado"
                ),
            ),
            patch.object(
                precos,
                "registrar_karma",
                side_effect=AssertionError(
                    "Não conceder pontos"
                ),
            ),
        ):
            resposta = self.enviar()

        self.assertEqual(resposta.status_code, 201)

        dados = self.corpo(resposta)

        self.assertEqual(dados["karma_ganho"], 0)
        self.assertTrue(dados["administrativo"])
        self.assertIsNone(
            dados["distancia_verificada_metros"]
        )
        self.assertNotIn("+5", dados["message"])
        self.assertEqual(
            self.conn.salvo["precos"][0][1],
            7,
        )

        self.sem_pontos(1)

    def test_lote_sem_gps_tem_zero_por_item_e_no_total(self):
        with patch(
            "services.precos_lote.validar_proximidade",
            side_effect=AssertionError("GPS indevido"),
        ):
            resposta = self.enviar(lote=True)

        self.assertEqual(resposta.status_code, 201)

        dados = self.corpo(resposta)

        self.assertEqual(dados["karma_ganho"], 0)
        self.assertTrue(all(
            item["karma_ganho"] == 0
            for item in dados["registros"]
        ))
        self.assertIsNone(
            dados["distancia_verificada_metros"]
        )

        self.sem_pontos(2)

    def test_gps_distante_impreciso_ou_simulado_nao_e_requisito_do_admin(self):
        for lote in (False, True):
            with self.subTest(lote=lote):
                self.conn.recentes.clear()
                self.conn.salvo["precos"].clear()

                dados = self.pedido(lote)
                dados.update(
                    latitude=40,
                    longitude=50,
                    precisao_m=99999,
                    simulada=True,
                )

                self.assertEqual(
                    self.enviar(lote, dados).status_code,
                    201,
                )

    def test_alias_por_posto_tambem_aplica_politica(self):
        resposta = self.enviar(
            rota="/postos/11/precos"
        )

        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(
            self.corpo(resposta)["karma_ganho"],
            0,
        )
        self.sem_pontos(1)

    def test_alias_recusa_posto_divergente(self):
        resposta = self.enviar(
            rota="/postos/12/precos"
        )

        self.assertEqual(resposta.status_code, 400)
        self.sem_pontos(0)

    def test_comum_nao_ganha_privilegio_por_campos_no_json(self):
        with patch.dict(
            os.environ,
            {"ADMIN_USUARIO_IDS": "9"},
        ):
            for lote in (False, True):
                dados = self.pedido(lote)

                dados.update(
                    admin=True,
                    administrativo=True,
                    exige_gps=False,
                    karma_ganho=0,
                    usuario_id=9,
                )

                self.assertIn(
                    self.enviar(lote, dados).status_code,
                    (400, 403),
                )

        self.sem_pontos(0)

    def test_comum_mantem_gps_e_pontuacao(self):
        with patch.dict(
            os.environ,
            {"ADMIN_USUARIO_IDS": ""},
        ):
            resposta = self.enviar(
                dados=self.pedido(gps=True)
            )

        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(
            self.corpo(resposta)["karma_ganho"],
            5,
        )
        self.assertFalse(
            self.corpo(resposta)["administrativo"]
        )
        self.assertEqual(
            self.conn.salvo["karma"],
            42,
        )
        self.assertEqual(
            len(self.conn.salvo["historico"]),
            1,
        )

    def test_revogacao_depois_da_consulta_nao_dispensa_gps(self):
        resposta = self.client.get(
            "/precos/permissoes",
            headers={
                "Authorization": "Bearer " + self.token,
            },
        )

        self.assertTrue(
            self.corpo(resposta)["administrativo"]
        )

        with patch.dict(
            os.environ,
            {"ADMIN_USUARIO_IDS": ""},
        ):
            self.assertIn(
                self.enviar(lote=True).status_code,
                (400, 403),
            )

        self.sem_pontos(0)

    def test_configuracao_invalida_falha_fechada(self):
        with patch.dict(
            os.environ,
            {"ADMIN_USUARIO_IDS": "7,invalido"},
        ):
            for lote in (False, True):
                self.assertEqual(
                    self.enviar(lote).status_code,
                    503,
                )

            resposta = self.client.get(
                "/precos/permissoes",
                headers={
                    "Authorization": (
                        "Bearer " + self.token
                    ),
                },
            )
            self.assertEqual(
                resposta.status_code,
                503,
            )

        self.assertEqual(self.conn.inicios, 0)

    def test_produto_indisponivel_ou_recarga_nao_confirmada_continua_bloqueado(self):
        self.conn.ofertas["etanol"] = 0

        self.assertEqual(
            self.enviar(lote=True).status_code,
            409,
        )

        dados = self.pedido()
        dados["tipo_combustivel"] = (
            "Recarga Elétrica (kWh)"
        )

        self.assertEqual(
            self.enviar(dados=dados).status_code,
            400,
        )

        self.sem_pontos(0)

    def test_precos_invalidos_nao_abrem_transacao(self):
        for valor in (
            True,
            "NaN",
            "Infinity",
            "4.299",
            "0",
            "25.01",
        ):
            dados = self.pedido()
            dados["preco"] = valor

            self.assertEqual(
                self.enviar(dados=dados).status_code,
                400,
            )

        self.assertEqual(self.conn.inicios, 0)

    def test_repeticao_mantem_cooldown_sem_novos_registros(self):
        self.assertEqual(
            self.enviar(lote=True).status_code,
            201,
        )

        salvo = copy.deepcopy(self.conn.salvo)

        self.assertEqual(
            self.enviar(lote=True).status_code,
            429,
        )
        self.assertEqual(self.conn.salvo, salvo)

    def test_falha_no_segundo_preco_reverte_lote_e_eventos(self):
        with patch.object(
            self.conn,
            "falhar_no_insert",
            2,
        ):
            self.assertEqual(
                self.enviar(lote=True).status_code,
                500,
            )

        self.sem_pontos(0)
        self.assertEqual(self.conn.rollbacks, 1)

    def test_falha_no_evento_reverte_preco(self):
        self.conn.falhar_evento = True

        self.assertEqual(
            self.enviar().status_code,
            500,
        )

        self.sem_pontos(0)

    def test_commit_incerto_nao_repete_nem_alega_ausencia_de_gravacao(self):
        self.conn.commit_incerto = True

        resposta = self.enviar(lote=True)

        self.assertEqual(resposta.status_code, 500)
        self.assertIn(
            "atividade",
            self.corpo(resposta)["error"],
        )

        self.sem_pontos(2)
        self.assertEqual(self.conn.commits, 1)

    def test_ausencia_da_conta_ou_posto_impede_envio(self):
        self.conn.usuario = False

        self.assertEqual(
            self.enviar().status_code,
            401,
        )

        self.conn.usuario = True

        with patch.object(self.conn, "posto", None):
            self.assertEqual(
                self.enviar(lote=True).status_code,
                404,
            )

        self.sem_pontos(0)

    def ler_foto(self):
        return self.client.post(
            "/ia/ler-totem",
            data={
                "posto_id": "11",
                "foto": (
                    io.BytesIO(b"imagem-simulada"),
                    "totem.jpg",
                ),
            },
            headers={
                "Authorization": "Bearer " + self.token,
            },
        )

    def test_foto_admin_sem_gps_devolve_sugestoes_sem_cadastrar(self):
        cliente = Mock()
        cliente.models.generate_content.return_value.text = (
            '{"Gasolina Comum": 6.19}'
        )

        with (
            patch.object(
                ia,
                "_carregar_posto",
                return_value=self.conn.posto,
            ),
            patch.object(
                ia,
                "_preparar_imagem",
                return_value=b"jpeg",
            ),
            patch.object(
                ia,
                "_excedeu_limite",
                return_value=False,
            ),
            patch.object(
                ia,
                "_cliente",
                return_value=cliente,
            ),
            patch.object(
                ia,
                "validar_proximidade",
                side_effect=AssertionError("GPS indevido"),
            ),
            patch.object(
                ia,
                "upload_foto_totem",
                side_effect=AssertionError(
                    "Sem consentimento"
                ),
            ),
        ):
            resposta = self.ler_foto()

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            self.corpo(resposta)["precos"],
            {"Gasolina Comum": 6.19},
        )

        self.sem_pontos(0)

    def test_foto_comum_sem_gps_nao_chama_ia(self):
        with (
            patch.dict(
                os.environ,
                {"ADMIN_USUARIO_IDS": ""},
            ),
            patch.object(
                ia,
                "_carregar_posto",
                return_value=self.conn.posto,
            ),
            patch.object(
                ia,
                "_cliente",
                side_effect=AssertionError("IA indevida"),
            ),
        ):
            self.assertEqual(
                self.ler_foto().status_code,
                400,
            )

        self.sem_pontos(0)

    def test_foto_admin_mantem_limite_de_uso_da_ia(self):
        with (
            patch.object(
                ia,
                "_carregar_posto",
                return_value=self.conn.posto,
            ),
            patch.object(
                ia,
                "_preparar_imagem",
                return_value=b"jpeg",
            ),
            patch.object(
                ia,
                "_excedeu_limite",
                return_value=True,
            ),
            patch.object(
                ia,
                "_cliente",
                side_effect=AssertionError(
                    "Limite não respeitado"
                ),
            ),
        ):
            self.assertEqual(
                self.ler_foto().status_code,
                429,
            )

        self.sem_pontos(0)


if __name__ == "__main__":
    unittest.main()