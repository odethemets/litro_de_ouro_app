"""Executa uma rodada da fila; não instala agendamento nem envia push."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.database import get_db_connection
from services.atividade_alertas import processar_pendentes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--banco", required=True)
    parser.add_argument("--limite", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.limite <= 1000:
        parser.error("limite deve ser entre 1 e 1000")
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS banco")
            if cursor.fetchone()["banco"] != args.banco:
                parser.error("O banco conectado difere do destino informado")
        conn.rollback()
        print(f"Eventos processados: {processar_pendentes(conn, args.limite)}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
