"""Envio pelo Resend/HTTPS. Não gera nem grava códigos no banco."""

import json
import logging
import os
import re

from html import escape
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
)

log = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"
TIMEOUT_SEGUNDOS = 10
MAX_RESPOSTA_BYTES = 64 * 1024


class _SemRedirecionamento(HTTPRedirectHandler):
    def redirect_request(
        self, req, fp, code, msg, headers, newurl
    ):
        # Evita encaminhar a chave para outro endereço.
        return None


def enviar_email_codigo(
    destinatario,
    codigo,
    tipo="verificacao",
) -> bool:
    # True significa aceitação pela API, não entrega na caixa.
    chave = os.getenv("RESEND_API_KEY", "").strip()
    remetente = os.getenv("RESEND_FROM", "").strip()

    if (
        not chave
        or not remetente
        or any(c in chave + remetente for c in "\r\n")
    ):
        log.error(
            "Resend: configure RESEND_API_KEY "
            "e RESEND_FROM no backend."
        )
        return False

    if (
        not isinstance(destinatario, str)
        or not destinatario.strip()
    ):
        log.error("Resend: destinatário ausente ou inválido.")
        return False

    if (
        not isinstance(codigo, str)
        or not re.fullmatch(r"[0-9]{6}", codigo)
    ):
        log.error("Resend: código ausente ou inválido.")
        return False

    assunto = (
        "Litro de Ouro - Código de Acesso"
        if tipo == "verificacao"
        else "Litro de Ouro - Recuperação de Senha"
    )

    codigo_html = escape(codigo)

    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333;
                   text-align: center; padding: 20px;">
        <h2>Litro de Ouro</h2>
        <p>Aqui está o seu código de segurança:</p>
        <h1 style="font-size: 32px; letter-spacing: 5px;
                   color: #F59E0B; background: #1E1E1E;
                   padding: 15px; border-radius: 8px;
                   display: inline-block;">
          {codigo_html}
        </h1>
        <p>Este código expira em 15 minutos.</p>
      </body>
    </html>
    """

    payload = {
        "from": remetente,
        "to": [destinatario.strip()],
        "subject": assunto,
        "html": html,
        "text": (
            f"Litro de Ouro\n"
            f"Seu código de segurança: {codigo}\n"
            f"Este código expira em 15 minutos."
        ),
    }

    try:
        requisicao = Request(
            RESEND_URL,
            data=json.dumps(
                payload,
                ensure_ascii=False,
            ).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {chave}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "LitroDeOuro/1.0",
            },
            method="POST",
        )

        # Usa HTTPS com verificação TLS padrão.
        # Não repete automaticamente um envio de resultado incerto.
        with build_opener(
            _SemRedirecionamento()
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
                "Resend: resposta inesperada; status_http=%s",
                status,
            )
            return False

        corpo = json.loads(dados)

        if (
            not isinstance(corpo, dict)
            or not isinstance(corpo.get("id"), str)
            or not corpo["id"].strip()
        ):
            log.error(
                "Resend: resposta sem identificador de aceitação."
            )
            return False

        log.info(
            "Resend: envio aceito pela API; status_http=%s",
            status,
        )
        return True

    except HTTPError as erro:
        erro.close()

        # Não registra o corpo, que pode conter dados sensíveis.
        log.error(
            "Resend: envio recusado; status_http=%s",
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
        log.error(
            "Resend: falha no envio; tipo=%s",
            type(erro).__name__,
        )
        return False


# Mantém as funções que já existiam no projeto.
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