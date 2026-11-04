# back_end/services/email_services.py

import os
import smtplib
import ssl

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

from flask import current_app


def _obter_credenciais():
    # Não existem credenciais padrão no código.
    remetente = os.getenv("EMAIL_REMETENTE")
    senha_app = os.getenv("EMAIL_SENHA_APP")

    return remetente, senha_app


def _enviar_email(destinatario: str, assunto: str, html: str) -> bool:
    """
    Centraliza o transporte SMTP.

    As funções públicas de confirmação e recuperação são preservadas.
    """
    remetente, senha_app = _obter_credenciais()

    if not remetente or not senha_app:
        current_app.logger.error(
            "Credenciais de e-mail não configuradas."
        )
        return False

    try:
        mensagem = MIMEMultipart()
        mensagem["From"] = f"Litro de Ouro <{remetente}>"
        mensagem["To"] = destinatario
        mensagem["Subject"] = assunto
        mensagem.attach(MIMEText(html, "html", "utf-8"))

        # Verifica o certificado e a identidade do servidor SMTP.
        contexto_tls = ssl.create_default_context()

        # Encerra a conexão mesmo quando ocorre uma falha.
        with smtplib.SMTP(
            "smtp.gmail.com",
            587,
            timeout=10,
        ) as servidor:
            servidor.starttls(context=contexto_tls)
            servidor.login(remetente, senha_app)
            servidor.send_message(mensagem)

        return True

    except Exception:
        # Não registrar destinatário, credenciais, código ou conteúdo
        # de exceções SMTP que possam carregar informações sensíveis.
        current_app.logger.error(
            "Falha no envio de e-mail."
        )
        return False


def enviar_email_confirmacao(
    destinatario: str,
    codigo_confirmacao: str,
) -> bool:
    # Evita interpretar como HTML um valor recebido por esta função.
    codigo_seguro = escape(str(codigo_confirmacao))

    assunto = "Confirmação de Cadastro - Litro de Ouro"

    html = f"""
    <div style="
        font-family: Arial, sans-serif;
        max-width: 600px;
        margin: auto;
        padding: 20px;
        border: 1px solid #ddd;
        border-radius: 10px;
    ">
        <h2 style="color: #d79b00; text-align: center;">
            Bem-vindo ao Litro de Ouro!
        </h2>

        <p>Olá,</p>

        <p>
            Falta muito pouco para começar a economizar
            e ajudar a comunidade.
        </p>

        <p>
            Utilize o código de confirmação abaixo
            no aplicativo para ativar a sua conta:
        </p>

        <div style="text-align: center; margin: 30px 0;">
            <span style="
                font-size: 20px;
                font-weight: bold;
                background-color: #f4f4f4;
                padding: 10px 20px;
                border-radius: 5px;
                word-break: break-all;
            ">
                {codigo_seguro}
            </span>
        </div>

        <p style="font-size: 12px; color: #777;">
            Se não se cadastrou no Litro de Ouro,
            ignore este e-mail.
        </p>
    </div>
    """

    return _enviar_email(
        destinatario,
        assunto,
        html,
    )


def enviar_email_recuperacao(
    destinatario: str,
    codigo_recuperacao: str,
) -> bool:
    codigo_seguro = escape(str(codigo_recuperacao))

    assunto = "Recuperação de Senha - Litro de Ouro"

    html = f"""
    <div style="
        font-family: Arial, sans-serif;
        max-width: 600px;
        margin: auto;
        padding: 20px;
        border: 1px solid #ddd;
        border-radius: 10px;
    ">
        <h2 style="color: #d79b00; text-align: center;">
            Litro de Ouro
        </h2>

        <p>Olá,</p>

        <p>
            Recebemos uma solicitação para redefinir
            a sua senha.
        </p>

        <p>
            Utilize o código de recuperação abaixo
            na aplicação:
        </p>

        <div style="text-align: center; margin: 30px 0;">
            <span style="
                font-size: 20px;
                font-weight: bold;
                background-color: #f4f4f4;
                padding: 10px 20px;
                border-radius: 5px;
                word-break: break-all;
            ">
                {codigo_seguro}
            </span>
        </div>

        <p style="font-size: 12px; color: #777;">
            Se não solicitou esta alteração,
            ignore este e-mail.
        </p>
    </div>
    """

    return _enviar_email(
        destinatario,
        assunto,
        html,
    )