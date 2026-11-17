"""Relatorios locais: escrita atomica e sem serializar credenciais."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path


def json_default(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError("Tipo nao permitido no relatorio.")


def emit_report(report: dict, destination: str | None = None) -> None:
    body = json.dumps(
        report,
        ensure_ascii=False,
        indent=2,
        default=json_default,
    )
    if destination:
        path = Path(destination)
        if path.suffix.lower() != ".json":
            raise ValueError("O relatorio deve usar extensao .json.")
        if path.exists():
            raise FileExistsError(
                "O relatorio ja existe; escolha outro nome."
            )

        path.parent.mkdir(parents=True, exist_ok=True)
        name = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=".relatorio-",
                suffix=".tmp",
                delete=False,
            ) as stream:
                name = stream.name
                stream.write(body + "\n")
                stream.flush()
                os.fsync(stream.fileno())

            # Nao sobrescreve arquivos, inclusive em corrida entre processos.
            os.link(name, path)
        finally:
            if name and os.path.exists(name):
                os.unlink(name)
    print(body)