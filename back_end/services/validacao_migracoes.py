"""Inspeção e validação da estrutura existente; não executa migrações."""
from __future__ import annotations

import re

from services.contrato_migracoes import (
    CHAVES_004,
    ESTRUTURAS_004,
    FUELS,
    TABLES,
    MigrationError,
)


def _query(cursor, sql, params=None):
    cursor.execute(sql, params)
    return cursor.fetchall()


def inspect_schema(cursor) -> dict:
    marks = ",".join(["%s"] * len(TABLES))
    params = list(TABLES)

    tables = _query(
        cursor,
        f"""SELECT TABLE_NAME AS tabela, ENGINE AS engine
        FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()
        AND TABLE_NAME IN ({marks})""",
        params,
    )

    columns = _query(
        cursor,
        f"""SELECT TABLE_NAME AS tabela, COLUMN_NAME AS coluna,
        COLUMN_TYPE AS tipo, IS_NULLABLE AS nulo, COLLATION_NAME AS collation
        FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE()
        AND TABLE_NAME IN ({marks})""",
        params,
    )

    indexes = _query(
        cursor,
        f"""SELECT TABLE_NAME AS tabela, INDEX_NAME AS indice,
        COLUMN_NAME AS coluna, SEQ_IN_INDEX AS ordem, NON_UNIQUE AS nao_unico
        FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE()
        AND TABLE_NAME IN ({marks})
        ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX""",
        params,
    )

    for row in indexes:
        row["ordem"] = int(row["ordem"])
        row["nao_unico"] = int(row["nao_unico"])
    indexes.sort(
        key=lambda row: (
            row["tabela"],
            row["indice"],
            row["ordem"],
        )
    )

    fks = _query(
        cursor,
        """SELECT k.COLUMN_NAME AS coluna,
        k.REFERENCED_TABLE_NAME AS tabela_referenciada,
        k.REFERENCED_COLUMN_NAME AS coluna_referenciada,
        r.DELETE_RULE AS exclusao, r.UPDATE_RULE AS atualizacao
        FROM information_schema.KEY_COLUMN_USAGE k
        JOIN information_schema.REFERENTIAL_CONSTRAINTS r
          ON r.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA AND r.TABLE_NAME=k.TABLE_NAME
         AND r.CONSTRAINT_NAME=k.CONSTRAINT_NAME
        WHERE k.TABLE_SCHEMA=DATABASE()
        AND k.TABLE_NAME='postos_combustiveis'""",
    )

    return {
        "tables": {
            r["tabela"]: r["engine"]
            for r in tables
        },
        "columns": {
            (r["tabela"], r["coluna"]): r
            for r in columns
        },
        "indexes": indexes,
        "fks": fks,
    }


def _type(value):
    return re.sub(
        r"\b(int|tinyint|bigint)\(\d+\)",
        r"\1",
        value.lower(),
    )


def _column(schema, table, name, kind, nullable):
    row = schema["columns"].get((table, name))
    if (
        not row
        or _type(row["tipo"]) != kind
        or row["nulo"] != ("YES" if nullable else "NO")
    ):
        raise MigrationError(
            "Estrutura inesperada em " + table + "." + name
        )


def _index(schema, table, name, columns, unique=False):
    rows = [
        r
        for r in schema["indexes"]
        if r["tabela"] == table and r["indice"] == name
    ]
    if (
        [r["coluna"] for r in rows] != list(columns)
        or (
            unique
            and any(r["nao_unico"] for r in rows)
        )
    ):
        raise MigrationError(
            "Indice ausente ou divergente: "
            + table + "." + name
        )


