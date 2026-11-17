"""Copia pontual de quatro tabelas MySQL para TiDB, sem alterar a origem."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import ssl
import tempfile
import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path

from services.database import config_from_mapping, get_db_connection

ROOT = Path(__file__).resolve().parents[1]
TABLES = ("postos", "usuarios", "registos_preco", "votos_registos")
SQL_MODE = (
    "STRICT_TRANS_TABLES,NO_AUTO_VALUE_ON_ZERO,"
    "ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION"
)
ALLOWED_TYPES = {
    "int", "tinyint", "smallint", "mediumint", "bigint",
    "varchar", "char", "decimal", "datetime", "timestamp",
    "date", "time", "enum", "text",
}


class TransferError(RuntimeError):
    pass


def q(name):
    return "`" + str(name).replace("`", "``") + "`"


def rows(conn, sql, params=None):
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def execute(conn, sql, params=None):
    with conn.cursor() as cursor:
        cursor.execute(sql, params)


def load_profile(role):
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    if role not in ("ORIGEM", "DESTINO"):
        raise TransferError("Perfil de banco invalido.")

    key = "DATABASE_URL_" + role
    url = os.getenv(key, "").strip()
    if not url:
        raise TransferError(
            "Configure " + key + " no .env do backend."
        )

    return config_from_mapping({
        "DATABASE_URL": url,
        "DB_SSL_CA": os.getenv("DB_SSL_CA_" + role, ""),
    })


def connect(config, read_only=False):
    conn = get_db_connection(
        config=config,
        read_only=read_only,
        time_zone="+00:00",
    )
    sock = getattr(conn, "_sock", None)

    if not isinstance(sock, ssl.SSLSocket) or not sock.cipher():
        conn.close()
        raise TransferError(
            "A conexao nao confirmou TLS negociado."
        )
    if (
        sock.context.verify_mode != ssl.CERT_REQUIRED
        or not sock.context.check_hostname
    ):
        conn.close()
        raise TransferError(
            "A conexao exige certificado e hostname verificados."
        )
    return conn


def close(conn):
    if conn is not None:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


def failure(exc, stage):
    from scripts.migrar_banco import diagnostico_erro

    details = diagnostico_erro(
        exc,
        getattr(exc, "etapa_diagnostico", stage),
    )
    return {
        "status": "interrompido",
        **details,
        "erro": (
            str(exc)
            if isinstance(exc, TransferError)
            else (
                "Falha no banco ou arquivo local; "
                "mensagens com dados de conexao foram omitidas."
            )
        ),
    }


def tagged(value):
    if isinstance(value, Decimal):
        return {"decimal": format(value, "f")}
    if isinstance(value, (datetime, date, time)):
        return {type(value).__name__: value.isoformat()}
    if isinstance(value, bytes):
        return {
            "bytes": base64.b64encode(value).decode("ascii")
        }
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TransferError(
        "Tipo de valor nao suportado para copia exata."
    )


def digest(data, columns):
    serial = [
        [tagged(row[column]) for column in columns]
        for row in data
    ]
    return hashlib.sha256(
        json.dumps(
            serial,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def table_names(conn):
    return rows(
        conn,
        "SELECT TABLE_NAME AS nome,TABLE_TYPE AS tipo "
        "FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME",
    )


def require_empty(conn):
    if table_names(conn):
        raise TransferError(
            "O schema de destino deve estar completamente vazio. "
            "Use uma base de ensaio nova."
        )


def server(conn):
    return rows(
        conn,
        "SELECT DATABASE() AS banco,VERSION() AS versao,"
        "@@foreign_key_checks AS fk",
    )[0]


def metadata(conn, table):
    columns = rows(
        conn,
        """SELECT COLUMN_NAME AS nome,COLUMN_TYPE AS tipo,
        DATA_TYPE AS tipo_base,IS_NULLABLE AS nulo,COLUMN_DEFAULT AS padrao,
        EXTRA AS extra,COLLATION_NAME AS collation
        FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE()
        AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION""",
        (table,),
    )
    indexes = rows(
        conn,
        """SELECT INDEX_NAME AS nome,NON_UNIQUE AS nao_unico,
        COLUMN_NAME AS coluna,SEQ_IN_INDEX AS ordem,SUB_PART AS prefixo
        FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE()
        AND TABLE_NAME=%s ORDER BY INDEX_NAME,SEQ_IN_INDEX""",
        (table,),
    )
    fks = rows(
        conn,
        """SELECT k.CONSTRAINT_NAME AS nome,k.COLUMN_NAME AS coluna,
        k.ORDINAL_POSITION AS ordem,k.REFERENCED_TABLE_NAME AS tabela_pai,
        k.REFERENCED_COLUMN_NAME AS coluna_pai,
        k.REFERENCED_TABLE_SCHEMA AS schema_pai,
        r.DELETE_RULE AS exclusao,r.UPDATE_RULE AS atualizacao
        FROM information_schema.KEY_COLUMN_USAGE k
        JOIN information_schema.REFERENTIAL_CONSTRAINTS r
        ON r.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA AND r.TABLE_NAME=k.TABLE_NAME
        AND r.CONSTRAINT_NAME=k.CONSTRAINT_NAME
        WHERE k.TABLE_SCHEMA=DATABASE() AND k.TABLE_NAME=%s
        ORDER BY k.CONSTRAINT_NAME,k.ORDINAL_POSITION""",
        (table,),
    )
    info = rows(
        conn,
        """SELECT ENGINE AS engine,TABLE_COLLATION AS collation,
        AUTO_INCREMENT AS proximo_id FROM information_schema.TABLES
        WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s""",
        (table,),
    )[0]

    return {
        "columns": columns,
        "indexes": indexes,
        "fks": fks,
        "info": info,
    }


def signature(meta):
    copied = json.loads(json.dumps(meta, default=str))
    copied["info"].pop("proximo_id", None)

    for index in copied["indexes"]:
        index["nao_unico"] = int(index["nao_unico"])
        index["ordem"] = int(index["ordem"])
        if index["prefixo"] is not None:
            index["prefixo"] = int(index["prefixo"])

    copied["indexes"].sort(
        key=lambda row: (row["nome"], row["ordem"])
    )

    for col in copied["columns"]:
        col["tipo"] = re.sub(
            r"\b(tinyint|smallint|mediumint|int|bigint)\(\d+\)",
            r"\1",
            col["tipo"].lower(),
        )
        col["extra"] = re.sub(
            r"\bdefault_generated\b",
            "",
            col["extra"].lower(),
        ).strip()
        if (
            isinstance(col["padrao"], str)
            and re.fullmatch(
                r"current_timestamp(?:\(\))?",
                col["padrao"],
                re.I,
            )
        ):
            col["padrao"] = "CURRENT_TIMESTAMP"

    for fk in copied["fks"]:
        fk["ordem"] = int(fk["ordem"])
        fk.pop("schema_pai", None)
        for field in ("exclusao", "atualizacao"):
            if fk[field] == "NO ACTION":
                fk[field] = "RESTRICT"

    copied["fks"].sort(
        key=lambda row: (row["nome"], row["ordem"])
    )
    return copied


def unqualify_references(ddl, source_database):
    """Remove apenas qualificadores da origem em REFERENCES, fora de strings SQL."""
    tokens = []
    i = 0

    while i < len(ddl):
        c = ddl[i]
        if c == "'":
            i += 1
            while i < len(ddl):
                if ddl[i] == "\\":
                    i += 2
                elif ddl[i] == "'":
                    if i + 1 < len(ddl) and ddl[i + 1] == "'":
                        i += 2
                    else:
                        i += 1
                        break
                else:
                    i += 1
        elif c == "`":
            start, value = i, ""
            i += 1
            while i < len(ddl):
                if ddl[i] == "`":
                    if i + 1 < len(ddl) and ddl[i + 1] == "`":
                        value += "`"
                        i += 2
                    else:
                        i += 1
                        break
                else:
                    value += ddl[i]
                    i += 1
            tokens.append((value, start, i))
        elif c.isalnum() or c == "_":
            start = i
            while i < len(ddl) and (
                ddl[i].isalnum() or ddl[i] == "_"
            ):
                i += 1
            tokens.append((ddl[start:i], start, i))
        elif c == ".":
            tokens.append((c, i, i + 1))
            i += 1
        else:
            i += 1

    changes = []
    for n, token in enumerate(tokens):
        if (
            token[0].upper() != "REFERENCES"
            or n + 2 >= len(tokens)
        ):
            continue
        if tokens[n + 2][0] == ".":
            if (
                n + 3 >= len(tokens)
                or tokens[n + 1][0] != source_database
                or tokens[n + 3][0] not in TABLES
            ):
                raise TransferError(
                    "DDL possui referencia externa ao escopo da copia."
                )
            changes.append((
                tokens[n + 1][1],
                tokens[n + 2][2],
            ))

    for start, end in reversed(changes):
        ddl = ddl[:start] + ddl[end:]
    return ddl


def read_data(
    conn,
    table,
    columns,
    max_rows=100000,
    max_bytes=64 * 1024 * 1024,
):
    result, size = [], 0
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT "
            + ",".join(q(c) for c in columns)
            + " FROM "
            + q(table)
            + " ORDER BY id LIMIT "
            + str(max_rows + 1)
        )
        while True:
            batch = cursor.fetchmany(500)
            if not batch:
                break
            for row in batch:
                size += len(
                    json.dumps(
                        [tagged(row[c]) for c in columns],
                        ensure_ascii=False,
                    ).encode("utf-8")
                )
                result.append(row)
                if len(result) > max_rows or size > max_bytes:
                    raise TransferError(
                        "Copia excede o limite desta ferramenta; "
                        "requer planejamento de carga maior."
                    )
    return result


def snapshot(conn):
    conn.rollback()
    execute(
        conn,
        "SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ",
    )
    execute(conn, "SET SESSION sql_mode=%s", (SQL_MODE,))
    execute(conn, "SET SESSION sql_quote_show_create=1")
    execute(
        conn,
        "START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY",
    )

    actual = table_names(conn)
    if (
        {r["nome"] for r in actual} != set(TABLES)
        or any(r["tipo"] != "BASE TABLE" for r in actual)
    ):
        raise TransferError(
            "A origem deve conter exatamente as quatro tabelas base; "
            "outros objetos exigem revisao."
        )

    for catalog in ("TRIGGERS", "ROUTINES", "EVENTS"):
        field = {
            "TRIGGERS": "TRIGGER_SCHEMA",
            "ROUTINES": "ROUTINE_SCHEMA",
            "EVENTS": "EVENT_SCHEMA",
        }[catalog]
        if rows(
            conn,
            "SELECT COUNT(*) AS n FROM information_schema."
            + catalog
            + " WHERE "
            + field
            + "=DATABASE()",
        )[0]["n"]:
            raise TransferError(
                "A origem possui rotinas, eventos ou triggers "
                "fora do escopo desta copia."
            )

    origin = server(conn)
    captured = {
        "gerado_em_utc": datetime.now(timezone.utc).isoformat(),
        "tabelas": {},
    }

    for table in TABLES:
        meta = metadata(conn, table)

        if str(meta["info"]["engine"]).lower() != "innodb":
            raise TransferError(
                "A copia consistente requer todas as tabelas em InnoDB."
            )

        columns = [r["nome"] for r in meta["columns"]]
        if "id" not in columns or any(
            r["tipo_base"].lower() not in ALLOWED_TYPES
            or "GENERATED" in r["extra"].upper().replace(
                "DEFAULT_GENERATED", ""
            )
            for r in meta["columns"]
        ):
            raise TransferError(
                "Tipo ou coluna gerada fora do escopo da copia."
            )

        primary = [
            r["coluna"]
            for r in meta["indexes"]
            if r["nome"] == "PRIMARY"
        ]
        if (
            primary != ["id"]
            or next(
                r
                for r in meta["columns"]
                if r["nome"] == "id"
            )["tipo_base"] not in {"int", "bigint"}
        ):
            raise TransferError(
                "A copia exige uma chave primaria inteira "
                "chamada id em cada tabela."
            )

        if any(
            fk["schema_pai"] != origin["banco"]
            or fk["tabela_pai"] not in TABLES
            for fk in meta["fks"]
        ):
            raise TransferError(
                "A origem possui chave estrangeira externa as quatro tabelas."
            )

        ddl_row = rows(
            conn,
            "SHOW CREATE TABLE " + q(table),
        )[0]
        ddl = next(
            v
            for k, v in ddl_row.items()
            if k.lower() == "create table"
        )
        ddl = unqualify_references(ddl, origin["banco"])

        if (
            not ddl.lstrip().startswith("CREATE TABLE " + q(table))
            or ";" in ddl.rstrip(";\n ")
        ):
            raise TransferError(
                "DDL recebido fora do formato permitido."
            )

        data = read_data(conn, table, columns)
        minimum_id = max(
            int(meta["info"]["proximo_id"] or 1),
            max((r["id"] for r in data), default=0) + 1,
        )

        captured["tabelas"][table] = {
            "ddl": ddl,
            "meta": meta,
            "columns": columns,
            "rows": data,
            "sha256": digest(data, columns),
            "proximo_id": minimum_id,
        }

    for table, item in captured["tabelas"].items():
        if signature(
            metadata(conn, table)
        ) != signature(item["meta"]):
            raise TransferError(
                "O esquema da origem mudou durante a leitura."
            )
    return captured


def summary(captured):
    return {
        table: {
            "linhas": len(item["rows"]),
            "sha256": item["sha256"],
            "proximo_id_minimo": item["proximo_id"],
        }
        for table, item in captured["tabelas"].items()
    }


def check_collations(dest, captured):
    supported = {
        r["nome"]
        for r in rows(
            dest,
            "SELECT COLLATION_NAME AS nome "
            "FROM information_schema.COLLATIONS",
        )
    }
    required = set()
    for item in captured["tabelas"].values():
        required.add(item["meta"]["info"]["collation"])
        required.update(
            c["collation"]
            for c in item["meta"]["columns"]
            if c["collation"]
        )

    if required - supported:
        raise TransferError(
            "O destino nao suporta todas as collations da origem; "
            "nao havera conversao automatica."
        )


def write_backup(source, captured, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    name = (
        "aiven_"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_")
        + uuid.uuid4().hex[:8]
        + ".sql"
    )
    path = folder / name
    temp_name = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=folder,
            prefix=".backup-",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temp_name = stream.name
            stream.write(
                "-- Backup consistente. Contem dados pessoais "
                "e hashes de senha.\n"
            )
            stream.write(
                "SET NAMES utf8mb4;\n"
                "SET time_zone='+00:00';\n"
                "SET SESSION sql_mode='" + SQL_MODE + "';\n"
            )

            for table, item in captured["tabelas"].items():
                stream.write(
                    item["ddl"].rstrip(";\n ") + ";\n"
                )
                stream.write(
                    "ALTER TABLE "
                    + q(table)
                    + " AUTO_INCREMENT="
                    + str(item["proximo_id"])
                    + ";\n"
                )

            stream.write("START TRANSACTION;\n")
            with source.cursor() as cursor:
                for table, item in captured["tabelas"].items():
                    sql = (
                        "INSERT INTO "
                        + q(table)
                        + " ("
                        + ",".join(q(c) for c in item["columns"])
                        + ") VALUES ("
                        + ",".join(["%s"] * len(item["columns"]))
                        + ")"
                    )
                    for row in item["rows"]:
                        stream.write(
                            cursor.mogrify(
                                sql,
                                tuple(
                                    row[c]
                                    for c in item["columns"]
                                ),
                            )
                            + ";\n"
                        )

            stream.write("COMMIT;\n")
            stream.flush()
            os.fsync(stream.fileno())

        os.link(temp_name, path)
        return str(path)

    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def verify_data(dest, captured):
    for table, item in captured["tabelas"].items():
        actual = read_data(
            dest,
            table,
            item["columns"],
        )
        if (
            len(actual) != len(item["rows"])
            or digest(actual, item["columns"]) != item["sha256"]
        ):
            raise TransferError(
                "Dados de destino divergentes em "
                + table
                + "; a transacao nao sera confirmada."
            )


def next_id(dest, table, item):
    value = int(
        metadata(dest, table)["info"]["proximo_id"] or 0
    )
    if value < item["proximo_id"] and not item["rows"]:
        allocators = rows(
            dest,
            "SHOW TABLE " + q(table) + " NEXT_ROW_ID",
        )
        for row in allocators:
            row = {
                k.upper(): v
                for k, v in row.items()
            }
            if row.get("COLUMN_NAME") == "id":
                value = max(
                    value,
                    int(row.get("NEXT_GLOBAL_ROW_ID") or 0),
                )
    return value


def transfer(
    origin_config,
    dest_config,
    *,
    apply=False,
    expected_database=None,
    backup_folder=ROOT / "backups",
    state=None,
):
    from services.diagnostico_tidb import diagnose

    state = state if state is not None else {}
    state.update(
        modo="aplicar" if apply else "dry-run",
        etapa="conectar_origem",
        ddl_destino_iniciado=False,
        commit_dados="nao_iniciado",
    )

    source = dest = None
    locked = False
    lock_name = (
        "ldo_copy_"
        + hashlib.sha256(
            dest_config.database.encode()
        ).hexdigest()[:32]
    )

    try:
        if (
            origin_config.host.lower(),
            origin_config.port,
            origin_config.database.lower(),
        ) == (
            dest_config.host.lower(),
            dest_config.port,
            dest_config.database.lower(),
        ):
            raise TransferError(
                "Origem e destino devem ser bancos distintos."
            )

        source = connect(
            origin_config,
            read_only=True,
        )
        origin_info = server(source)
        if "tidb" in origin_info["versao"].lower():
            raise TransferError(
                "O perfil ORIGEM deve apontar para MySQL/Aiven."
            )

        state["etapa"] = "conectar_destino"
        dest = connect(
            dest_config,
            read_only=not apply,
        )
        target = server(dest)
        if (
            "tidb" not in target["versao"].lower()
            or int(target["fk"]) != 1
        ):
            raise TransferError(
                "DESTINO deve ser TiDB com foreign_key_checks ativo."
            )

        if apply and (
            not expected_database
            or expected_database != target["banco"]
        ):
            raise TransferError(
                "--banco-destino deve corresponder ao schema conectado."
            )

        state.update(
            banco_destino=target["banco"],
            versao_destino=target["versao"],
            etapa="ler_snapshot_origem",
        )

        captured = snapshot(source)
        require_empty(dest)
        check_collations(dest, captured)
        state.update(
            tabelas=summary(captured),
            snapshot_em_utc=captured["gerado_em_utc"],
        )

        state["etapa"] = "diagnostico_destino"
        state["diagnostico"] = diagnose(
            dest_config,
            write=False,
        )

        if not apply:
            return {
                **state,
                "status": "ok",
                "etapa": "previa_concluida",
                "gravacoes_tabelas_aplicacao": False,
            }

        dest.commit()
        if rows(
            dest,
            "SELECT GET_LOCK(%s,1) AS adquirido",
            (lock_name,),
        )[0]["adquirido"] != 1:
            raise TransferError(
                "Outra transferencia esta em andamento nesse destino."
            )
        locked = True
        require_empty(dest)

        state["etapa"] = "backup_local"
        state["backup_arquivo"] = write_backup(
            source,
            captured,
            backup_folder,
        )

        state["etapa"] = "testar_integridade_destino"
        state["diagnostico"] = diagnose(
            dest_config,
            write=True,
        )
        require_empty(dest)
        dest.commit()
        execute(
            dest,
            "SET SESSION sql_mode=%s",
            (SQL_MODE,),
        )

        state["etapa"] = "criar_estrutura_destino"
        state["ddl_destino_iniciado"] = True

        for table, item in captured["tabelas"].items():
            execute(dest, item["ddl"])
            dest.commit()
            execute(
                dest,
                "ALTER TABLE " + q(table) + " AUTO_INCREMENT=%s",
                (item["proximo_id"],),
            )
            dest.commit()

        for table, item in captured["tabelas"].items():
            meta = metadata(dest, table)
            if signature(meta) != signature(item["meta"]):
                raise TransferError(
                    "Estrutura de destino divergente em "
                    + table
                    + "; nenhuma conversao sera aceita."
                )

            text = next(
                v
                for k, v in rows(
                    dest,
                    "SHOW CREATE TABLE " + q(table),
                )[0].items()
                if k.lower() == "create table"
            )
            if "FOREIGN KEY INVALID" in text.upper():
                raise TransferError(
                    "O destino criou chave estrangeira sem enforcement."
                )

        dest.commit()
        execute(dest, "BEGIN PESSIMISTIC")
        state.update(
            etapa="copiar_dados",
            commit_dados="nao_confirmado",
        )

        for table, item in captured["tabelas"].items():
            sql = (
                "INSERT INTO "
                + q(table)
                + " ("
                + ",".join(q(c) for c in item["columns"])
                + ") VALUES ("
                + ",".join(["%s"] * len(item["columns"]))
                + ")"
            )
            with dest.cursor() as cursor:
                for row in item["rows"]:
                    cursor.execute(
                        sql,
                        tuple(
                            row[c]
                            for c in item["columns"]
                        ),
                    )

        state["etapa"] = "conferir_dados_antes_commit"
        verify_data(dest, captured)

        for table, item in captured["tabelas"].items():
            if next_id(dest, table, item) < item["proximo_id"]:
                raise TransferError(
                    "AUTO_INCREMENT de destino inferior "
                    "ao minimo preservado."
                )

        state["etapa"] = "confirmar_estabilidade_origem"
        fresh = None
        try:
            fresh = connect(
                origin_config,
                read_only=True,
            )
            latest = snapshot(fresh)

            for table in TABLES:
                if (
                    latest["tabelas"][table]["sha256"]
                    != captured["tabelas"][table]["sha256"]
                    or signature(
                        latest["tabelas"][table]["meta"]
                    ) != signature(
                        captured["tabelas"][table]["meta"]
                    )
                ):
                    raise TransferError(
                        "A origem mudou durante a copia; "
                        "pause escritas e use um novo destino vazio."
                    )
        finally:
            close(fresh)

        state["etapa"] = "confirmar_commit"
        dest.commit()
        state["commit_dados"] = "confirmado"

        return {
            **state,
            "status": "ok",
            "etapa": "transferencia_concluida",
            "gravacoes_tabelas_aplicacao": True,
            "origem_preservada": True,
        }

    except Exception:
        if (
            dest is not None
            and state["commit_dados"] == "nao_confirmado"
            and state.get("etapa") != "confirmar_commit"
        ):
            try:
                dest.rollback()
                state["commit_dados"] = "revertido"
            except Exception:
                pass
        raise

    finally:
        if locked:
            try:
                rows(
                    dest,
                    "SELECT RELEASE_LOCK(%s) AS liberado",
                    (lock_name,),
                )
            except Exception:
                pass
        close(dest)
        close(source)