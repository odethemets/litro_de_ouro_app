"""Executar manualmente apenas no banco descartável nomeado abaixo.

Cria o schema vazio e dados sintéticos. Nunca usa o banco de desenvolvimento.
DB_NAME=ldo_validacao_20261113_01 python -B tests/integracao_participacao.py
"""
import os
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jwt
from app import create_app
from services.database import get_db_connection
from services.migrations import load_migrations, run, split_sql
from services.atividade_alertas import processar_pendentes
from werkzeug.security import generate_password_hash

BANCO = "ldo_validacao_20261113_01"


class IntegracaoParticipacao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("DB_NAME") != BANCO or os.environ.get("DATABASE_URL"):
            raise RuntimeError("Este teste exige o banco descartável explícito")
        cls.conn = get_db_connection()
        with cls.conn.cursor() as c:
            c.execute("SELECT DATABASE() AS banco")
            if c.fetchone()["banco"] != BANCO:
                raise RuntimeError("Destino recusado")
            c.execute("SHOW TABLES")
            if c.fetchall():
                raise RuntimeError("O banco descartável deve estar vazio")
            for sql in split_sql((ROOT / "docker/schema_base.sql").read_text()):
                c.execute(sql)
        cls.conn.commit()
        run(cls.conn, load_migrations(ROOT / "migrations"), apply=True, expected_database=BANCO)
        cls.app = create_app()
        cls.app.config["TESTING"] = True

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def setUp(self):
        self.client = self.app.test_client()
        # IDs únicos por cenário; não se apagam registros entre testes.
        with self.conn.cursor() as c:
            self.usuarios = []
            for indice in range(3):
                email = f"{self._testMethodName}-{indice}@example.invalid"
                c.execute("INSERT INTO usuarios (nome,email,email_verificado) VALUES ('Pessoa de teste',%s,1)", (email,))
                self.usuarios.append(c.lastrowid)
            c.execute("INSERT INTO postos (nome,latitude,longitude,tipo_posto) VALUES ('[TESTE] Participação',-7.11,-34.86,'Convencional')")
            self.posto = c.lastrowid
        self.conn.commit()

    def headers(self, indice=0):
        token = jwt.encode({"usuario_id": self.usuarios[indice], "ver": 0,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10)}, self.app.config["SECRET_KEY"], algorithm="HS256")
        return {"Authorization": "Bearer " + token}

    def sql(self, sql, args=()):
        self.conn.rollback()
        with self.conn.cursor() as c:
            c.execute(sql, args)
            rows = list(c.fetchall()) if c.description else []
        self.conn.commit()
        return rows

    def registrar(self, preco="5.89"):
        with patch("app.rotas.precos.COOLDOWN_MINUTOS", 0):
            r = self.client.post("/precos", headers=self.headers(), json={"posto_id": self.posto,
                "tipo_combustivel": "Gasolina Comum", "preco": preco,
                "latitude": -7.11, "longitude": -34.86, "precisao_m": 10, "simulada": False})
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()["registo_id"]

    def voto(self, registo, tipo, indice=1):
        return self.client.post(f"/precos/{registo}/votar", headers=self.headers(indice), json={"voto": tipo})

    def oferta(self, **extra):
        dados = dict(confirmado=True, latitude=-7.11, longitude=-34.86, precisao_m=10, simulada=False)
        dados.update(extra)
        return self.client.post(f"/postos/{self.posto}/ofertas/gnv/confirmar", headers=self.headers(), json=dados)

    def test_oferta_idempotente_nao_altera_preco_karma(self):
        registo = self.registrar()
        antes = self.sql("SELECT * FROM registos_preco WHERE id=%s", (registo,))
        self.assertEqual(self.oferta().status_code, 200)
        auditoria = self.sql("SELECT * FROM postos_combustiveis WHERE posto_id=%s", (self.posto,))
        self.assertEqual(self.oferta().status_code, 200)
        self.assertEqual(self.sql("SELECT * FROM postos_combustiveis WHERE posto_id=%s", (self.posto,)), auditoria)
        self.assertEqual(self.sql("SELECT * FROM registos_preco WHERE id=%s", (registo,)), antes)
        self.assertEqual(self.sql("SELECT karma FROM usuarios WHERE id=%s", (self.usuarios[0],))[0]["karma"], 5)
        resposta = self.client.get("/postos?combustiveis=gnv").get_json()
        self.assertIn(self.posto, [p["id"] for p in resposta])

    def test_oferta_preserva_negativa_e_origem_osm(self):
        self.sql("INSERT INTO postos_combustiveis (posto_id,combustivel_codigo,disponivel_osm) VALUES (%s,'gnv',0)", (self.posto,))
        self.assertEqual(self.oferta().status_code, 409)
        self.sql("UPDATE postos_combustiveis SET disponivel_osm=1 WHERE posto_id=%s", (self.posto,))
        self.assertEqual(self.oferta().get_json()["origem"], "osm")
        self.assertIsNone(self.sql("SELECT disponivel_manual FROM postos_combustiveis WHERE posto_id=%s", (self.posto,))[0]["disponivel_manual"])

    def test_oferta_validacoes_e_autenticacao(self):
        self.assertEqual(self.oferta(confirmado=False).status_code, 400)
        self.assertEqual(self.oferta(simulada=True).status_code, 403)
        self.assertEqual(self.oferta(precisao_m=151).status_code, 422)
        self.assertEqual(self.oferta(precisao_m=True).status_code, 400)
        self.assertEqual(self.oferta(latitude=None).status_code, 400)
        self.assertEqual(self.oferta(latitude=-6).status_code, 403)
        self.assertEqual(self.client.post(f"/postos/{self.posto}/ofertas/gnv/confirmar", json={}).status_code, 401)
        self.assertEqual(self.sql("SELECT * FROM postos_combustiveis WHERE posto_id=%s", (self.posto,)), [])

    def test_preco_grava_evento_e_historico_atomicos(self):
        registo = self.registrar()
        h = self.sql("SELECT pontos,saldo_apos FROM historico_karma WHERE registo_id=%s", (registo,))
        self.assertEqual(h, [dict(pontos=5, saldo_apos=5)])
        self.assertIsNone(self.sql("SELECT preco_anterior FROM eventos_preco WHERE registo_id=%s", (registo,))[0]["preco_anterior"])
        segundo = self.registrar("5.69")
        self.assertEqual(float(self.sql("SELECT preco_anterior FROM eventos_preco WHERE registo_id=%s", (segundo,))[0]["preco_anterior"]), 5.89)
        produto = next(p for p in self.client.get("/postos").get_json() if p["id"] == self.posto)["combustiveis"][0]
        self.assertEqual(produto["registo_id"], segundo)
        with patch("app.rotas.precos.registrar_karma", side_effect=RuntimeError("falha simulada")):
            r = self.client.post("/precos", headers=self.headers(), json={"posto_id": self.posto,
                "tipo_combustivel": "Etanol", "preco": "4.00", "latitude": -7.11, "longitude": -34.86})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM registos_preco WHERE posto_id=%s", (self.posto,))[0]["n"], 2)

    def test_voto_proprio_repeticao_troca_e_retorno(self):
        registo = self.registrar()
        self.assertEqual(self.voto(registo, "positivo", 0).status_code, 400)
        for tipo, score, karma in [("positivo", 2, 7), ("positivo", 2, 7), ("negativo", 0, 3), ("negativo", 0, 3), ("positivo", 2, 7)]:
            r = self.voto(registo, tipo)
            self.assertEqual(r.status_code, 200, r.get_json())
            self.assertEqual(r.get_json()["confianca_score"], score)
            self.assertEqual(r.get_json()["meu_voto"], tipo)
            self.assertEqual(self.sql("SELECT karma FROM usuarios WHERE id=%s", (self.usuarios[0],))[0]["karma"], karma)
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM historico_karma WHERE registo_id=%s", (registo,))[0]["n"], 4)
        self.assertFalse(self.client.get(f"/precos/{registo}/votos", headers=self.headers()).get_json()["pode_votar"])

    def test_votos_concorrentes_mesma_conta_e_duas_contas(self):
        registo = self.registrar()
        def enviar(indice):
            with self.app.test_client() as cliente:
                r = cliente.post(f"/precos/{registo}/votar", headers=self.headers(indice), json={"voto": "positivo"})
                return r.status_code
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(list(pool.map(enviar, [1, 1, 2, 2])), [200]*4)
        r = self.client.get(f"/precos/{registo}/votos", headers=self.headers(1)).get_json()
        self.assertEqual((r["positivos"], r["negativos"], r["confianca_score"]), (2, 0, 3))
        self.assertEqual(self.sql("SELECT karma FROM usuarios WHERE id=%s", (self.usuarios[0],))[0]["karma"], 9)

    def test_votos_json_invalido_e_registro_inexistente(self):
        registo = self.registrar()
        for bruto in ([], 1, "x", None, {}, {"voto": True}):
            r = self.client.post(f"/precos/{registo}/votar", headers=self.headers(1), json=bruto)
            self.assertEqual(r.status_code, 400)
        self.assertEqual(self.voto(2147483647, "positivo").status_code, 404)
        self.assertEqual(self.client.get(f"/precos/{registo}/votos").status_code, 401)

    def test_voto_falha_reverte_pontos_score_e_voto(self):
        registo = self.registrar()
        with patch("app.rotas.votos.registrar_karma", side_effect=RuntimeError("falha simulada")):
            self.assertEqual(self.voto(registo, "positivo").status_code, 503)
        self.assertEqual(self.sql("SELECT * FROM votos_registos WHERE registo_id=%s", (registo,)), [])
        self.assertEqual(self.sql("SELECT confianca_score FROM registos_preco WHERE id=%s", (registo,))[0]["confianca_score"], 1)
        self.assertEqual(self.sql("SELECT karma FROM usuarios WHERE id=%s", (self.usuarios[0],))[0]["karma"], 5)

    def test_trocas_concorrentes_mesma_conta_mantem_saldo(self):
        registo = self.registrar()
        self.assertEqual(self.voto(registo, "positivo").status_code, 200)
        def enviar(tipo):
            with self.app.test_client() as cliente:
                return cliente.post(f"/precos/{registo}/votar", headers=self.headers(1), json={"voto": tipo}).status_code
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(list(pool.map(enviar, ["positivo", "negativo"] * 4)), [200] * 8)
        r = self.client.get(f"/precos/{registo}/votos", headers=self.headers(1)).get_json()
        self.assertEqual(r["positivos"] + r["negativos"], 1)
        self.assertEqual(r["confianca_score"], 1 + r["positivos"] - r["negativos"])
        karma = self.sql("SELECT karma FROM usuarios WHERE id=%s", (self.usuarios[0],))[0]["karma"]
        self.assertEqual(karma, 5 + 2 * (r["positivos"] - r["negativos"]))

    def test_oferta_concorrente_preserva_uma_auditoria(self):
        def confirmar(indice):
            with self.app.test_client() as cliente:
                return cliente.post(f"/postos/{self.posto}/ofertas/gnv/confirmar", headers=self.headers(indice),
                    json=dict(confirmado=True, latitude=-7.11, longitude=-34.86, precisao_m=10, simulada=False)).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(confirmar, [1, 2])), [200, 200])
        rows = self.sql("SELECT manual_atualizado_por FROM postos_combustiveis WHERE posto_id=%s", (self.posto,))
        self.assertEqual(len(rows), 1)
        self.assertIn(rows[0]["manual_atualizado_por"], self.usuarios[1:])

    def test_fila_favoritos_quedas_idempotencia_e_concorrencia(self):
        self.sql("INSERT INTO favoritos_postos (usuario_id,posto_id,criado_em) VALUES (%s,%s,UTC_TIMESTAMP())", (self.usuarios[1], self.posto))
        self.sql("INSERT INTO favoritos_combustiveis (usuario_id,combustivel_codigo,criado_em) VALUES (%s,'gasolina_comum',UTC_TIMESTAMP())", (self.usuarios[1],))
        self.sql("INSERT INTO preferencias_alertas (usuario_id,ativo,somente_quedas,intervalo_minutos) VALUES (%s,1,1,30)", (self.usuarios[1],))
        self.registrar("6.00")
        queda = self.registrar("5.80")
        self.registrar("5.90")
        self.registrar("5.70")  # outra queda dentro do intervalo
        def processar(_):
            conn = get_db_connection()
            try:
                return processar_pendentes(conn)
            finally:
                conn.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(processar, [1, 2]))
        rows = self.sql("SELECT registo_id,usuario_id FROM notificacoes WHERE posto_id=%s", (self.posto,))
        self.assertEqual(rows, [dict(registo_id=queda, usuario_id=self.usuarios[1])])
        self.assertEqual(processar(0), 0)
        r = self.client.get("/notificacoes", headers=self.headers(1)).get_json()
        aviso = r["itens"][0]
        self.assertEqual(self.client.put(f'/notificacoes/{aviso["id"]}/lida', headers=self.headers(2)).status_code, 404)
        self.assertEqual(self.client.put(f'/notificacoes/{aviso["id"]}/lida', headers=self.headers(1)).status_code, 200)

    def test_conta_nome_favoritos_preferencias_e_exclusao(self):
        senha = "Senha-sintetica-exclusiva-do-teste-123"
        self.sql("UPDATE usuarios SET senha=%s WHERE id=%s", (generate_password_hash(senha), self.usuarios[0]))
        r = self.client.patch("/conta/nome", headers=self.headers(), json={"nome": "Nome revisado"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.sql("SELECT nome FROM usuarios WHERE id=%s", (self.usuarios[0],))[0]["nome"], "Nome revisado")
        caminho = f"/favoritos/postos/{self.posto}"
        for _ in range(2):
            self.assertEqual(self.client.put(caminho, headers=self.headers()).status_code, 200)
        preferencias = dict(combustiveis=["gnv"], ativo=True, somente_quedas=True, intervalo_minutos=15)
        self.assertEqual(self.client.put("/favoritos/preferencias", headers=self.headers(), json=preferencias).status_code, 200)
        f = self.client.get("/favoritos", headers=self.headers()).get_json()
        self.assertEqual(f["postos"], [self.posto])
        self.assertEqual(f["combustiveis"], ["gnv"])
        self.assertEqual(f["alertas"]["intervalo_minutos"], 15)
        self.assertEqual(self.client.get("/favoritos", headers=self.headers(1)).get_json()["postos"], [])
        self.assertEqual(self.oferta().status_code, 200)
        self.registrar()
        self.assertEqual(self.client.delete("/conta", headers=self.headers(), json={"confirmacao": "APAGAR", "senha": "errada"}).status_code, 403)
        self.assertEqual(self.client.delete("/conta", headers=self.headers(), json={"confirmacao": "APAGAR", "senha": senha}).status_code, 200)
        self.assertEqual(self.client.get("/favoritos", headers=self.headers()).status_code, 401)
        self.assertEqual(self.sql("SELECT * FROM registos_preco WHERE posto_id=%s", (self.posto,)), [])
        oferta = self.sql("SELECT disponivel_manual,manual_atualizado_por FROM postos_combustiveis WHERE posto_id=%s", (self.posto,))[0]
        self.assertEqual(oferta["disponivel_manual"], 1)
        self.assertIsNone(oferta["manual_atualizado_por"])

    def test_fila_recupera_falha_sem_aviso_parcial(self):
        self.sql("INSERT INTO favoritos_postos (usuario_id,posto_id,criado_em) VALUES (%s,%s,UTC_TIMESTAMP())", (self.usuarios[1], self.posto))
        self.sql("INSERT INTO favoritos_combustiveis (usuario_id,combustivel_codigo,criado_em) VALUES (%s,'gasolina_comum',UTC_TIMESTAMP())", (self.usuarios[1],))
        self.sql("INSERT INTO preferencias_alertas (usuario_id,ativo,somente_quedas,intervalo_minutos) VALUES (%s,1,0,0)", (self.usuarios[1],))
        registo = self.registrar()
        real = self.conn
        class FalhaCommit:
            def cursor(self): return real.cursor()
            def commit(self): raise RuntimeError("Falha antes do commit")
            def rollback(self): real.rollback()
        with self.assertRaises(RuntimeError):
            processar_pendentes(FalhaCommit(), limite=1)
        self.assertIsNone(self.sql("SELECT processado_em FROM eventos_preco WHERE registo_id=%s", (registo,))[0]["processado_em"])
        self.assertEqual(self.sql("SELECT * FROM notificacoes WHERE registo_id=%s", (registo,)), [])
        processar_pendentes(self.conn)
        self.assertEqual(len(self.sql("SELECT id FROM notificacoes WHERE registo_id=%s", (registo,))), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
