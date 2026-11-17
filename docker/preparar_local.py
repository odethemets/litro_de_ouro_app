"""Cria configuracao Docker local sem ler ou alterar o .env da aplicacao."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "docker" / "local"
KEYS = (
    "LDO_MYSQL_ROOT_PASSWORD",
    "LDO_DB_PASSWORD",
    "LDO_SECRET_KEY",
)


def main():
    LOCAL.mkdir(parents=True, exist_ok=True)
    (LOCAL / "certs").mkdir(exist_ok=True)

    ignore = LOCAL / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n!.gitignore\n", encoding="utf-8")

    path = LOCAL / ".env"

    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
        values = dict(
            line.split("=", 1)
            for line in lines
            if line
            and not line.startswith("#")
            and "=" in line
        )

        if any(len(values.get(k, "")) < 32 for k in KEYS):
            raise RuntimeError(
                "Configuracao local incompleta; revisar docker/local/.env. "
                "Nada foi sobrescrito."
            )

        print("Configuracao local existente preservada.")
        return

    body = "# Gerado para o Docker local. Nao compartilhar nem versionar.\n"
    body += "".join(
        k + "=" + secrets.token_hex(32) + "\n"
        for k in KEYS
    )

    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )

    with os.fdopen(
        descriptor,
        "w",
        encoding="utf-8",
        newline="\n",
    ) as stream:
        stream.write(body)

    print(
        "Configuracao criada em docker/local/.env; "
        "nenhum segredo foi exibido."
    )


if __name__ == "__main__":
    main()