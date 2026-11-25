"""Testes locais com SQLite sintético; nunca acessam TiDB."""

import copy
import csv
from datetime import date, datetime
from decimal import Decimal
import hashlib
import io
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services import referencias_medias as m
from services.migrations import (
    MigrationError,
    load_migrations,
)
from services.validacao_migracoes import (
    _column,
    _index,
)
from services.validacao_medias import (
    COLUNAS,
    validar_estrutura,
)
from services.catalogo_postos import (
    consultar_catalogo,
    validar_filtros,
)


def csv_snapshot():
    stream = io.StringIO(newline="")

    writer = csv.DictWriter(
        stream,
        fieldnames=sorted(m.CAMPOS),
    )
    writer.writeheader()

    for pid in (1, 2):
        for codigo, dados in m.MEDIAS.items():
            nome, unidade, _, _ = dados
            row = dict.fromkeys(m.CAMPOS, "")

            row.update(
                posto_id=str(pid),
                nome="Posto " + str(pid),
                tipo_posto="Convencional",
                cidade="João Pessoa",
                combustivel_codigo=codigo,
                combustivel_nome=nome,
                unidade=unidade,
            )
            writer.writerow(row)

    return stream.getvalue().encode("utf-8")


class Banco:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

        self.conn.executescript("""
        CREATE TABLE postos(
            id INTEGER PRIMARY KEY,
            nome TEXT,
            tipo_posto TEXT,
            cidade TEXT,
            uf TEXT,
            bairro TEXT,
            endereco TEXT,
            latitude NUMERIC,
            longitude NUMERIC,
            horario_funcionamento TEXT,
            marca TEXT,
            marca_origem TEXT
        );

        INSERT INTO postos(
            id,nome,tipo_posto,cidade,uf,latitude,longitude
        ) VALUES
            (1,'Posto 1','Convencional','João Pessoa','',-7.1,-34.8),
            (2,'Posto 2','Convencional','João Pessoa','',-7.2,-34.9);

        CREATE TABLE postos_combustiveis(
            posto_id INTEGER,
            combustivel_codigo TEXT,
            disponivel_manual INTEGER,
            disponivel_osm INTEGER
        );

        CREATE TABLE usuarios(
            id INTEGER PRIMARY KEY,
            nome TEXT
        );

        CREATE TABLE registos_preco(
            id INTEGER PRIMARY KEY,
            posto_id INTEGER,
            usuario_id INTEGER,
            tipo_combustivel TEXT,
            preco NUMERIC,
            data_registro TEXT
        );

        CREATE TABLE referencias_medias_iniciais(
            posto_id INTEGER,
            combustivel_codigo TEXT,
            preco NUMERIC,
            municipio_referencia TEXT,
            uf_referencia TEXT,
            periodo_inicio TEXT,
            periodo_fim TEXT,
            amostra INTEGER,
            fonte_sha256 TEXT,
            snapshot_sha256 TEXT,
            criado_em TEXT,
            PRIMARY KEY(
                posto_id,
                combustivel_codigo
            )
        );
        """)

        self.sql = []
        self.falhar_insert = 0
        self.inserts = 0
        self.commit_perdido = False

    def cursor(self):
        return Cursor(self)

    def commit(self):
        self.conn.commit()

        if self.commit_perdido:
            raise OSError(
                "commit simulado sem resposta"
            )

    def rollback(self):
        self.conn.rollback()

    def quantidade(self):
        return self.conn.execute(
            "SELECT COUNT(*) "
            "FROM referencias_medias_iniciais"
        ).fetchone()[0]


