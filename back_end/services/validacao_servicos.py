"""Validação de estrutura da migração 005, inclusive índices e relações."""
import re

from services.contrato_migracoes import MigrationError

COLUNAS = {
    "id": ("int", False), "usuario_id": ("int", True), "posto_id": ("int", False),
    "combustivel_codigo": ("varchar(32)", False), "chave_cliente": ("char(32)", False),
    "foto_arquivo": ("varchar(64)", False), "foto_sha256": ("char(64)", False),
    "observacao": ("varchar(500)", False), "distancia_m": ("decimal(10,2)", False),
    "precisao_m": ("decimal(10,2)", False), "estado": ("varchar(16)", False),
    "criado_em": ("datetime", False), "revisado_em": ("datetime", True),
    "revisado_por": ("int", True), "motivo": ("varchar(500)", True),
}


def normalizar_check(valor):
    # MySQL pode escapar as aspas do CHECK em information_schema; TiDB pode
    # devolvê-las sem escape. Só normaliza representação, não altera a lógica.
    texto = valor.lower().replace("\\'", "'")
    texto = re.sub(r"_(?:ascii|utf8mb4)(?=')", "", texto)
    return re.sub(r"[\s`()]+", "", texto)


def validar_estrutura(cursor, schema, coluna, indice):
    tabela = "solicitacoes_servicos"
    if str(schema["tables"].get(tabela, "")).lower() != "innodb":
        raise MigrationError("Tabela de solicitações ausente ou engine divergente.")
    if {c for t, c in schema["columns"] if t == tabela} != set(COLUNAS):
        raise MigrationError("Colunas divergentes em solicitacoes_servicos.")
    for nome, (tipo, nulo) in COLUNAS.items():
        coluna(schema, tabela, nome, tipo, nulo)
    for nome in ("combustivel_codigo", "chave_cliente", "foto_arquivo", "foto_sha256", "estado"):
        if schema["columns"][(tabela, nome)]["collation"] != "ascii_bin":
            raise MigrationError("Collation divergente em solicitacoes_servicos." + nome)
    for nome, campos, unico in (
        ("PRIMARY", ("id",), True),
        ("uq_ss_usuario_chave", ("usuario_id", "chave_cliente"), True),
        ("uq_ss_foto", ("foto_arquivo",), True),
        ("idx_ss_estado_id", ("estado", "id"), False),
        ("idx_ss_usuario_id", ("usuario_id", "id"), False),
        ("idx_ss_posto", ("posto_id",), False),
        ("idx_ss_produto", ("combustivel_codigo",), False),
        ("idx_ss_revisor", ("revisado_por",), False),
    ):
        indice(schema, tabela, nome, campos, unico)
    cursor.execute("""SELECT k.COLUMN_NAME AS origem,k.REFERENCED_TABLE_NAME AS destino,
        k.REFERENCED_COLUMN_NAME AS campo,r.DELETE_RULE AS exclusao
        FROM information_schema.KEY_COLUMN_USAGE k
        JOIN information_schema.REFERENTIAL_CONSTRAINTS r
        ON r.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA AND r.TABLE_NAME=k.TABLE_NAME
        AND r.CONSTRAINT_NAME=k.CONSTRAINT_NAME
        WHERE k.TABLE_SCHEMA=DATABASE() AND k.TABLE_NAME=%s""", (tabela,))
    atuais = {(r["origem"], r["destino"], r["campo"], "RESTRICT" if r["exclusao"] == "NO ACTION" else r["exclusao"]) for r in cursor.fetchall()}
    if atuais != {
        ("usuario_id", "usuarios", "id", "SET NULL"),
        ("posto_id", "postos", "id", "CASCADE"),
        ("combustivel_codigo", "combustiveis", "codigo", "RESTRICT"),
        ("revisado_por", "usuarios", "id", "SET NULL"),
    }:
        raise MigrationError("Relações divergentes em solicitacoes_servicos.")
    cursor.execute("""SELECT c.CHECK_CLAUSE AS clausula FROM information_schema.CHECK_CONSTRAINTS c
        JOIN information_schema.TABLE_CONSTRAINTS t
        ON t.CONSTRAINT_SCHEMA=c.CONSTRAINT_SCHEMA AND t.CONSTRAINT_NAME=c.CONSTRAINT_NAME
        WHERE t.TABLE_SCHEMA=DATABASE() AND t.TABLE_NAME=%s AND t.CONSTRAINT_TYPE='CHECK'""", (tabela,))
    clausulas = [normalizar_check(r["clausula"]) for r in cursor.fetchall()]
    if "estadoin'pendente','aprovada','rejeitada'" not in clausulas:
        raise MigrationError("CHECK de estados ausente ou divergente em solicitacoes_servicos.")