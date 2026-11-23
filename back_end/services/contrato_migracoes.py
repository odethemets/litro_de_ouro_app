"""Contrato das migrações: arquivos, estruturas esperadas e leitura do SQL."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path


class MigrationError(RuntimeError):
    pass


FILES = (
    "001_catalogo_disponibilidade.sql",
    "002_marcas_postos.sql",
    "003_gestao_conta.sql",
    "004_atividade_alertas.sql",
    "005_solicitacoes_servicos.sql",
)


TABLES = (
    "postos",
    "usuarios",
    "registos_preco",
    "votos_registos",
    "combustiveis",
    "postos_combustiveis",
    "schema_migrations",
    "trocas_email",
    "favoritos_postos",
    "favoritos_combustiveis",
    "preferencias_alertas",
    "historico_karma",
    "eventos_preco",
    "notificacoes",
    "solicitacoes_servicos",
)


ESTRUTURAS_004 = {
    "favoritos_postos": {
        "usuario_id": ("int", False),
        "posto_id": ("int", False),
        "criado_em": ("datetime", False),
    },
    "favoritos_combustiveis": {
        "usuario_id": ("int", False),
        "combustivel_codigo": ("varchar(32)", False),
        "criado_em": ("datetime", False),
    },
    "preferencias_alertas": {
        "usuario_id": ("int", False),
        "ativo": ("tinyint", False),
        "somente_quedas": ("tinyint", False),
        "intervalo_minutos": ("int", False),
    },
    "historico_karma": {
        "id": ("bigint", False),
        "usuario_id": ("int", False),
        "origem": ("varchar(100)", False),
        "motivo": ("varchar(100)", False),
        "pontos": ("int", False),
        "saldo_apos": ("int", False),
        "registo_id": ("int", True),
        "criado_em": ("datetime", False),
    },
    "eventos_preco": {
        "registo_id": ("int", False),
        "preco_anterior": ("decimal(5,2)", True),
        "criado_em": ("datetime", False),
        "processado_em": ("datetime", True),
    },
    "notificacoes": {
        "id": ("bigint", False),
        "usuario_id": ("int", False),
        "registo_id": ("int", False),
        "posto_id": ("int", False),
        "combustivel_codigo": ("varchar(32)", False),
        "preco_anterior": ("decimal(5,2)", True),
        "preco_novo": ("decimal(5,2)", False),
        "criado_em": ("datetime", False),
        "lida_em": ("datetime", True),
    },
}


CHAVES_004 = {
    "favoritos_postos": [
        ("usuario_id", "usuarios", "CASCADE"),
        ("posto_id", "postos", "CASCADE"),
    ],
    "favoritos_combustiveis": [
        ("usuario_id", "usuarios", "CASCADE"),
        ("combustivel_codigo", "combustiveis", "RESTRICT"),
    ],
    "preferencias_alertas": [
        ("usuario_id", "usuarios", "CASCADE"),
    ],
    "historico_karma": [
        ("usuario_id", "usuarios", "CASCADE"),
        ("registo_id", "registos_preco", "SET NULL"),
    ],
    "eventos_preco": [
        ("registo_id", "registos_preco", "CASCADE"),
    ],
    "notificacoes": [
        ("usuario_id", "usuarios", "CASCADE"),
        ("registo_id", "registos_preco", "CASCADE"),
        ("posto_id", "postos", "CASCADE"),
        ("combustivel_codigo", "combustiveis", "RESTRICT"),
    ],
}


FUELS = {
    "gasolina_comum": ("Gasolina Comum", "L"),
    "gasolina_aditivada": ("Gasolina Aditivada", "L"),
    "etanol": ("Etanol", "L"),
    "diesel": ("Diesel", "L"),
    "gnv": ("GNV", "m³"),
    "recarga_eletrica": ("Recarga Elétrica", "kWh"),
}


LEDGER_COLUMNS = {
    "aplicada_em",
    "erro_tipo",
    "estado",
    "iniciada_em",
    "sha256",
    "ultimo_passo",
    "versao",
}


LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
 versao VARCHAR(96) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 estado VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 iniciada_em DATETIME NOT NULL,
 aplicada_em DATETIME NULL,
 ultimo_passo INT UNSIGNED NOT NULL DEFAULT 0,
 erro_tipo VARCHAR(80) NULL,
 PRIMARY KEY (versao)
) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
"""