class Cursor:
    def __init__(self, banco):
        self.banco = banco
        self.cur = banco.conn.cursor()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.cur.close()

    def execute(self, sql, params=()):
        self.banco.sql.append(sql)

        # Normaliza somente para identificar o comando.
        # O SQL executado abaixo preserva seu conteúdo.
        sql_normalizado = " ".join(
            sql.split()
        ).casefold()

        if sql_normalizado.startswith(
            "insert into referencias_medias_iniciais"
        ):
            self.banco.inserts += 1

            if (
                self.banco.falhar_insert
                == self.banco.inserts
            ):
                raise RuntimeError(
                    "insert simulado recusado"
                )

        convertido = (
            sql.replace("%s", "?")
            .replace(" FOR UPDATE", "")
            .replace(
                "UTC_TIMESTAMP()",
                "CURRENT_TIMESTAMP",
            )
            .replace(
                "BEGIN PESSIMISTIC",
                "BEGIN",
            )
        )

        adaptados = [
            format(valor, "f")
            if isinstance(valor, Decimal)
            else valor.isoformat()
            if isinstance(valor, date)
            else valor
            for valor in params
        ]

        self.cur.execute(
            convertido,
            adaptados,
        )

    def fetchall(self):
        resultado = [
            dict(row)
            for row in self.cur.fetchall()
        ]

        for row in resultado:
            for campo in (
                "periodo_inicio",
                "periodo_fim",
            ):
                if (
                    campo in row
                    and isinstance(row[campo], str)
                ):
                    row[campo] = date.fromisoformat(
                        row[campo]
                    )

            if (
                "data_registro" in row
                and isinstance(
                    row["data_registro"],
                    str,
                )
            ):
                row["data_registro"] = (
                    datetime.fromisoformat(
                        row["data_registro"]
                    )
                )

        return resultado


