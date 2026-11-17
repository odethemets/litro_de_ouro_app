"""Conexao MySQL/PyMySQL compartilhada, sem importar ou inicializar Flask."""
from __future__ import annotations

import os
import ssl
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping
from urllib.parse import parse_qsl, unquote, urlsplit


class DatabaseConfigError(ValueError):
    pass


@dataclass(frozen=True)
class DatabaseConfig:
    host: str = field(repr=False)
    port: int
    user: str = field(repr=False)
    password: str = field(repr=False)
    database: str
    ca_file: str | None = field(default=None, repr=False)


def config_from_mapping(env: Mapping[str, str]) -> DatabaseConfig:
    """DATABASE_URL prevalece; variaveis DB_* sao o formato alternativo."""
    raw = env.get("DATABASE_URL", "").strip()
    ca_file = env.get("DB_SSL_CA", "").strip() or None
    if raw:
        try:
            if any(ord(c) < 32 for c in raw):
                raise ValueError
            parts = urlsplit(raw)
            if parts.scheme not in ("mysql", "mysql+pymysql"):
                raise ValueError
            if parts.fragment or not parts.hostname or not parts.username:
                raise ValueError
            if parts.password is None or not parts.path.startswith("/"):
                raise ValueError
            query = parse_qsl(
                parts.query,
                keep_blank_values=True,
                strict_parsing=True,
            )
            if len(query) > 1 or any(
                k != "charset" or v != "utf8mb4"
                for k, v in query
            ):
                raise ValueError
            host = parts.hostname
            port = parts.port if parts.port is not None else 3306
            user = unquote(parts.username)
            password = unquote(parts.password)
            database = unquote(parts.path[1:])
        except (TypeError, ValueError):
            raise DatabaseConfigError(
                "DATABASE_URL invalida. Use mysql://usuario:senha@host:porta/banco; "
                "codifique caracteres especiais e configure a CA em DB_SSL_CA."
            ) from None
    else:
        required = ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME")
        if any(not env.get(k, "").strip() for k in required):
            raise DatabaseConfigError(
                "Configure DATABASE_URL ou todos os campos: "
                + ", ".join(required)
            )
        host = env["DB_HOST"].strip()
        user = env["DB_USER"].strip()
        password = env["DB_PASSWORD"]
        database = env["DB_NAME"].strip()
        try:
            port = int(env["DB_PORT"])
        except (TypeError, ValueError):
            raise DatabaseConfigError(
                "DB_PORT deve ser uma porta numerica valida."
            ) from None

    if (
        not host
        or not user
        or not password
        or not database
        or not (1 <= port <= 65535)
    ):
        raise DatabaseConfigError(
            "Parametros de banco incompletos ou porta invalida."
        )
    if (
        "/" in database
        or "\\" in database
        or any(ord(c) < 32 for c in host + user + database)
    ):
        raise DatabaseConfigError(
            "Nome de banco, host ou usuario invalido."
        )
    return DatabaseConfig(host, port, user, password, database, ca_file)


def load_config() -> DatabaseConfig:
    from dotenv import load_dotenv

    load_dotenv(
        Path(__file__).resolve().parents[1] / ".env",
        override=False,
    )
    return config_from_mapping(os.environ)


def tls_context(config: DatabaseConfig) -> ssl.SSLContext:
    try:
        context = ssl.create_default_context(cafile=config.ca_file)
    except (OSError, ssl.SSLError):
        raise DatabaseConfigError(
            "Nao foi possivel carregar a CA configurada em DB_SSL_CA."
        ) from None
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def get_db_connection(
    *,
    read_only: bool = False,
    time_zone: str = "-03:00",
    config: DatabaseConfig | None = None,
):
    """Metadados novos usam UTC; o app conserva UTC-3 para seu historico atual."""
    conn = None
    stage = "configuracao"
    try:
        if time_zone not in ("-03:00", "+00:00"):
            raise DatabaseConfigError("Fuso de conexao nao permitido.")
        config = config or load_config()

        stage = "carregar_driver"
        import pymysql
        import pymysql.cursors

        stage = "preparar_tls"
        context = tls_context(config)

        stage = "conectar"
        conn = pymysql.connect(
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password,
            database=config.database,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
            ssl=context,
            connect_timeout=10,
            read_timeout=30,
            write_timeout=30,
        )
        with conn.cursor() as cursor:
            stage = "definir_fuso"
            cursor.execute("SET SESSION time_zone = %s", (time_zone,))

            if read_only:
                stage = "identificar_servidor"
                cursor.execute("SELECT VERSION() AS versao")
                version = str(cursor.fetchone()["versao"])

                stage = "configurar_isolamento_leitura"
                cursor.execute(
                    "SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ"
                )
                stage = "iniciar_transacao_leitura"

                # READ ONLY pode retornar 1235 no TiDB por ser noop.
                # As previas TiDB nao devem emitir DML/DDL.
                if "tidb" in version.lower():
                    cursor.execute("START TRANSACTION")
                else:
                    cursor.execute(
                        "START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY"
                    )
        return conn

    except Exception as exc:
        try:
            exc.etapa_banco = stage
        except (AttributeError, TypeError):
            pass

        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        raise