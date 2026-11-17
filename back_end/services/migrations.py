"""Executor de migrações e interface compatível com os scripts existentes.

As exportações antigas permanecem disponíveis. Validar/planejar não aplica DDL;
a escrita só ocorre em run(..., apply=True, expected_database=...).
"""
from __future__ import annotations

from services.contrato_migracoes import (
    CHAVES_004,
    ESTRUTURAS_004,
    FILES,
    FUELS,
    LEDGER_COLUMNS,
    LEDGER_DDL,
    TABLES,
    MigrationError,
    load_migrations,
    split_sql,
)
from services.plano_migracoes import compatibility, make_plan
from services.validacao_migracoes import (
    _column,
    _index,
    _query,
    _type,
    inspect_schema,
    validate_structure,
)

# Compatibilidade para importadores, inicializador Docker e testes existentes.
__all__ = (
    "CHAVES_004", "ESTRUTURAS_004", "FILES", "FUELS", "LEDGER_COLUMNS",
    "LEDGER_DDL", "TABLES", "MigrationError", "load_migrations", "split_sql",
    "compatibility", "make_plan", "inspect_schema", "validate_structure",
    "apply_one", "run",
)


def apply_one(conn, migration):
    version, claimed = migration["versao"], False
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """INSERT INTO schema_migrations
                (versao,sha256,estado,iniciada_em,ultimo_passo)
                VALUES (%s,%s,'em_execucao',UTC_TIMESTAMP(),0)""",
                (version, migration["sha256"]),
            )
        conn.commit()
        claimed = True

        for step, statement in enumerate(
            migration["statements"], 1
        ):
            with conn.cursor() as cursor:
                cursor.execute(statement)
            conn.commit()

            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE schema_migrations "
                    "SET ultimo_passo=%s WHERE versao=%s",
                    (step, version),
                )
            conn.commit()

        with conn.cursor() as cursor:
            validate_structure(
                cursor,
                inspect_schema(cursor),
                version,
            )
            cursor.execute(
                """UPDATE schema_migrations SET estado='aplicada',
                aplicada_em=UTC_TIMESTAMP(),erro_tipo=NULL WHERE versao=%s""",
                (version,),
            )
        conn.commit()

    except Exception as exc:
        try:
            conn.rollback()
            if claimed:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE schema_migrations "
                        "SET estado='falhou',erro_tipo=%s WHERE versao=%s",
                        (type(exc).__name__[:80], version),
                    )
                conn.commit()
        except Exception:
            pass

        raise MigrationError(
            "Execucao interrompida em "
            + version
            + ". DDL pode ter sido aplicado; "
            "conferir o historico antes de repetir."
        ) from None


def run(
    conn,
    migrations,
    *,
    apply=False,
    expected_database=None,
):
    with conn.cursor() as cursor:
        server = compatibility(cursor)
        if (
            (apply and not expected_database)
            or (
                expected_database
                and expected_database != server["banco"]
            )
        ):
            raise MigrationError(
                "--banco deve corresponder exatamente "
                "ao banco conectado."
            )
        plan = make_plan(cursor, migrations)

    report = {
        "status": "ok",
        "modo": "aplicar" if apply else "dry-run",
        **server,
        "migracoes": plan,
        "aplicadas_nesta_execucao": [],
        "ddl_tem_commit_implicito": True,
    }
    if not apply:
        return report

    conn.commit()
    if any(m["estado"] == "pendente" for m in plan):
        with conn.cursor() as cursor:
            cursor.execute(LEDGER_DDL)
        conn.commit()

        for migration in migrations:
            with conn.cursor() as cursor:
                current = make_plan(cursor, migrations)
            conn.commit()

            state = next(
                m["estado"]
                for m in current
                if m["versao"] == migration["versao"]
            )
            if state == "pendente":
                apply_one(conn, migration)
                report["aplicadas_nesta_execucao"].append(
                    migration["versao"]
                )

    with conn.cursor() as cursor:
        report["migracoes"] = make_plan(cursor, migrations)
    return report