class MediasTests(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)

        self.arquivo = (
            Path(self.pasta.name)
            / "snapshot.csv"
        )
        self.arquivo.write_bytes(csv_snapshot())

        self.sha = hashlib.sha256(
            self.arquivo.read_bytes()
        ).hexdigest()

        self.snapshot = m.carregar_snapshot(
            self.arquivo, self.sha
        )

        self.banco = Banco()
        self.addCleanup(self.banco.conn.close)

        self.remendo = patch(
            "services.migrations.run",
            return_value={
                "versao_servidor": (
                    "8.0.11-TiDB-v8.5.3"
                ),
                "migracoes": [
                    {"estado": "aplicada"}
                ],
            },
        )

        self.verificar = self.remendo.start()
        self.addCleanup(self.remendo.stop)

    def executar(self, aplicar=False):
        return m.carregar_medias(
            self.banco,
            [],
            self.snapshot,
            self.sha,
            banco="ensaio",
            aplicar=aplicar,
        )

    def test_previa_nao_grava_e_mostra_oito_referencias(self):
        resultado = self.executar()

        self.assertEqual(
            resultado["resumo"],
            {"inserir_referencia_estimada": 8},
        )
        self.assertEqual(
            self.banco.quantidade(), 0
        )
        self.assertFalse(any(
            sql.lstrip().startswith((
                "INSERT", "UPDATE", "DELETE", "CREATE"
            ))
            for sql in self.banco.sql
        ))

    def test_carga_so_grava_referencias_e_repete_sem_duplicar(self):
        self.executar(True)

        self.assertEqual(
            self.banco.quantidade(), 8
        )

        resultado = self.executar(True)

        self.assertEqual(
            resultado["resumo"],
            {"referencia_ja_existe": 8},
        )
        self.assertEqual(
            self.banco.quantidade(), 8
        )
        self.assertEqual(
            self.banco.conn.execute(
                "SELECT COUNT(*) FROM registos_preco"
            ).fetchone()[0],
            0,
        )
        self.assertTrue(all(
            not sql.lstrip().startswith((
                "UPDATE", "DELETE", "CREATE", "ALTER"
            ))
            for sql in self.banco.sql
        ))

    def test_preco_existente_preservado_e_novo_registro_prevalece(self):
        self.banco.conn.execute(
            "INSERT INTO registos_preco VALUES"
            "(99,1,NULL,'Gasolina Comum',6.27,"
            "'2026-11-24 10:00:00')"
        )
        self.banco.conn.commit()

        resultado = self.executar(True)

        self.assertEqual(
            resultado["resumo"][
                "preservar_preco_registrado"
            ],
            1,
        )
        self.assertEqual(
            self.banco.quantidade(), 7
        )
        self.assertEqual(
            self.banco.conn.execute(
                "SELECT preco FROM registos_preco "
                "WHERE id=99"
            ).fetchone()[0],
            6.27,
        )

    def test_snapshot_com_registro_removido_nao_e_substituido(self):
        self.snapshot[0]["possui_registro"] = True

        self.assertEqual(
            self.executar(True)["resumo"][
                "preservar_preco_registrado"
            ],
            1,
        )
        self.assertEqual(
            self.banco.quantidade(), 7
        )

    def test_mudanca_de_oferta_para_indisponivel_bloqueia(self):
        self.banco.conn.execute(
            "INSERT INTO postos_combustiveis "
            "VALUES(1,'gnv',0,1)"
        )
        self.banco.conn.commit()

        self.assertEqual(
            self.executar(True)["resumo"][
                "ignorar_indisponivel"
            ],
            1,
        )
        self.assertEqual(
            self.banco.quantidade(), 7
        )

    def test_erro_no_segundo_insert_reverte_o_primeiro(self):
        self.banco.falhar_insert = 2

        with self.assertRaisesRegex(
            RuntimeError,
            "insert simulado recusado",
        ):
            self.executar(True)

        self.assertEqual(
            self.banco.inserts,
            2,
        )

        self.assertEqual(
            self.banco.quantidade(),
            0,
        )

    def test_commit_perdido_recupera_por_previa_sem_repeticao(self):
        self.banco.commit_perdido = True

        with self.assertRaisesRegex(
            m.ErroMedias,
            "Commit sem confirmação",
        ):
            self.executar(True)

        self.banco.commit_perdido = False

        self.assertEqual(
            self.banco.quantidade(), 8
        )
        self.assertEqual(
            self.executar()["resumo"],
            {"referencia_ja_existe": 8},
        )

    def test_schema_pendente_e_banco_errado_bloqueiam(self):
        self.verificar.return_value[
            "migracoes"
        ][0]["estado"] = "pendente"

        with self.assertRaisesRegex(
            m.ErroMedias, "006"
        ):
            self.executar(True)

        self.verificar.side_effect = MigrationError(
            "Banco diferente"
        )

        with self.assertRaises(MigrationError):
            self.executar(True)

        self.assertEqual(
            self.banco.quantidade(), 0
        )

    def test_posto_removido_renomeado_ou_de_outra_cidade_bloqueia(self):
        comandos = (
            "DELETE FROM postos WHERE id=1",
            "UPDATE postos SET nome='Outro' WHERE id=1",
            "UPDATE postos SET cidade='Campina Grande' WHERE id=1",
        )

        for sql in comandos:
            with self.subTest(sql=sql):
                banco = Banco()

                try:
                    banco.conn.execute(sql)
                    banco.conn.commit()

                    with self.assertRaises(
                        m.ErroMedias
                    ):
                        m.carregar_medias(
                            banco,
                            [],
                            self.snapshot,
                            self.sha,
                            banco="ensaio",
                            aplicar=True,
                        )

                    self.assertEqual(
                        banco.quantidade(), 0
                    )
                finally:
                    banco.conn.close()

    def test_referencia_divergente_nao_e_sobrescrita(self):
        self.executar(True)

        self.banco.conn.execute(
            "UPDATE referencias_medias_iniciais "
            "SET preco=6.21 "
            "WHERE combustivel_codigo='gasolina_comum'"
        )
        self.banco.conn.commit()

        with self.assertRaises(m.ErroMedias):
            self.executar(True)

        self.assertEqual(
            self.banco.quantidade(), 8
        )

    def test_hash_trocado_csv_incompleto_e_produto_desconhecido_recusados(self):
        with self.assertRaises(m.ErroMedias):
            m.carregar_snapshot(
                self.arquivo, "0" * 64
            )

        original = csv_snapshot().decode()

        variantes = (
            original.replace(
                "gasolina_comum", "diesel"
            ),
            "\n".join(
                original.splitlines()[:-1]
            ),
            original
            + original.splitlines()[1]
            + "\n",
        )

        for texto in variantes:
            self.arquivo.write_text(
                texto, encoding="utf-8"
            )
            sha = hashlib.sha256(
                self.arquivo.read_bytes()
            ).hexdigest()

            with self.assertRaises(m.ErroMedias):
                m.carregar_snapshot(
                    self.arquivo, sha
                )

    def test_api_opt_in_preserva_caminho_legado(self):
        self.executar(True)
        filtros = validar_filtros({})

        legado = consultar_catalogo(
            self.banco,
            None,
            25,
            500,
            filtros,
            lambda *args: 0,
        )

        self.assertIsNone(
            legado[0]["preco_referencia"]
        )

        atual = consultar_catalogo(
            self.banco,
            None,
            25,
            500,
            filtros,
            lambda *args: 0,
            incluir_estimativas=True,
        )

        oferta = atual[0]["combustiveis"][0]

        self.assertEqual(
            atual[0]["preco_referencia"], 6.20
        )
        self.assertIsNone(oferta["autor_nome"])
        self.assertIsNone(oferta["registo_id"])
        self.assertIsNone(oferta["atualizado_em"])
        self.assertIsNone(oferta["disponivel"])

        self.assertEqual(
            oferta["estimativa"]["periodo_inicio"],
            "2026-11-15",
        )

    def test_api_registro_real_prevalece_sobre_media_e_na_ordenacao(self):
        self.executar(True)

        self.banco.conn.execute(
            "INSERT INTO registos_preco VALUES"
            "(99,1,NULL,'Gasolina Comum',6.27,"
            "'2026-11-24 10:00:00')"
        )
        self.banco.conn.commit()

        resultado = consultar_catalogo(
            self.banco,
            None,
            25,
            500,
            validar_filtros({"ordenar": "preco"}),
            lambda *args: 0,
            incluir_estimativas=True,
        )

        self.assertEqual(
            resultado[0]["id"], 1
        )
        self.assertEqual(
            resultado[0]["preco_referencia"],
            6.27,
        )
        self.assertNotIn(
            "estimativa",
            resultado[0]["combustiveis"][0],
        )
        self.assertEqual(
            resultado[1]["preco_referencia"],
            6.20,
        )

    def test_api_nao_confirma_disponibilidade_por_ter_media(self):
        self.executar(True)

        resultado = consultar_catalogo(
            self.banco,
            None,
            25,
            500,
            validar_filtros({
                "combustiveis": "gasolina_comum",
            }),
            lambda *args: 0,
            incluir_estimativas=True,
        )

        self.assertEqual(resultado, [])

    def test_api_ignora_media_se_oferta_virar_negativa_ou_posto_eletrico(self):
        self.executar(True)

        self.banco.conn.execute(
            "INSERT INTO postos_combustiveis "
            "VALUES(1,'gasolina_comum',0,1)"
        )
        self.banco.conn.execute(
            "UPDATE postos "
            "SET tipo_posto='Eletroposto' WHERE id=2"
        )
        self.banco.conn.commit()

        resultado = consultar_catalogo(
            self.banco,
            None,
            25,
            500,
            validar_filtros({}),
            lambda *args: 0,
            incluir_estimativas=True,
        )

        self.assertTrue(all(
            posto["preco_referencia"] is None
            for posto in resultado
        ))

    def test_migracao_006_e_um_create_sem_reescrever_sql_anterior(self):
        migracoes = load_migrations(
            ROOT / "migrations"
        )

        self.assertEqual(
            migracoes[-1]["versao"],
            "006_referencias_medias_iniciais",
        )
        self.assertEqual(
            len(migracoes[-1]["statements"]),
            1,
        )
        self.assertTrue(
            migracoes[-1]["statements"][0].startswith(
                "CREATE TABLE referencias_medias_iniciais"
            )
        )
        self.assertEqual(len(migracoes), 6)

    def test_006_exige_colunas_indices_collations_e_relacoes(self):
        tabela = "referencias_medias_iniciais"

        schema = {
            "tables": {
                tabela: "InnoDB",
            },
            "columns": {
                (tabela, nome): {
                    "tipo": tipo,
                    "nulo": "NO",
                    "collation": "ascii_bin",
                }
                for nome, tipo in COLUNAS.items()
            },
            "indexes": [
                {
                    "tabela": tabela,
                    "indice": nome,
                    "coluna": campo,
                    "ordem": ordem,
                    "nao_unico": nao_unico,
                }
                for nome, campos, nao_unico in (
                    (
                        "PRIMARY",
                        ("posto_id", "combustivel_codigo"),
                        0,
                    ),
                    (
                        "idx_rmi_combustivel",
                        ("combustivel_codigo",),
                        1,
                    ),
                )
                for ordem, campo
                in enumerate(campos, 1)
            ],
        }

        cursor = Mock()
        cursor.fetchall.return_value = [
            {
                "origem": "posto_id",
                "destino": "postos",
                "campo": "id",
                "exclusao": "CASCADE",
            },
            {
                "origem": "combustivel_codigo",
                "destino": "combustiveis",
                "campo": "codigo",
                "exclusao": "NO ACTION",
            },
        ]

        validar_estrutura(
            cursor, schema, _column, _index
        )

        for defeito in (
            "coluna",
            "indice",
            "collation",
            "fk",
        ):
            ruim = copy.deepcopy(schema)

            if defeito == "coluna":
                ruim["columns"].pop(
                    (tabela, "fonte_sha256")
                )
            elif defeito == "indice":
                ruim["indexes"] = []
            elif defeito == "collation":
                ruim["columns"][
                    (tabela, "fonte_sha256")
                ]["collation"] = "utf8mb4_unicode_ci"
            else:
                cursor.fetchall.return_value = []

            with (
                self.subTest(defeito=defeito),
                self.assertRaises(MigrationError),
            ):
                validar_estrutura(
                    cursor,
                    ruim,
                    _column,
                    _index,
                )

    def test_006_parcial_sem_ledger_nao_e_adotada(self):
        from test_infra_banco import FakeDB
        from services.plano_migracoes import make_plan

        db = FakeDB()

        db.tables[
            "referencias_medias_iniciais"
        ] = "InnoDB"

        with self.assertRaisesRegex(
            MigrationError,
            "Estrutura sem registro",
        ):
            make_plan(
                db.cursor(),
                [
                    load_migrations(
                        ROOT / "migrations"
                    )[-1]
                ],
            )

    def test_parametro_publico_so_aceita_opt_in_explicito(self):
        from flask import Flask
        from app.rotas import postos

        app = Flask("teste_medias_opt_in")

        app.register_blueprint(
            postos.postos_bp,
            url_prefix="/postos",
        )

        conn = Mock(open=True)

        with patch.object(
            postos,
            "get_db_connection",
            return_value=conn,
        ) as conectar:
            with patch.object(
                postos,
                "consultar_catalogo",
                return_value=[],
            ) as consultar:
                client = app.test_client()

                self.assertEqual(
                    client.get(
                        "/postos?incluir_estimativas=1"
                    ).status_code,
                    200,
                )
                self.assertTrue(
                    consultar.call_args.kwargs[
                        "incluir_estimativas"
                    ]
                )

                self.assertEqual(
                    client.get("/postos").status_code,
                    200,
                )
                self.assertFalse(
                    consultar.call_args.kwargs[
                        "incluir_estimativas"
                    ]
                )

                conectar.reset_mock()

                self.assertEqual(
                    client.get(
                        "/postos?incluir_estimativas=sim"
                    ).status_code,
                    400,
                )

                conectar.assert_not_called()


if __name__ == "__main__":
    unittest.main()