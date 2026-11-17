"""Compatibilidade do servidor e plano baseado no histórico de migrações."""
from __future__ import annotations

import re

from services.contrato_migracoes import (
    ESTRUTURAS_004,
    LEDGER_COLUMNS,
    TABLES,
    MigrationError,
)
from services.validacao_migracoes import (
    _column,
    _index,
    _query,
    inspect_schema,
    validate_structure,
)


def compatibility(cursor):
    cursor.execute(
        "SELECT DATABASE() AS banco, VERSION() AS versao, "
        "@@foreign_key_checks AS fk"
    )
    server = cursor.fetchone()
    if int(server["fk"]) != 1:
        raise MigrationError(
            "foreign_key_checks deve estar ativo."
        )

    version = str(server["versao"])
    if "tidb" in version.lower():
        found = re.search(
            r"tidb-v?(\d+)\.(\d+)\.(\d+)",
            version,
            re.I,
        )
        if (
            not found
            or tuple(map(int, found.groups())) < (7, 2, 0)
        ):
            raise MigrationError(
                "Confirmar uma versao TiDB com suporte a FK e CHECK."
            )

        cursor.execute(
            "SHOW VARIABLES LIKE 'tidb_enable_check_constraint'"
        )
        row = cursor.fetchone()
        if row and str(
            next(
                v
                for k, v in row.items()
                if k.lower() == "value"
            )
        ).lower() not in ("1", "on"):
            raise MigrationError(
                "Enforcement de CHECK do TiDB nao esta habilitado; "
                "revisar a instancia."
            )
    else:
        found = re.match(
            r"(\d+)\.(\d+)\.(\d+)",
            version,
        )
        if (
            "mariadb" in version.lower()
            or not found
            or tuple(map(int, found.groups())) < (8, 0, 16)
        ):
            raise MigrationError(
                "Destino deve ser MySQL 8.0.16+ ou TiDB compativel; "
                "revisar versao."
            )

    return {
        "banco": server["banco"],
        "versao_servidor": version,
    }


def make_plan(cursor, migrations):
    schema = inspect_schema(cursor)
    for table in TABLES[:4]:
        if str(
            schema["tables"].get(table, "")
        ).lower() != "innodb":
            raise MigrationError(
                "Tabela base ausente ou engine inesperada: " + table
            )

    for table in ("postos", "usuarios"):
        _column(schema, table, "id", "int", False)

    ledger = {}
    if "schema_migrations" in schema["tables"]:
        if str(
            schema["tables"]["schema_migrations"]
        ).lower() != "innodb":
            raise MigrationError(
                "Engine inesperada em schema_migrations."
            )

        names = {
            c
            for t, c in schema["columns"]
            if t == "schema_migrations"
        }
        if names != LEDGER_COLUMNS:
            raise MigrationError(
                "schema_migrations possui estrutura desconhecida."
            )

        for field, kind, nullable in (
            ("versao", "varchar(96)", False),
            ("sha256", "char(64)", False),
            ("estado", "varchar(16)", False),
            ("iniciada_em", "datetime", False),
            ("aplicada_em", "datetime", True),
            ("ultimo_passo", "int unsigned", False),
            ("erro_tipo", "varchar(80)", True),
        ):
            _column(
                schema, "schema_migrations",
                field, kind, nullable,
            )

        _index(
            schema, "schema_migrations",
            "PRIMARY", ("versao",), True,
        )

        ledger = {
            r["versao"]: r
            for r in _query(
                cursor,
                "SELECT versao,sha256,estado,ultimo_passo "
                "FROM schema_migrations ORDER BY versao",
            )
        }

    if set(ledger) - {m["versao"] for m in migrations}:
        raise MigrationError(
            "Banco possui migracoes desconhecidas "
            "por esta versao da ferramenta."
        )

    result, pending_seen = [], False
    for migration in migrations:
        version = migration["versao"]
        row = ledger.get(version)

        if row:
            if row["sha256"] != migration["sha256"]:
                raise MigrationError(
                    "Checksum divergente: "
                    + version
                    + ". Restaure o arquivo original."
                )
            if row["estado"] != "aplicada":
                raise MigrationError(
                    "Migracao parcial ou em execucao: "
                    + version
                    + ". Exige revisao manual."
                )
            if pending_seen:
                raise MigrationError(
                    "Historico de migracoes fora de ordem."
                )

            validate_structure(cursor, schema, version)
            state = "aplicada"
        else:
            pending_seen = True
            if version.startswith("004"):
                partial = any(t in schema["tables"] for t in ESTRUTURAS_004)
            elif version.startswith("003"):
                partial = "trocas_email" in schema["tables"] or any(
                    ("usuarios", field) in schema["columns"] for field in (
                        "versao_token", "tentativas_codigo", "codigo_emitido_em",
                        "falhas_login", "login_bloqueado_ate"))
            elif version.startswith("001"):
                partial = any(
                    t in schema["tables"]
                    for t in (
                        "combustiveis",
                        "postos_combustiveis",
                    )
                )
            else:
                partial = any(
                    ("postos", c) in schema["columns"]
                    for c in ("marca", "marca_origem")
                )
                partial = partial or any(
                    r["tabela"] == "postos"
                    and r["indice"] == "idx_postos_marca"
                    for r in schema["indexes"]
                )

            if partial:
                raise MigrationError(
                    "Estrutura sem registro de migracao: "
                    + version
                    + ". Nao sera adotada automaticamente."
                )
            state = "pendente"

        result.append({
            "versao": version,
            "arquivo": migration["arquivo"],
            "sha256": migration["sha256"],
            "estado": state,
            "passos": len(migration["statements"]),
        })
    return result