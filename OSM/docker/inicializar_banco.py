"""Inicializa somente o schema Docker ficticio; nunca apaga ou reimporta dados."""
from __future__ import annotations

import hashlib
import json
import os
import ssl
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.database import load_config, get_db_connection
from services.migrations import split_sql
from werkzeug.security import generate_password_hash

BASE = ROOT / "docker" / "schema_base.sql"
MARKER = "ldo_docker_local"
VERSION = "1"


def local_connection(read_only=False):
    config = load_config()

    if (
        os.getenv("LDO_DOCKER_LOCAL") != "1"
        or config.host != "db"
        or config.port != 3306
        or config.database != "litro_de_ouro_dev"
        or config.user != "litro_local"
        or os.getenv("DATABASE_URL", "").strip()
    ):
        raise RuntimeError(
            "Operacao exclusiva do banco "
            "db/litro_de_ouro_dev do Compose local."
        )

    conn = get_db_connection(
        config=config,
        read_only=read_only,
        time_zone="-03:00",
    )

    sock = getattr(conn, "_sock", None)
    if (
        not isinstance(sock, ssl.SSLSocket)
        or not sock.cipher()
        or sock.context.verify_mode != ssl.CERT_REQUIRED
        or not sock.context.check_hostname
    ):
        conn.close()
        raise RuntimeError(
            "TLS local negociado e verificado e obrigatorio."
        )

    return conn


def run():
    conn = local_connection()
    checksum = hashlib.sha256(
        BASE.read_bytes()
    ).hexdigest()

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT VERSION() AS versao")
            if "tidb" in cursor.fetchone()["versao"].lower():
                raise RuntimeError(
                    "Inicializacao Docker nao deve executar no TiDB."
                )

            cursor.execute(
                "SELECT TABLE_NAME AS nome "
                "FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA=DATABASE()"
            )
            tables = {
                r["nome"]
                for r in cursor.fetchall()
            }

            if tables:
                if MARKER not in tables:
                    raise RuntimeError(
                        "Schema ocupado sem marcador local. "
                        "Revisar; nenhum dado sera removido."
                    )

                cursor.execute(
                    "SELECT versao,sha256,estado "
                    "FROM ldo_docker_local WHERE id=1"
                )
                row = cursor.fetchone()

                if not row or row != {
                    "versao": VERSION,
                    "sha256": checksum,
                    "estado": "pronto",
                }:
                    raise RuntimeError(
                        "Inicializacao parcial ou esquema base alterado. "
                        "Revisao manual necessaria."
                    )

                if not {
                    "postos",
                    "usuarios",
                    "registos_preco",
                    "votos_registos",
                }.issubset(tables):
                    raise RuntimeError(
                        "Tabela base local ausente; revisar o volume."
                    )

                return {
                    "status": "ok",
                    "acao": "dados_locais_existentes_preservados",
                }

            cursor.execute(
                """CREATE TABLE ldo_docker_local (
                id INT PRIMARY KEY,
                versao VARCHAR(16) NOT NULL,
                sha256 CHAR(64) NOT NULL,
                estado VARCHAR(20) NOT NULL,
                criado_em DATETIME NOT NULL
                ) ENGINE=InnoDB"""
            )
            cursor.execute(
                "INSERT INTO ldo_docker_local "
                "VALUES(1,%s,%s,'em_execucao',UTC_TIMESTAMP())",
                (VERSION, checksum),
            )

        conn.commit()

        for sql in split_sql(
            BASE.read_text(encoding="utf-8")
        ):
            with conn.cursor() as cursor:
                cursor.execute(sql)
            conn.commit()

        with conn.cursor() as cursor:
            cursor.execute(
                """INSERT INTO usuarios(
                    id,nome,email,senha,karma,email_verificado
                )
                VALUES(
                    1,'Usuario Docker Ficticio',
                    'dev@litro.local',%s,0,1
                )""",
                (generate_password_hash("DockerLocal123!"),),
            )

            stations = [
                (
                    1,
                    "[TESTE] Posto Docker A",
                    "Endereco ficticio A",
                    -7.1100,
                    -34.8600,
                    "Convencional",
                ),
                (
                    2,
                    "[TESTE] Posto Docker B",
                    "Endereco ficticio B",
                    -7.1140,
                    -34.8640,
                    "Convencional",
                ),
                (
                    3,
                    "[TESTE] Eletroposto Docker",
                    "Endereco ficticio C",
                    -7.1080,
                    -34.8560,
                    "Eletroposto",
                ),
                (
                    4,
                    "[TESTE] Posto sem preco",
                    "Endereco ficticio D",
                    -7.1120,
                    -34.8580,
                    "Convencional",
                ),
            ]

            cursor.executemany(
                """INSERT INTO postos(
                    id,nome,endereco,latitude,longitude,tipo_posto
                ) VALUES(%s,%s,%s,%s,%s,%s)""",
                stations,
            )

            cursor.executemany(
                """INSERT INTO registos_preco(
                    posto_id,usuario_id,tipo_combustivel,
                    preco,data_registro
                ) VALUES(%s,1,%s,%s,NOW())""",
                [
                    (1, "Gasolina Comum", "5.89"),
                    (1, "Diesel", "5.10"),
                    (2, "Gasolina Comum", "6.19"),
                    (3, "Recarga Elétrica (kWh)", "2.20"),
                ],
            )

            cursor.execute(
                "UPDATE ldo_docker_local "
                "SET estado='pronto' WHERE id=1"
            )

        conn.commit()

        return {
            "status": "ok",
            "acao": "base_ficticia_criada",
            "postos": 4,
            "usuarios": 1,
            "precos": 4,
            "votos": 0,
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    try:
        print(json.dumps(run(), ensure_ascii=False))

    except Exception as exc:
        print(json.dumps({
            "status": "falha_inicializacao_local",
            "tipo": type(exc).__name__,
            "erro": (
                str(exc)
                if isinstance(exc, RuntimeError)
                else (
                    "Falha de banco; "
                    "detalhes de conexao omitidos."
                )
            ),
        }))
        raise SystemExit(1)