def validate_structure(cursor, schema, version):
    if version.startswith("005"):
        from services.validacao_servicos import validar_estrutura
        validar_estrutura(cursor, schema, _column, _index)
        return
    if version.startswith("004"):
        for table, fields in ESTRUTURAS_004.items():
            if str(schema["tables"].get(table, "")).lower() != "innodb":
                raise MigrationError("Engine inesperada em " + table)
            for name, (kind, nullable) in fields.items():
                _column(schema, table, name, kind, nullable)
            pk = ("usuario_id", "posto_id") if table == "favoritos_postos" else ("usuario_id", "combustivel_codigo") if table == "favoritos_combustiveis" else ("usuario_id",) if table == "preferencias_alertas" else ("registo_id",) if table == "eventos_preco" else ("id",)
            _index(schema, table, "PRIMARY", pk, True)
            cursor.execute("""SELECT k.COLUMN_NAME AS origem, k.REFERENCED_TABLE_NAME AS destino,
                k.REFERENCED_COLUMN_NAME AS campo, r.DELETE_RULE AS exclusao
                FROM information_schema.KEY_COLUMN_USAGE k
                JOIN information_schema.REFERENTIAL_CONSTRAINTS r
                ON r.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA AND r.TABLE_NAME=k.TABLE_NAME
                AND r.CONSTRAINT_NAME=k.CONSTRAINT_NAME
                WHERE k.TABLE_SCHEMA=DATABASE() AND k.TABLE_NAME=%s""", (table,))
            recebidas = {(x["origem"], x["destino"], x["campo"], "RESTRICT" if x["exclusao"] == "NO ACTION" else x["exclusao"]) for x in cursor.fetchall()}
            esperadas = {(o, d, "codigo" if d == "combustiveis" else "id", a) for o, d, a in CHAVES_004[table]}
            if recebidas != esperadas:
                raise MigrationError("Chaves estrangeiras divergentes em " + table)
        _index(schema, "historico_karma", "uq_karma_origem", ("usuario_id", "origem"), True)
        _index(schema, "notificacoes", "uq_notificacao_registo", ("usuario_id", "registo_id"), True)
        return
    if version.startswith("003"):
        for name, kind, nullable in (
            ("versao_token", "int", False), ("tentativas_codigo", "int", False),
            ("codigo_emitido_em", "datetime", True), ("falhas_login", "int", False),
            ("login_bloqueado_ate", "datetime", True),
        ):
            _column(schema, "usuarios", name, kind, nullable)
        expected = {
            "usuario_id": ("int", False), "novo_email": ("varchar(100)", False),
            "codigo_hash": ("char(64)", False), "expira_em": ("datetime", False),
            "solicitado_em": ("datetime", False), "tentativas": ("int", False),
        }
        if str(schema["tables"].get("trocas_email", "")).lower() != "innodb":
            raise MigrationError("Engine inesperada em trocas_email.")
        for field, (kind, nullable) in expected.items():
            _column(schema, "trocas_email", field, kind, nullable)
        _index(schema, "trocas_email", "PRIMARY", ("usuario_id",), True)
        cursor.execute("""SELECT k.REFERENCED_TABLE_NAME AS tabela,
            k.REFERENCED_COLUMN_NAME AS coluna, r.DELETE_RULE AS exclusao
            FROM information_schema.KEY_COLUMN_USAGE k
            JOIN information_schema.REFERENTIAL_CONSTRAINTS r
            ON r.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA AND r.TABLE_NAME=k.TABLE_NAME
            AND r.CONSTRAINT_NAME=k.CONSTRAINT_NAME
            WHERE k.TABLE_SCHEMA=DATABASE() AND k.TABLE_NAME='trocas_email'
            AND k.COLUMN_NAME='usuario_id'""")
        if cursor.fetchall() != [{"tabela": "usuarios", "coluna": "id", "exclusao": "CASCADE"}]:
            raise MigrationError("Chave estrangeira de trocas_email divergente.")
        return
    if version.startswith("001"):
        expected = {
            "combustiveis": {
                "codigo": ("varchar(32)", False),
                "nome": ("varchar(50)", False),
                "unidade": ("varchar(8)", False),
            },
            "postos_combustiveis": {
                "posto_id": ("int", False),
                "combustivel_codigo": ("varchar(32)", False),
                "disponivel_osm": ("tinyint", True),
                "osm_verificado_em": ("datetime", True),
                "disponivel_manual": ("tinyint", True),
                "manual_atualizado_em": ("datetime", True),
                "manual_atualizado_por": ("int", True),
            },
        }

        for table, fields in expected.items():
            if str(
                schema["tables"].get(table, "")
            ).lower() != "innodb":
                raise MigrationError(
                    "Tabela ausente ou engine inesperada: " + table
                )

            actual = {
                c
                for t, c in schema["columns"]
                if t == table
            }
            if actual != set(fields):
                raise MigrationError(
                    "Colunas divergentes em " + table
                )
            for name, (kind, nullable) in fields.items():
                _column(schema, table, name, kind, nullable)

        for table, field in (
            ("combustiveis", "codigo"),
            ("postos_combustiveis", "combustivel_codigo"),
        ):
            if (
                schema["columns"][(table, field)]["collation"]
                != "ascii_bin"
            ):
                raise MigrationError(
                    "Collation divergente no codigo de combustivel."
                )

        _index(
            schema, "combustiveis", "PRIMARY",
            ("codigo",), True,
        )
        _index(
            schema, "postos_combustiveis", "PRIMARY",
            ("posto_id", "combustivel_codigo"), True,
        )
        _index(
            schema, "postos_combustiveis", "idx_pc_combustivel",
            ("combustivel_codigo",),
        )
        _index(
            schema, "postos_combustiveis", "idx_pc_responsavel",
            ("manual_atualizado_por",),
        )

        links = {
            (
                r["coluna"],
                r["tabela_referenciada"],
                r["coluna_referenciada"],
            )
            for r in schema["fks"]
            if r["exclusao"] in ("RESTRICT", "NO ACTION")
            and r["atualizacao"] in ("RESTRICT", "NO ACTION")
        }
        if (
            links != {
                ("posto_id", "postos", "id"),
                ("combustivel_codigo", "combustiveis", "codigo"),
                ("manual_atualizado_por", "usuarios", "id"),
            }
            or len(schema["fks"]) != 3
        ):
            raise MigrationError(
                "Chaves estrangeiras de disponibilidade divergentes."
            )

        checks = _query(
            cursor,
            """SELECT CONSTRAINT_NAME AS nome, CHECK_CLAUSE AS clausula
            FROM information_schema.CHECK_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA=DATABASE()
              AND CONSTRAINT_NAME IN (
                'ck_pc_disponivel_osm',
                'ck_pc_disponivel_manual'
              )""",
        )
        clauses = {
            r["nome"]: re.sub(
                r"[`()\s]",
                "",
                r["clausula"].lower(),
            )
            for r in checks
        }
        for field in ("disponivel_osm", "disponivel_manual"):
            if (
                clauses.get("ck_pc_" + field)
                != field + "isnullor" + field + "in0,1"
            ):
                raise MigrationError(
                    "CHECK de disponibilidade ausente ou divergente."
                )

        cursor.execute(
            "SHOW CREATE TABLE postos_combustiveis"
        )
        create_row = cursor.fetchone()
        create_sql = next(
            (
                v
                for k, v in create_row.items()
                if k.lower() == "create table"
            ),
            "",
        )
        if (
            not create_sql
            or "NOT ENFORCED" in create_sql.upper()
        ):
            raise MigrationError(
                "Enforcement dos CHECKs nao foi confirmado."
            )

        rows = _query(
            cursor,
            "SELECT codigo,nome,unidade "
            "FROM combustiveis ORDER BY codigo",
        )
        if {
            r["codigo"]: (r["nome"], r["unidade"])
            for r in rows
        } != FUELS:
            raise MigrationError(
                "Catalogo divergente dos seis combustiveis aprovados."
            )
    else:
        _column(
            schema, "postos", "marca", "varchar(120)", True
        )
        _column(
            schema, "postos", "marca_origem",
            "enum('osm','manual')", True,
        )
        _index(
            schema, "postos", "idx_postos_marca", ("marca",)
        )