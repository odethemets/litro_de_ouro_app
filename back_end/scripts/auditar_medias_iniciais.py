"""Audita médias iniciais sem alterar banco, migrações ou referências."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.auditoria_medias import auditar_medias
from services.database import get_db_connection
from services.migrations import load_migrations


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--banco", required=True)
    parser.add_argument("--relatorio", help="Novo arquivo JSON; não sobrescreve.")
    args = parser.parse_args(argv)
    conn = None
    etapa = "validar_destino_relatorio"
    try:
        destino = Path(args.relatorio) if args.relatorio else None
        if destino is not None and (destino.exists() or destino.suffix.lower() != ".json"):
            raise ValueError("Escolha um arquivo JSON novo.")
        etapa = "carregar_migracoes"
        migracoes = load_migrations(ROOT / "migrations")
        etapa = "abrir_conexao_somente_leitura"
        conn = get_db_connection(read_only=True, time_zone="+00:00")
        etapa = "auditar_medias"
        resultado = auditar_medias(conn, migracoes, banco=args.banco)
        etapa = "gravar_relatorio_local"
        texto = json.dumps(resultado, ensure_ascii=False, indent=2)
        if destino is not None:
            destino.parent.mkdir(parents=True, exist_ok=True)
            with destino.open("x", encoding="utf-8") as arquivo:
                arquivo.write(texto + "\n")
        print(texto)
        return 0
    except Exception as erro:
        print(json.dumps({
            "status": "interrompido", "modo": "somente-leitura",
            "etapa": etapa, "erro_tipo": type(erro).__name__,
            "erro": "Auditoria interrompida; detalhes de conexão omitidos.",
        }, ensure_ascii=False, indent=2))
        return 1
    finally:
        if conn is not None:
            for acao in (conn.rollback, conn.close):
                try:
                    acao()
                except Exception:
                    pass


if __name__ == "__main__":
    raise SystemExit(main())