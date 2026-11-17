"""Política CORS e saúde do backend, sem executar migrações."""
import os
from pathlib import Path
import re
from threading import Lock
import time
from urllib.parse import urlsplit

from flask import jsonify
from flask_cors import CORS

from services.contrato_migracoes import load_migrations

ROOT = Path(__file__).resolve().parents[1]


# Produção exige origens HTTPS exatas.
def origens_permitidas(ambiente):
    perfil = ambiente.get("APP_ENV", "local").strip().lower()

    if perfil not in {"local", "test", "production"}:
        raise ValueError(
            "APP_ENV deve ser local, test ou production."
        )

    texto = ambiente.get("CORS_ORIGINS", "").strip()

    if not texto:
        if perfil == "production":
            raise ValueError(
                "Configure CORS_ORIGINS em produção."
            )
        return ["*"]

    valores = [v.strip() for v in texto.split(",")]

    if len(valores) > 20 or any(not v for v in valores):
        raise ValueError(
            "CORS_ORIGINS contém origens vazias "
            "ou excede 20 origens."
        )

    if "*" in valores:
        if perfil == "production" or valores != ["*"]:
            raise ValueError(
                "Coringa CORS permitido somente sozinho "
                "em modo local/test."
            )
        return valores

    resultado = []

    for valor in valores:
        try:
            url = urlsplit(valor)
            porta = url.port
            host = url.hostname

            if (
                url.scheme not in {"http", "https"}
                or not host
                or url.username is not None
                or url.password is not None
                or url.path not in {"", "/"}
                or any(
                    c in valor
                    for c in ("*", "\\", "?", "#", "%")
                )
                or any(
                    c.isspace() or ord(c) < 32 or ord(c) == 127
                    for c in valor
                )
                or (
                    perfil == "production"
                    and url.scheme != "https"
                )
            ):
                raise ValueError

            host = host.encode("idna").decode("ascii").lower()
            autoridade = "[" + host + "]" if ":" in host else host
            porta_padrao = {"http": 80, "https": 443}[url.scheme]

            if porta is not None and porta != porta_padrao:
                autoridade += ":" + str(porta)

            origem = url.scheme + "://" + autoridade

        except (ValueError, UnicodeError):
            raise ValueError(
                "CORS_ORIGINS exige origens válidas "
                "sem caminho ou credenciais."
            ) from None

        if origem not in resultado:
            resultado.append(origem)

    return resultado


def conectar_leitura(**opcoes):
    from services.database import get_db_connection

    return get_db_connection(**opcoes)


# Cache por processo, compartilhado pelas sondagens concorrentes.
class Prontidao:
    def __init__(
        self,
        esperadas,
        conectar,
        relogio=time.monotonic,
    ):
        self.esperadas = {
            m["versao"]: m["sha256"]
            for m in esperadas
        }
        self.conectar = conectar
        self.relogio = relogio
        self.erro_tipo = None
        self._resultado = None
        self._valido_ate = 0
        self._lock = Lock()

    def consultar(self):
        with self._lock:
            if (
                self._resultado is not None
                and self.relogio() < self._valido_ate
            ):
                return self._resultado

            self._resultado = self._consultar_banco()
            self._valido_ate = self.relogio() + 5

            return self._resultado

    def _consultar_banco(self):
        conn, pronto = None, False
        self.erro_tipo = None

        try:
            conn = self.conectar(
                read_only=True,
                time_zone="+00:00",
            )

            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT versao,sha256,estado "
                    "FROM schema_migrations ORDER BY versao"
                )
                linhas = cursor.fetchall()

            atuais = {r["versao"]: r for r in linhas}

            pronto = (
                bool(self.esperadas)
                and len(linhas) == len(atuais) == len(self.esperadas)
                and all(
                    versao in atuais
                    and atuais[versao]["sha256"] == sha
                    and atuais[versao]["estado"] == "aplicada"
                    for versao, sha in self.esperadas.items()
                )
            )

            if not pronto:
                self.erro_tipo = "MigracoesIncompativeis"

        except Exception as erro:
            self.erro_tipo = type(erro).__name__

        finally:
            if conn is not None:
                for acao in (conn.rollback, conn.close):
                    try:
                        acao()
                    except Exception as erro:
                        pronto = False
                        if self.erro_tipo is None:
                            self.erro_tipo = type(erro).__name__

        return pronto


# Substitui a chamada CORS anterior da fábrica Flask.
def configurar_web(app, ambiente=None, conectar=None):
    if any(
        getattr(funcao, "__module__", "").startswith("flask_cors.")
        for funcao in app.after_request_funcs.get(None, [])
    ):
        raise ValueError(
            "Substitua a chamada CORS anterior "
            "por configurar_web(app)."
        )

    origens = origens_permitidas(
        os.environ if ambiente is None else ambiente
    )
    esperadas = load_migrations(ROOT / "migrations")

    prontidao = Prontidao(
        esperadas,
        conectar or conectar_leitura,
    )
    app.extensions["ldo_prontidao"] = prontidao

    # Domínios são tratados como origens exatas.
    regras = ["*"] if origens == ["*"] else [
        re.compile(r"\A" + re.escape(origem) + r"\Z")
        for origem in origens
    ]

    CORS(
        app,
        resources={r"/*": {"origins": regras}},
        methods=[
            "GET",
            "HEAD",
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
            "OPTIONS",
        ],
        allow_headers=["Authorization", "Content-Type"],
        supports_credentials=False,
        always_send=False,
        vary_header=True,
        max_age=600,
    )

    def resposta(status, codigo):
        r = jsonify({"status": status})
        r.status_code = codigo
        r.headers["Cache-Control"] = "no-store"
        return r

    def live():
        return resposta("ok", 200)

    def ready():
        pronto = prontidao.consultar()
        return resposta(
            "pronto" if pronto else "indisponivel",
            200 if pronto else 503,
        )

    app.add_url_rule(
        "/health/live",
        "ldo_live",
        live,
        methods=["GET"],
    )
    app.add_url_rule(
        "/health/ready",
        "ldo_ready",
        ready,
        methods=["GET"],
    )