def split_sql(source: str) -> list[str]:
    """Reconhece strings/identificadores e comentarios; nao aceita procedimentos."""
    output, part = [], []
    quote, i = None, 0

    while i < len(source):
        c = source[i]
        if quote:
            part.append(c)
            if c == "\\" and i + 1 < len(source):
                i += 1
                part.append(source[i])
            elif c == quote:
                if i + 1 < len(source) and source[i + 1] == quote:
                    i += 1
                    part.append(source[i])
                else:
                    quote = None
        elif c in "'\"`":
            quote = c
            part.append(c)
        elif source.startswith("--", i) or c == "#":
            end = source.find("\n", i)
            i = len(source) if end < 0 else end
            part.append(" ")
            continue
        elif source.startswith("/*", i):
            if source.startswith("/*!", i):
                raise MigrationError(
                    "Comentarios executaveis nao sao permitidos."
                )
            end = source.find("*/", i + 2)
            if end < 0:
                raise MigrationError("Comentario SQL nao terminado.")
            i = end + 2
            part.append(" ")
            continue
        elif c == ";":
            if "".join(part).strip():
                output.append("".join(part).strip())
            part = []
        else:
            part.append(c)
        i += 1

    if quote:
        raise MigrationError("String SQL nao terminada.")
    if "".join(part).strip():
        output.append("".join(part).strip())
    if not output:
        raise MigrationError("Migracao vazia.")
    return output


def load_migrations(folder: Path) -> list[dict]:
    result = []
    allowed = (
        (
            r"CREATE\s+TABLE\s+`?combustiveis`?\s*\(",
            r"INSERT\s+INTO\s+`?combustiveis`?\s*\(",
            r"CREATE\s+TABLE\s+`?postos_combustiveis`?\s*\(",
        ),
        (
            r"ALTER\s+TABLE\s+`?postos`?\s+ADD\s+COLUMN\b",
            r"ALTER\s+TABLE\s+`?postos`?\s+ADD\s+KEY\b",
        ),
        (
            r"ALTER\s+TABLE\s+`?usuarios`?\s+ADD\s+COLUMN\b",
            r"CREATE\s+TABLE\s+`?trocas_email`?\s*\(",
        ),
        (
            r"CREATE\s+TABLE\s+favoritos_postos\s*\(",
            r"CREATE\s+TABLE\s+favoritos_combustiveis\s*\(",
            r"CREATE\s+TABLE\s+preferencias_alertas\s*\(",
            r"CREATE\s+TABLE\s+historico_karma\s*\(",
            r"INSERT\s+INTO\s+historico_karma\b",
            r"CREATE\s+TABLE\s+eventos_preco\s*\(",
            r"CREATE\s+TABLE\s+notificacoes\s*\(",
        ),
    )

    allowed += ((r"CREATE\s+TABLE\s+solicitacoes_servicos\s*\(",),)

    for name, patterns in zip(FILES, allowed):
        text = (folder / name).read_text(encoding="utf-8-sig")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        statements = split_sql(text)

        if len(statements) != len(patterns) or any(
            not re.match(p, s, re.I)
            for p, s in zip(patterns, statements)
        ):
            raise MigrationError(
                "Conteudo inesperado no arquivo " + name
            )

        result.append({
            "versao": name[:-4],
            "arquivo": name,
            "sha256": hashlib.sha256(
                text.encode("utf-8")
            ).hexdigest(),
            "statements": statements,
        })
    return result