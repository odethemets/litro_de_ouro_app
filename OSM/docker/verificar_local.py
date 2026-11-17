"""Confere TLS, dados e API local. Nao registra precos nem limpa o banco."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent),
)

from inicializar_banco import local_connection


def api(path, payload=None, token=None):
    headers = {
        "Accept": "application/json",
    }

    if token:
        headers["Authorization"] = "Bearer " + token

    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    request = Request(
        "http://127.0.0.1:5000" + path,
        data=data,
        headers=headers,
    )

    with urlopen(request, timeout=5) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--saude",
        action="store_true",
        help="Usado pelo healthcheck.",
    )
    args = parser.parse_args()

    conn = local_connection(read_only=True)

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 AS ok")
            assert cursor.fetchone()["ok"] == 1

            report = {
                "status": "ok",
                "tls_verificado": True,
                "banco": "litro_de_ouro_dev",
            }

            if not args.saude:
                counts = {}

                for table in (
                    "postos",
                    "usuarios",
                    "registos_preco",
                    "votos_registos",
                ):
                    cursor.execute(
                        "SELECT COUNT(*) AS n FROM `"
                        + table
                        + "`"
                    )
                    counts[table] = cursor.fetchone()["n"]

                report["contagens_atuais"] = counts

        assert api("/").get("status") == "online"

        if not args.saude:
            stations = api(
                "/postos?lat=-7.11&lng=-34.86"
            )

            assert (
                isinstance(stations, list)
                and any(
                    p["nome"].startswith("[TESTE]")
                    for p in stations
                )
            )

            auth = api(
                "/auth/login",
                {
                    "email": "dev@litro.local",
                    "senha": "DockerLocal123!",
                },
            )

            assert isinstance(auth.get("token"), str)

            profile = api(
                "/auth/perfil",
                token=auth["token"],
            )

            report.update(
                api_raiz=True,
                listagem_postos=True,
                login_ficticio=True,
                perfil_recebido=isinstance(profile, dict),
            )

        print(
            json.dumps(report, ensure_ascii=False)
        )

    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    try:
        main()

    except Exception as exc:
        print(json.dumps({
            "status": "falha_verificacao_local",
            "tipo": type(exc).__name__,
        }))
        raise SystemExit(1)