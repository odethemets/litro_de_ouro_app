"""Valida a migração 005 sem depender do JOIN de CHECKs do TiDB."""
import re

from services.contrato_migracoes import MigrationError

COLUNAS = {
    "id": ("int", False),
    "usuario_id": ("int", True),
    "posto_id": ("int", False),
    "combustivel_codigo": ("varchar(32)", False),
    "chave_cliente": ("char(32)", False),
    "foto_arquivo": ("varchar(64)", False),
    "foto_sha256": ("char(64)", False),
    "observacao": ("varchar(500)", False),
    "distancia_m": ("decimal(10,2)", False),
    "precisao_m": ("decimal(10,2)", False),
    "estado": ("varchar(16)", False),
    "criado_em": ("datetime", False),
    "revisado_em": ("datetime", True),
    "revisado_por": ("int", True),
    "motivo": ("varchar(500)", True),
}
INDICES = (
    ("PRIMARY", ("id",), True),
    ("uq_ss_usuario_chave", ("usuario_id", "chave_cliente"), True),
    ("uq_ss_foto", ("foto_arquivo",), True),
    ("idx_ss_estado_id", ("estado", "id"), False),
    ("idx_ss_usuario_id", ("usuario_id", "id"), False),
    ("idx_ss_posto", ("posto_id",), False),
    ("idx_ss_produto", ("combustivel_codigo",), False),
    ("idx_ss_revisor", ("revisado_por",), False),
)
CHECK_ESPERADO = "estadoin'pendente','aprovada','rejeitada'"


def normalizar_check(valor):
    # Os escapes externos são representação de metadados do MySQL.
    texto = valor.replace("\\'", "'")
    partes = re.split(r"('(?:''|[^'])*')", texto)

    for i in range(0, len(partes), 2):
        trecho = partes[i].lower()
        trecho = re.sub(r"_(?:ascii|utf8mb4)\s*$", "", trecho)
        partes[i] = re.sub(r"[\s`()]+", "", trecho)

    # Mantém os literais intactos: ascii_bin distingue maiúsculas e espaços.
    return "".join(partes)


def _check_no_ddl(sql):
    inicio = re.search(
        r"\bCONSTRAINT\s+`?ck_ss_estado`?\s+CHECK\s*\(", sql, re.I
    )
    if not inicio:
        raise MigrationError("CHECK ck_ss_estado não vinculado à tabela.")

    offset = inicio.end() - 1
    tokens = re.finditer(
        r"'(?:''|\\.|[^'\\])*'|`(?:``|[^`])*`|[()]|[^'`()]+",
        sql[offset:], re.S,
    )
    nivel = 0

    for token in tokens:
        if token.group() == "(":
            nivel += 1
        elif token.group() == ")":
            nivel -= 1
            if nivel == 0:
                fim = offset + token.end()
                if re.match(r"\s*NOT\s+ENFORCED\b", sql[fim:], re.I):
                    raise MigrationError(
                        "CHECK ck_ss_estado não está enforced."
                    )
                return sql[offset:fim]

    raise MigrationError("Declaração de CHECK incompleta.")


def validar_estrutura(cursor, schema, coluna, indice):
    tabela = "solicitacoes_servicos"

    if str(schema["tables"].get(tabela, "")).lower() != "innodb":
        raise MigrationError(
            "Tabela de solicitações ausente ou engine divergente."
        )

    if {c for t, c in schema["columns"] if t == tabela} != set(COLUNAS):
        raise MigrationError("Colunas divergentes em solicitacoes_servicos.")

    for nome, (tipo, nulo) in COLUNAS.items():
        coluna(schema, tabela, nome, tipo, nulo)

    for nome in (
        "combustivel_codigo", "chave_cliente", "foto_arquivo",
        "foto_sha256", "estado",
    ):
        if schema["columns"][(tabela, nome)]["collation"] != "ascii_bin":
            raise MigrationError(
                "Collation divergente em " + tabela + "." + nome
            )

    for nome, campos, unico in INDICES:
        indice(schema, tabela, nome, campos, unico)

    cursor.execute(
        """SELECT k.COLUMN_NAME AS origem,
                  k.REFERENCED_TABLE_NAME AS destino,
                  k.REFERENCED_COLUMN_NAME AS campo,
                  r.DELETE_RULE AS exclusao
           FROM information_schema.KEY_COLUMN_USAGE k
           JOIN information_schema.REFERENTIAL_CONSTRAINTS r
             ON r.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA
            AND r.TABLE_NAME=k.TABLE_NAME
            AND r.CONSTRAINT_NAME=k.CONSTRAINT_NAME
           WHERE k.TABLE_SCHEMA=DATABASE() AND k.TABLE_NAME=%s""",
        (tabela,),
    )
    atuais = {
        (
            r["origem"], r["destino"], r["campo"],
            "RESTRICT" if r["exclusao"] == "NO ACTION" else r["exclusao"],
        )
        for r in cursor.fetchall()
    }
    if atuais != {
        ("usuario_id", "usuarios", "id", "SET NULL"),
        ("posto_id", "postos", "id", "CASCADE"),
        ("combustivel_codigo", "combustiveis", "codigo", "RESTRICT"),
        ("revisado_por", "usuarios", "id", "SET NULL"),
    }:
        raise MigrationError(
            "Relações divergentes em solicitacoes_servicos."
        )

    # A consulta direta funciona no TiDB observado; o JOIN anterior ficou vazio.
    cursor.execute(
        """SELECT CHECK_CLAUSE AS clausula
           FROM information_schema.CHECK_CONSTRAINTS
           WHERE CONSTRAINT_SCHEMA=DATABASE() AND CONSTRAINT_NAME=%s""",
        ("ck_ss_estado",),
    )
    checks = cursor.fetchall()

    if (
        len(checks) != 1
        or normalizar_check(checks[0]["clausula"]) != CHECK_ESPERADO
    ):
        raise MigrationError(
            "CHECK de estados ausente ou divergente em " + tabela
        )

    # Confirma vínculo e enforcement na própria tabela.
    cursor.execute("SHOW CREATE TABLE solicitacoes_servicos")
    row = cursor.fetchone() or {}
    sql = next(
        (v for k, v in row.items() if k.lower() == "create table"),
        "",
    )
    if (
        not isinstance(sql, str)
        or normalizar_check(_check_no_ddl(sql)) != CHECK_ESPERADO
    ):
        raise MigrationError(
            "CHECK de estados divergente no SHOW CREATE TABLE."
        )