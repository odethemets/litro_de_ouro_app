"""HTTP e transações com SQLite adaptado; nenhum acesso a TiDB/Dropbox/rede.

O adaptador só traduz o subconjunto usado nas rotas. Não substitui a
integração MySQL/TiDB fornecida separadamente para validar DDL e locks.
"""
from datetime import datetime, timedelta, timezone
import io
import os
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import unittest
from typing import Any
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jwt
from flask import Flask
from PIL import Image
from werkzeug.test import TestResponse

from app.rotas import servicos
from services import fotos_servicos
from services.servicos_postos import produto_compativel


class Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.rows: list[dict[str, Any]] = []
        self.lastrowid: int | None = 0
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows

    def execute(self, sql, params=None):
        n = " ".join(sql.split())
        self.conn.log.append((n, params))

        if self.conn.falha and self.conn.falha in n:
            raise sqlite3.OperationalError(
                "falha simulada sem dados privados"
            )

        if n == "SELECT VERSION() AS versao":
            self.rows = [{"versao": self.conn.versao}]
            return

        if n.startswith("SET SESSION"):
            return

        n = n.replace(" FOR UPDATE", "").replace("%s", "?")
        n = n.replace(
            "UTC_TIMESTAMP() - INTERVAL 1 DAY",
            "datetime('now','-1 day')",
        )
        n = n.replace("UTC_TIMESTAMP()", "datetime('now')")

        if "ON DUPLICATE KEY UPDATE" in n:
            n = n.split("ON DUPLICATE KEY UPDATE")[0] + """
                ON CONFLICT(posto_id,combustivel_codigo)
                DO UPDATE SET
                    disponivel_manual=1,
                    manual_atualizado_em=datetime('now'),
                    manual_atualizado_por=excluded.manual_atualizado_por
            """

        cur = self.conn.db.execute(n, params or ())
        self.lastrowid, self.rowcount = cur.lastrowid, cur.rowcount
        self.rows = [
            dict(r) for r in cur.fetchall()
        ] if cur.description else []


class Conexao:
    def __init__(self, db):
        self.db = db
        self.log: list[tuple[str, Any]] = []
        self.falha: str | None = None
        self.commit_perdido = False
        self.versao = "8.4.0"

    def cursor(self):
        return Cursor(self)

    def begin(self):
        self.db.execute("BEGIN")

    def rollback(self):
        self.db.rollback()

    def commit(self):
        self.db.commit()
        if self.commit_perdido:
            raise sqlite3.OperationalError(
                "resposta do commit perdida"
            )

    def close(self):
        pass


class SolicitacoesTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(
            ":memory:",
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA foreign_keys=ON;

            CREATE TABLE usuarios (
                id INTEGER PRIMARY KEY,
                versao_token INTEGER NOT NULL DEFAULT 0
            );

            INSERT INTO usuarios(id) VALUES (1),(2),(3),(4);

            CREATE TABLE postos (
                id INTEGER PRIMARY KEY,
                nome TEXT,
                endereco TEXT,
                latitude REAL,
                longitude REAL,
                tipo_posto TEXT
            );

            INSERT INTO postos VALUES (
                1,
                'Posto sintético',
                'Endereço de teste',
                -7.11,
                -34.86,
                'Convencional'
            );

            CREATE TABLE postos_combustiveis (
                posto_id INTEGER,
                combustivel_codigo TEXT,
                disponivel_manual INTEGER,
                disponivel_osm INTEGER,
                manual_atualizado_em TIMESTAMP,
                manual_atualizado_por INTEGER,
                PRIMARY KEY(posto_id,combustivel_codigo)
            );

            CREATE TABLE solicitacoes_servicos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER,
                posto_id INTEGER,
                combustivel_codigo TEXT,
                chave_cliente TEXT,
                foto_arquivo TEXT UNIQUE,
                foto_sha256 TEXT,
                observacao TEXT,
                distancia_m REAL,
                precisao_m REAL,
                estado TEXT,
                criado_em TIMESTAMP,
                revisado_em TIMESTAMP,
                revisado_por INTEGER,
                motivo TEXT,
                UNIQUE(usuario_id,chave_cliente)
            );
        """)

        self.conn = Conexao(self.db)
        self.app = Flask("solicitacoes_tests")
        self.app.config.update(
            TESTING=True,
            SECRET_KEY=secrets.token_hex(32),
        )
        self.app.register_blueprint(servicos.servicos_bp)
        self.client = self.app.test_client()
        self.storage = {}

        def guardar(jpeg):
            nome = secrets.token_hex(16) + ".jpg"
            self.storage[nome] = jpeg
            return nome

        self.mock_guardar = MagicMock(side_effect=guardar)
        self.mock_ler = MagicMock(
            side_effect=lambda nome: self.storage[nome]
        )
        self.mock_remover = MagicMock(return_value=True)

        self.patches = [
            patch.dict(
                os.environ,
                {"ADMIN_USUARIO_IDS": "2,3"},
            ),
            patch(
                "app.utils.decorator.get_db_connection",
                return_value=self.conn,
            ),
            patch.object(
                servicos,
                "get_db_connection",
                return_value=self.conn,
            ),
            patch.object(
                fotos_servicos,
                "guardar",
                new=self.mock_guardar,
            ),
            patch.object(
                fotos_servicos,
                "ler",
                new=self.mock_ler,
            ),
            patch.object(
                fotos_servicos,
                "remover",
                new=self.mock_remover,
            ),
        ]
        self.mocks = [p.start() for p in self.patches]

        imagem = Image.new("RGB", (20, 20), "blue")
        f = io.BytesIO()
        imagem.save(f, format="JPEG")
        imagem.close()
        self.jpeg = f.getvalue()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.db.close()

    def corpo(self, resposta: TestResponse) -> dict[str, Any]:
        dados = resposta.get_json()
        if not isinstance(dados, dict):
            raise AssertionError(
                "A resposta da API deve conter um objeto JSON."
            )
        return dados

    def headers(self, usuario=1):
        token = jwt.encode(
            {
                "usuario_id": usuario,
                "ver": 0,
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            self.app.config["SECRET_KEY"],
            algorithm="HS256",
        )
        return {"Authorization": "Bearer " + token}

    def enviar(self, usuario=1, **extras):
        dados = dict(
            codigo="recarga_eletrica",
            chave_cliente="a" * 32,
            observacao="Carregador visível junto ao posto",
            consentimento="true",
            presenca_observada="true",
            simulada="false",
            latitude="-7.11",
            longitude="-34.86",
            precisao_m="15",
            foto=(io.BytesIO(self.jpeg), "evidencia.jpg"),
        )
        dados.update(extras)
        return self.client.post(
            "/postos/1/servicos/solicitacoes",
            data=dados,
            headers=self.headers(usuario),
        )

    def decidir(self, id=1, usuario=2, **extras):
        dados = dict(
            decisao="aprovar",
            motivo="Foto compatível com o serviço e o posto",
            foto_revisada=True,
        )
        dados.update(extras)
        return self.client.post(
            f"/admin/servicos/solicitacoes/{id}/decidir",
            json=dados,
            headers=self.headers(usuario),
        )

    def test_solicitacao_pendente_nao_libera_oferta_preco_ou_karma(self):
        r = self.enviar()
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.corpo(r)["estado"], "pendente")
        self.assertIsNone(self.corpo(r)["revisado_em"])
        self.assertTrue(self.corpo(r)["criado_em"].endswith("Z"))
        self.assertEqual(
            self.db.execute(
                "SELECT COUNT(*) FROM postos_combustiveis"
            ).fetchone()[0],
            0,
        )
        self.assertNotRegex(
            str(self.corpo(r)),
            "foto_arquivo|foto_sha256|chave_cliente|usuario_id|Bearer",
        )
        self.assertFalse(
            any(
                re.search(
                    r"INSERT INTO (registos_preco|historico_karma|eventos_preco)",
                    sql,
                )
                for sql, _ in self.conn.log
            )
        )

    def test_aprovacao_confirma_recarga_sem_mudar_tipo_do_posto(self):
        self.enviar()
        r = self.decidir()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.corpo(r)["estado"], "aprovada")
        o = self.db.execute(
            "SELECT * FROM postos_combustiveis"
        ).fetchone()
        self.assertEqual(
            (o["disponivel_manual"], o["manual_atualizado_por"]),
            (1, 2),
        )
        self.assertEqual(
            self.db.execute(
                "SELECT tipo_posto FROM postos"
            ).fetchone()[0],
            "Convencional",
        )

    def test_rejeicao_exige_motivo_e_nao_muda_oferta(self):
        self.enviar()
        self.assertEqual(
            self.decidir(decisao="rejeitar", motivo=" ").status_code,
            400,
        )
        r = self.decidir(
            decisao="rejeitar",
            motivo="Não identifica o posto",
            foto_revisada=False,
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.corpo(r)["estado"], "rejeitada")
        self.assertEqual(
            self.db.execute(
                "SELECT COUNT(*) FROM postos_combustiveis"
            ).fetchone()[0],
            0,
        )

    def test_admin_nao_pode_revisar_a_propria_solicitacao(self):
        self.enviar(usuario=2)
        r = self.decidir(usuario=2)
        self.assertEqual(
            (r.status_code, self.corpo(r)["codigo"]),
            (409, "REVISAO_PROPRIA"),
        )
        self.assertEqual(self.decidir(usuario=3).status_code, 200)

    def test_sem_login_e_sem_admin_nao_acessam_foto_lista_ou_decisao(self):
        self.assertEqual(
            self.client.get("/admin/servicos/solicitacoes").status_code,
            401,
        )
        self.enviar()
        for url in [
            "/admin/servicos/solicitacoes",
            "/admin/servicos/solicitacoes/1/foto",
        ]:
            self.assertEqual(
                self.client.get(url, headers=self.headers()).status_code,
                403,
            )
        self.assertEqual(self.decidir(usuario=1).status_code, 403)
        self.mock_ler.assert_not_called()

    def test_corpo_nao_concede_privilegio_e_configuracao_invalida_falha_fechada(self):
        comum = self.client.get(
            "/admin/servicos/acesso",
            headers=self.headers(),
        )
        admin = self.client.get(
            "/admin/servicos/acesso",
            headers=self.headers(2),
        )
        self.assertFalse(self.corpo(comum)["pode_moderar"])
        self.assertTrue(self.corpo(admin)["pode_moderar"])
        with patch.dict(os.environ, {"ADMIN_USUARIO_IDS": "2,errado"}):
            self.assertEqual(
                self.client.get(
                    "/admin/servicos/acesso",
                    headers=self.headers(2),
                ).status_code,
                503,
            )

    def test_retry_mesma_chave_e_payload_nao_sobe_ou_insere_outra_foto(self):
        a = self.enviar()
        b = self.enviar()
        self.assertEqual(
            (
                a.status_code,
                b.status_code,
                self.corpo(a)["id"],
                self.corpo(b)["id"],
            ),
            (201, 200, 1, 1),
        )
        self.mock_guardar.assert_called_once()
        self.assertEqual(
            self.enviar(observacao="Outra descrição").status_code,
            409,
        )

    def test_outra_chave_nao_cria_duas_pendencias_do_mesmo_produto(self):
        self.enviar()
        self.assertEqual(
            self.corpo(
                self.enviar(chave_cliente="b" * 32)
            )["codigo"],
            "SOLICITACAO_PENDENTE",
        )
        self.mock_guardar.assert_called_once()

    def test_decisao_repetida_e_conflitante_nao_alteram_auditoria(self):
        self.enviar()
        a = self.decidir()
        b = self.decidir()
        self.assertEqual((a.status_code, b.status_code), (200, 200))
        self.assertEqual(
            self.corpo(a)["revisado_em"],
            self.corpo(b)["revisado_em"],
        )
        self.assertEqual(self.decidir(usuario=3).status_code, 409)
        self.assertEqual(
            self.decidir(decisao="rejeitar").status_code,
            409,
        )

    def test_falha_na_decisao_reverte_oferta_e_estado_juntos(self):
        self.enviar()
        self.conn.falha = "UPDATE solicitacoes_servicos SET estado="
        self.assertEqual(self.decidir().status_code, 503)
        self.assertEqual(
            self.db.execute(
                "SELECT estado FROM solicitacoes_servicos"
            ).fetchone()[0],
            "pendente",
        )
        self.assertEqual(
            self.db.execute(
                "SELECT COUNT(*) FROM postos_combustiveis"
            ).fetchone()[0],
            0,
        )

    def test_commit_perdido_preserva_evidencia_e_retry_recupera_solicitacao(self):
        self.conn.commit_perdido = True
        r = self.enviar()
        self.assertEqual(
            (r.status_code, self.corpo(r)["codigo"]),
            (503, "RESULTADO_INCERTO"),
        )
        self.mock_remover.assert_not_called()
        self.conn.commit_perdido = False
        self.assertEqual(self.enviar().status_code, 200)
        self.mock_guardar.assert_called_once()

    def test_commit_perdido_da_revisao_nao_repete_mutacao(self):
        self.enviar()
        self.conn.commit_perdido = True
        self.assertEqual(
            self.corpo(self.decidir())["codigo"],
            "RESULTADO_INCERTO",
        )
        self.conn.commit_perdido = False
        self.assertEqual(
            self.corpo(self.decidir())["estado"],
            "aprovada",
        )

    def test_falha_antes_do_commit_remove_foto_sem_registro(self):
        self.conn.falha = "INSERT INTO solicitacoes_servicos"
        self.assertEqual(self.enviar().status_code, 503)
        self.mock_remover.assert_called_once()
        self.assertEqual(
            self.db.execute(
                "SELECT COUNT(*) FROM solicitacoes_servicos"
            ).fetchone()[0],
            0,
        )

    def test_foto_privada_so_sai_em_rota_admin_sem_cache(self):
        self.enviar()
        r = self.client.get(
            "/admin/servicos/solicitacoes/1/foto",
            headers=self.headers(2),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.corpo(r)["mime"], "image/jpeg")
        self.assertEqual(r.headers["Cache-Control"], "no-store")
        self.assertNotIn("http", str(self.corpo(r)))

    def test_foto_alterada_no_storage_nao_chega_a_revisao(self):
        self.enviar()
        for nome in self.storage:
            self.storage[nome] = b"\xff\xd8\xff\xd9"
        r = self.client.get(
            "/admin/servicos/solicitacoes/1/foto",
            headers=self.headers(2),
        )
        self.assertEqual(r.status_code, 503)
        self.assertNotIn("base64", self.corpo(r))

    def test_minhas_nao_expoe_solicitacao_de_outra_conta(self):
        self.enviar()
        minhas = self.client.get(
            "/servicos/solicitacoes/minhas",
            headers=self.headers(),
        )
        outra_conta = self.client.get(
            "/servicos/solicitacoes/minhas",
            headers=self.headers(4),
        )
        admin = self.client.get(
            "/admin/servicos/solicitacoes",
            headers=self.headers(2),
        )
        self.assertEqual(len(self.corpo(minhas)["itens"]), 1)
        self.assertEqual(self.corpo(outra_conta)["itens"], [])
        self.assertTrue(self.corpo(admin)["itens"][0]["pode_revisar"])

    def test_formato_gps_consentimento_e_foto_invalidos_nao_fazem_upload(self):
        for extra in [
            dict(consentimento="false"),
            dict(presenca_observada="false"),
            dict(simulada="true"),
            dict(precisao_m="151"),
            dict(latitude="-6.11"),
            dict(codigo="glp"),
            dict(chave_cliente="inválida"),
            dict(foto=(io.BytesIO(b"texto"), "foto.jpg")),
        ]:
            with self.subTest(extra=tuple(extra)):
                self.assertGreaterEqual(
                    self.enviar(**extra).status_code,
                    400,
                )
        self.mock_guardar.assert_not_called()

    def test_limite_de_corpo_antes_de_ler_arquivo(self):
        r = self.client.post(
            "/postos/1/servicos/solicitacoes",
            data=b"x",
            headers=self.headers(),
            environ_overrides={
                "CONTENT_LENGTH": str(
                    servicos.MAX_BYTES + 512 * 1024 + 1
                ),
            },
        )
        self.assertEqual(r.status_code, 413)
        self.mock_guardar.assert_not_called()

    def test_limite_diario_antes_do_upload(self):
        for i in range(10):
            self.db.execute(
                """
                INSERT INTO solicitacoes_servicos
                    (usuario_id,posto_id,combustivel_codigo,
                     chave_cliente,foto_arquivo,estado,criado_em)
                VALUES (1,1,'gnv',?,?,'rejeitada',datetime('now'))
                """,
                (str(i), str(i)),
            )
        self.db.commit()
        self.assertEqual(self.enviar().status_code, 429)
        self.mock_guardar.assert_not_called()

    def test_solicitacao_antiga_nao_aprova_e_exige_nova_evidencia(self):
        self.enviar()
        self.db.execute(
            "UPDATE solicitacoes_servicos SET criado_em=?",
            (
                datetime.now(timezone.utc).replace(tzinfo=None)
                - timedelta(days=31),
            ),
        )
        self.db.commit()
        self.assertEqual(
            self.corpo(self.decidir())["codigo"],
            "EVIDENCIA_ANTIGA",
        )
        self.assertEqual(
            self.decidir(
                decisao="rejeitar",
                motivo="Envie foto atual",
            ).status_code,
            200,
        )

    def test_aprovacao_exige_foto_revisada_e_negativa_anterior_e_preservada_ate_aprovar(self):
        self.db.execute(
            "INSERT INTO postos_combustiveis "
            "VALUES (1,'recarga_eletrica',0,1,NULL,NULL)"
        )
        self.db.commit()
        self.enviar()
        self.assertEqual(
            self.decidir(foto_revisada=False).status_code,
            400,
        )
        self.assertEqual(
            self.db.execute(
                "SELECT disponivel_manual FROM postos_combustiveis"
            ).fetchone()[0],
            0,
        )
        self.assertEqual(self.decidir().status_code, 200)

    def test_servico_confirmado_nao_gera_nova_pendencia(self):
        self.db.execute(
            "INSERT INTO postos_combustiveis "
            "VALUES (1,'recarga_eletrica',NULL,1,NULL,NULL)"
        )
        self.db.commit()
        self.assertEqual(
            self.corpo(self.enviar())["codigo"],
            "OFERTA_CONFIRMADA",
        )
        self.mock_guardar.assert_not_called()

    def test_paginacao_e_validacao_de_filtros(self):
        for i in range(23):
            self.db.execute(
                """
                INSERT INTO solicitacoes_servicos
                    (usuario_id,posto_id,combustivel_codigo,
                     chave_cliente,foto_arquivo,foto_sha256,
                     observacao,distancia_m,precisao_m,estado,criado_em)
                VALUES (
                    1,1,'gnv',?,?,?,'Foto',0,10,
                    'pendente',datetime('now')
                )
                """,
                (str(i), str(i), str(i)),
            )
        self.db.commit()
        a = self.corpo(
            self.client.get(
                "/servicos/solicitacoes/minhas",
                headers=self.headers(),
            )
        )
        b = self.corpo(
            self.client.get(
                "/servicos/solicitacoes/minhas?antes_de="
                + str(a["antes_de"]),
                headers=self.headers(),
            )
        )
        self.assertEqual(
            (len(a["itens"]), len(b["itens"])),
            (20, 3),
        )
        self.assertFalse(
            {x["id"] for x in a["itens"]}
            & {x["id"] for x in b["itens"]}
        )
        for q in [
            "estado=outro",
            "antes_de=-1",
            "antes_de=NaN",
            "antes_de=2147483648",
        ]:
            self.assertEqual(
                self.client.get(
                    "/servicos/solicitacoes/minhas?" + q,
                    headers=self.headers(),
                ).status_code,
                400,
            )

    def test_tidb_usa_transacao_pessimista(self):
        self.conn.versao = "8.0.11-TiDB-v8.1.0"
        self.assertEqual(self.enviar().status_code, 201)
        self.assertTrue(
            any("tidb_txn_mode" in sql for sql, _ in self.conn.log)
        )

    def test_servidor_sem_resultado_nao_faz_upload(self):
        original = Cursor.fetchone

        def ler(cursor):
            if cursor.conn.log[-1][0] == "SELECT VERSION() AS versao":
                return None
            return original(cursor)

        with patch.object(Cursor, "fetchone", ler):
            self.assertEqual(self.enviar().status_code, 503)
        self.mock_guardar.assert_not_called()
        self.assertEqual(
            self.db.execute(
                "SELECT COUNT(*) FROM solicitacoes_servicos"
            ).fetchone()[0],
            0,
        )

    def test_contagem_sem_resultado_nao_faz_upload(self):
        original = Cursor.fetchone

        def ler(cursor):
            if cursor.conn.log[-1][0].startswith(
                "SELECT COUNT(*) AS total FROM solicitacoes_servicos"
            ):
                return None
            return original(cursor)

        with patch.object(Cursor, "fetchone", ler):
            self.assertEqual(self.enviar().status_code, 503)
        self.mock_guardar.assert_not_called()
        self.assertEqual(
            self.db.execute(
                "SELECT COUNT(*) FROM solicitacoes_servicos"
            ).fetchone()[0],
            0,
        )

    def test_leitura_ausente_apos_insert_reverte_e_limpa_foto(self):
        with patch.object(servicos, "_buscar", return_value=None):
            self.assertEqual(self.enviar().status_code, 503)
        self.assertEqual(
            self.db.execute(
                "SELECT COUNT(*) FROM solicitacoes_servicos"
            ).fetchone()[0],
            0,
        )
        self.mock_remover.assert_called_once()

    def test_solicitacao_ausente_na_releitura_nao_altera_oferta(self):
        self.enviar()
        original = servicos._buscar
        chamadas = 0

        def buscar(cursor, solicitacao_id):
            nonlocal chamadas
            chamadas += 1
            return None if chamadas == 2 else original(cursor, solicitacao_id)

        with patch.object(servicos, "_buscar", side_effect=buscar):
            self.assertEqual(self.decidir().status_code, 404)
        self.assertEqual(
            self.db.execute(
                "SELECT estado FROM solicitacoes_servicos"
            ).fetchone()[0],
            "pendente",
        )
        self.assertEqual(
            self.db.execute(
                "SELECT COUNT(*) FROM postos_combustiveis"
            ).fetchone()[0],
            0,
        )

    def test_leitura_ausente_apos_decisao_reverte_oferta_e_estado(self):
        self.enviar()
        original = servicos._buscar
        chamadas = 0

        def buscar(cursor, solicitacao_id):
            nonlocal chamadas
            chamadas += 1
            return None if chamadas == 3 else original(cursor, solicitacao_id)

        with patch.object(servicos, "_buscar", side_effect=buscar):
            resposta = self.decidir()
        self.assertEqual(
            (
                resposta.status_code,
                self.corpo(resposta)["codigo"],
            ),
            (503, "REVISAO_INDISPONIVEL"),
        )
        self.assertEqual(
            self.db.execute(
                "SELECT estado FROM solicitacoes_servicos"
            ).fetchone()[0],
            "pendente",
        )
        self.assertEqual(
            self.db.execute(
                "SELECT COUNT(*) FROM postos_combustiveis"
            ).fetchone()[0],
            0,
        )

    def test_produtos_conservam_unidades_e_posto_pode_ter_recarga_confirmada(self):
        self.assertFalse(
            produto_compativel("Convencional", "glp", 1)
        )
        self.assertFalse(
            produto_compativel("Convencional", "recarga_eletrica")
        )
        self.assertFalse(
            produto_compativel("Convencional", "recarga_eletrica", 0)
        )
        self.assertTrue(
            produto_compativel("Convencional", "recarga_eletrica", 1)
        )
        self.assertTrue(
            produto_compativel("Convencional", "gnv")
        )
        self.assertFalse(
            produto_compativel("Eletroposto", "diesel", 1)
        )
        self.assertTrue(
            produto_compativel("Eletroposto", "recarga_eletrica")
        )


if __name__ == "__main__":
    unittest.main()