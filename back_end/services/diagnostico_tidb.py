"""Provas de GET_LOCK, transacao, CHECK e FK em tabelas descartaveis do destino."""
from __future__ import annotations

import uuid

from services.transferencia_banco import (
    TransferError,
    close,
    connect,
    execute,
    q,
    rows,
    server,
)


def expect_error(conn, sql, expected):
    try:
        execute(conn, sql)
    except Exception as exc:
        if exc.args and exc.args[0] in expected:
            return
        raise TransferError(
            "A prova retornou um erro diferente do esperado."
        ) from exc

    raise TransferError(
        "A operacao que deveria ser rejeitada foi aceita pelo destino."
    )


def count(conn, table):
    return rows(
        conn,
        "SELECT COUNT(*) AS n FROM " + q(table),
    )[0]["n"]


def lock(conn, name):
    return rows(
        conn,
        "SELECT GET_LOCK(%s,1) AS resultado",
        (name,),
    )[0]["resultado"]


def release(conn, name):
    return rows(
        conn,
        "SELECT RELEASE_LOCK(%s) AS resultado",
        (name,),
    )[0]["resultado"]


def check_locks(config, a, b):
    name = "ldo_diag_" + uuid.uuid4().hex
    third = None

    try:
        if lock(a, name) != 1:
            raise TransferError(
                "GET_LOCK nao adquiriu o lock de diagnostico."
            )

        a.rollback()
        if lock(b, name) != 0:
            raise TransferError(
                "GET_LOCK nao excluiu uma segunda sessao."
            )

        if (
            release(a, name) != 1
            or lock(b, name) != 1
            or release(b, name) != 1
        ):
            raise TransferError(
                "GET_LOCK/RELEASE_LOCK nao preservaram "
                "a propriedade esperada."
            )

        third = connect(config, read_only=True)
        if lock(third, name) != 1:
            raise TransferError(
                "GET_LOCK falhou na prova de encerramento de sessao."
            )
        close(third)
        third = None

        if lock(b, name) != 1 or release(b, name) != 1:
            raise TransferError(
                "Fechar a sessao nao liberou o lock no destino."
            )

        return {
            "exclusao_entre_sessoes": True,
            "sobrevive_rollback": True,
            "liberacao_explicita": True,
            "liberacao_ao_fechar": True,
            "timeout_segundos": 1,
        }

    finally:
        close(third)
        for conn in (a, b):
            try:
                release(conn, name)
            except Exception:
                pass


