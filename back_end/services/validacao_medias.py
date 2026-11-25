"""Validação da estrutura da migração 006."""

from services.contrato_migracoes import MigrationError


COLUNAS = {
    "posto_id": "int",
    "combustivel_codigo": "varchar(32)",
    "preco": "decimal(5,2)",
    "municipio_referencia": "varchar(100)",
    "uf_referencia": "char(2)",
    "periodo_inicio": "date",
    "periodo_fim": "date",
    "amostra": "int unsigned",
    "fonte_sha256": "char(64)",
    "snapshot_sha256": "char(64)",
    "criado_em": "datetime",
}


def validar_estrutura(cursor, schema, coluna, indice):
    tabela = "referencias_medias_iniciais"

    engine = str(schema["tables"].get(tabela, "")).lower()

    if engine != "innodb":
        raise MigrationError(
            "Tabela de médias ausente ou engine divergente."
        )

    colunas_atuais = {
        nome
        for nome_tabela, nome in schema["columns"]
        if nome_tabela == tabela
    }

    if colunas_atuais != set(COLUNAS):
        raise MigrationError(
            "Colunas divergentes em " + tabela
        )

    for nome, tipo in COLUNAS.items():
        coluna(
            schema,
            tabela,
            nome,
            tipo,
            False,
        )

    campos_ascii = (
        "combustivel_codigo",
        "uf_referencia",
        "fonte_sha256",
        "snapshot_sha256",
    )

    for nome in campos_ascii:
        collation = schema["columns"][
            (tabela, nome)
        ]["collation"]

        if collation != "ascii_bin":
            raise MigrationError(
                "Collation divergente em "
                + tabela
                + "."
                + nome
            )

    indice(
        schema,
        tabela,
        "PRIMARY",
        ("posto_id", "combustivel_codigo"),
        True,
    )

    indice(
        schema,
        tabela,
        "idx_rmi_combustivel",
        ("combustivel_codigo",),
    )

    cursor.execute(
        """
        SELECT
            k.COLUMN_NAME AS origem,
            k.REFERENCED_TABLE_NAME AS destino,
            k.REFERENCED_COLUMN_NAME AS campo,
            r.DELETE_RULE AS exclusao
        FROM information_schema.KEY_COLUMN_USAGE k
        JOIN information_schema.REFERENTIAL_CONSTRAINTS r
          ON r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA
         AND r.TABLE_NAME = k.TABLE_NAME
         AND r.CONSTRAINT_NAME = k.CONSTRAINT_NAME
        WHERE k.TABLE_SCHEMA = DATABASE()
          AND k.TABLE_NAME = %s
        """,
        (tabela,),
    )

    atuais = {
        (
            registro["origem"],
            registro["destino"],
            registro["campo"],
            (
                "RESTRICT"
                if registro["exclusao"] == "NO ACTION"
                else registro["exclusao"]
            ),
        )
        for registro in cursor.fetchall()
    }

    esperadas = {
        (
            "posto_id",
            "postos",
            "id",
            "CASCADE",
        ),
        (
            "combustivel_codigo",
            "combustiveis",
            "codigo",
            "RESTRICT",
        ),
    }

    if atuais != esperadas:
        raise MigrationError(
            "Relações divergentes em " + tabela
        )