"""Envio pelo Gmail via Google Apps Script/HTTPS."""

import json
import logging
import os
import re
import uuid

from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
)

log = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = 10
MAX_RESPOSTA_BYTES = 64 * 1024

ERROS_CONHECIDOS = {
    "CONFIGURACAO_AUSENTE",
    "REQUISICAO_INVALIDA",
    "NAO_AUTORIZADO",
    "DADOS_INVALIDOS",
    "OCUPADO",
    "COTA_ESGOTADA",
    "FALHA_NO_ENVIO",
}


class _RespostaGoogle(HTTPRedirectHandler):
    def redirect_request(
        self, req, fp, code, msg, headers, newurl
    ):
        # O Google entrega a resposta do script por redirecionamento.
        # Seguimos apenas o endereço de resposta oficial, usando GET.
        # O POST contendo o segredo não é reenviado.
        destino = urlsplit(newurl)

        if (
            code not in (302, 303)
            or destino.scheme != "https"
            or destino.hostname != "script.googleusercontent.com"
            or destino.port not in (None, 443)
            or destino.username
            or destino.password
        ):
            return None

        return Request(
            newurl,
            headers={
                "Accept": "application/json",
                "User-Agent": "LitroDeOuro/1.0",
            },
            method="GET",
        )


def _configuracao():
    url = os.getenv("GOOGLE_SCRIPT_URL", "").strip()
    segredo = os.getenv("GOOGLE_SCRIPT_SECRET", "").strip()

    if len(segredo) < 32:
        raise ValueError("Segredo ausente ou curto.")

    destino = urlsplit(url)

    if (
        destino.scheme != "https"
        or destino.hostname != "script.google.com"
        or destino.port not in (None, 443)
        or destino.username
        or destino.password
        or destino.query
        or destino.fragment
        or not re.fullmatch(
            r"/macros/s/[A-Za-z0-9_-]+/exec",
            destino.path,
        )
    ):
        raise ValueError(
            "Use a URL de produção /exec do Apps Script."
        )

    return url, segredo


def enviar_email_codigo(
    destinatario,
    codigo,
    tipo="verificacao",
) -> bool:
    """
    True significa que MailApp aceitou o envio.
    Não comprova entrega na caixa de entrada.
    """
    try:
        url, segredo = _configuracao()

    except ValueError:
        log.error(
            "Gmail: configure GOOGLE_SCRIPT_URL (/exec) "
            "e GOOGLE_SCRIPT_SECRET (mínimo 32 caracteres)."
        )
        return False

    if (
        not isinstance(destinatario, str)
        or len(destinatario.strip()) > 100
        or not re.fullmatch(
            r"[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+",
            destinatario.strip(),
        )
        or not isinstance(codigo, str)
        or not re.fullmatch(r"[0-9]{6}", codigo)
        or tipo not in ("verificacao", "recuperacao")
    ):
        log.error("Gmail: dados de envio inválidos.")
        return False

    identificador = uuid.uuid4().hex

    payload = {
        "token": segredo,
        "destinatario": destinatario.strip(),
        "codigo": codigo,
        "tipo": tipo,
        "request_id": identificador,
    }

    try:
        requisicao = Request(
            url,
            data=json.dumps(
                payload,
                ensure_ascii=False,
            ).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "LitroDeOuro/1.0",
            },
            method="POST",
        )

        with build_opener(
            _RespostaGoogle()
        ).open(
            requisicao,
            timeout=TIMEOUT_SEGUNDOS,
        ) as resposta:
            status = resposta.status
            dados = resposta.read(MAX_RESPOSTA_BYTES + 1)

        if (
            not 200 <= status < 300
            or len(dados) > MAX_RESPOSTA_BYTES
        ):
            log.error(
                "Gmail: resposta inesperada; status_http=%s",
                status,
            )
            return False

        corpo = json.loads(dados)

        if (
            isinstance(corpo, dict)
            and corpo.get("ok") is True
            and corpo.get("request_id") == identificador
        ):
            log.info(
                "Gmail: serviço confirmou aceitação do envio."
            )
            return True

        erro = (
            corpo.get("erro")
            if isinstance(corpo, dict)
            else None
        )

        seguro = (
            erro
            if isinstance(erro, str)
            and erro in ERROS_CONHECIDOS
            else "RESPOSTA_INVALIDA"
        )

        log.error(
            "Gmail: envio não confirmado; motivo=%s",
            seguro,
        )
        return False

    except HTTPError as erro:
        erro.close()

        log.error(
            "Gmail: falha HTTP; status_http=%s. "
            "Confira a publicação do Apps Script.",
            erro.code,
        )
        return False

    except (
        URLError,
        TimeoutError,
        OSError,
        HTTPException,
        ValueError,
        TypeError,
    ) as erro:
        # Não repete automaticamente: o envio pode ter acontecido
        # antes da perda da resposta.
        log.error(
            "Gmail: envio não confirmado; tipo=%s",
            type(erro).__name__,
        )
        return False


# Mantém as funções existentes e a compatibilidade com auth.py.
def enviar_email_confirmacao(
    destinatario: str,
    codigo_confirmacao: str,
) -> bool:
    return enviar_email_codigo(
        destinatario,
        codigo_confirmacao,
        "verificacao",
    )


def enviar_email_recuperacao(
    destinatario: str,
    codigo_recuperacao: str,
) -> bool:
    return enviar_email_codigo(
        destinatario,
        codigo_recuperacao,
        "recuperacao",
    )