def diagnose(config, *, write=False):
    a = b = None
    created = []
    phase = "conectar_destino"
    original_error = None
    cleanup_errors = []
    result = None

    try:
        a = connect(config, read_only=not write)
        b = connect(config, read_only=not write)
        info = server(a)

        if (
            "tidb" not in info["versao"].lower()
            or int(info["fk"]) != 1
        ):
            raise TransferError(
                "O perfil DESTINO deve ser TiDB "
                "com foreign_key_checks ativo."
            )

        result = {
            "status": "ok",
            "banco": info["banco"],
            "versao": info["versao"],
            "tls_verificado": True,
            "testes_de_escrita": write,
        }

        phase = "verificar_check"
        check = rows(
            a,
            "SHOW GLOBAL VARIABLES LIKE 'tidb_enable_check_constraint'",
        )
        value = (
            next(
                (
                    v
                    for k, v in check[0].items()
                    if k.lower() == "value"
                ),
                None,
            )
            if check
            else None
        )
        result["check_habilitado"] = (
            None
            if value is None
            else str(value).lower() in ("on", "1")
        )

        if write and result["check_habilitado"] is False:
            raise TransferError(
                "Habilite CHECK no destino pelo DBeaver: "
                "SET GLOBAL tidb_enable_check_constraint=ON."
            )

        phase = "testar_get_lock"
        result["get_lock"] = check_locks(config, a, b)

        if write:
            phase = "criar_tabelas_diagnostico"
            suffix = uuid.uuid4().hex[:16]
            parent = "__ldo_p_" + suffix
            child = "__ldo_c_" + suffix

            a.rollback()
            b.rollback()

            execute(
                a,
                "CREATE TABLE "
                + q(parent)
                + " (id INT PRIMARY KEY,valor INT NOT NULL,"
                "CHECK(valor>=0)) ENGINE=InnoDB",
            )
            created.append(parent)

            execute(
                a,
                "CREATE TABLE "
                + q(child)
                + " (id INT PRIMARY KEY,pai_id INT NOT NULL,"
                "FOREIGN KEY(pai_id) REFERENCES "
                + q(parent)
                + "(id) ON DELETE CASCADE) ENGINE=InnoDB",
            )
            created.append(child)
            a.commit()

            phase = "testar_rollback"
            a.begin()
            execute(
                a,
                "INSERT INTO " + q(parent) + " VALUES(1,1)",
            )
            execute(
                a,
                "INSERT INTO " + q(child) + " VALUES(1,1)",
            )
            a.rollback()

            if count(a, parent) or count(a, child):
                raise TransferError(
                    "Rollback nao reverteu as duas tabelas de teste."
                )
            a.rollback()

            phase = "testar_commit_visibilidade"
            a.begin()
            execute(
                a,
                "INSERT INTO " + q(parent) + " VALUES(1,1)",
            )
            execute(
                a,
                "INSERT INTO " + q(child) + " VALUES(1,1)",
            )
            a.commit()
            b.rollback()

            if count(b, parent) != 1 or count(b, child) != 1:
                raise TransferError(
                    "Commit nao ficou visivel para outra conexao."
                )
            b.rollback()

            phase = "testar_foreign_key"
            a.begin()
            try:
                expect_error(
                    a,
                    "INSERT INTO " + q(child) + " VALUES(2,99999)",
                    {1452},
                )
            finally:
                a.rollback()

            phase = "testar_check"
            a.begin()
            try:
                expect_error(
                    a,
                    "INSERT INTO " + q(parent) + " VALUES(2,-1)",
                    {3819},
                )
            finally:
                a.rollback()

            phase = "testar_cascade_e_rollback"
            a.begin()
            execute(
                a,
                "DELETE FROM " + q(parent) + " WHERE id=1",
            )
            if count(a, child) != 0:
                raise TransferError(
                    "ON DELETE CASCADE nao foi efetivo na tabela de teste."
                )
            a.rollback()

            if count(a, parent) != 1 or count(a, child) != 1:
                raise TransferError(
                    "Rollback nao restaurou o cascade de teste."
                )
            a.rollback()

            phase = "testar_select_for_update"
            a.begin()
            rows(
                a,
                "SELECT valor FROM "
                + q(parent)
                + " WHERE id=1 FOR UPDATE",
            )
            b.begin()

            try:
                expect_error(
                    b,
                    "SELECT valor FROM "
                    + q(parent)
                    + " WHERE id=1 FOR UPDATE NOWAIT",
                    {1205, 3572},
                )
            finally:
                b.rollback()
                a.rollback()

            result["integridade"] = {
                "rollback": True,
                "commit_visivel": True,
                "fk_rejeita_orfao": True,
                "check_rejeita_invalido": True,
                "cascade_transacional": True,
                "select_for_update_exclusivo": True,
            }
        else:
            result["integridade"] = (
                "pendente: executar --testar-escrita "
                "para provar FK, CHECK e transacoes"
            )

    except Exception as exc:
        original_error = exc
        try:
            exc.etapa_diagnostico = phase
        except (AttributeError, TypeError):
            pass

    finally:
        for conn in (a, b):
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass

        for table in reversed(created):
            try:
                execute(a, "DROP TABLE " + q(table))
                a.commit()
            except Exception:
                cleanup_errors.append(table)

        close(b)
        close(a)

    if cleanup_errors:
        raise TransferError(
            "Conferir tabelas de diagnostico "
            "que nao puderam ser removidas: "
            + ", ".join(cleanup_errors)
        ) from original_error

    if original_error is not None:
        raise original_error

    if result is not None:
        result["tabelas_diagnostico_removidas"] = bool(write)
    return result