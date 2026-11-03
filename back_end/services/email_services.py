import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import current_app

def _obter_credenciais():
    remetente = os.getenv("EMAIL_REMETENTE", "litrodeourooficial@gmail.com")
    senha_app = os.getenv("EMAIL_SENHA_APP", "qugsurxrqbgptkwq")
    return remetente, senha_app

def enviar_email_confirmacao(destinatario: str, codigo_confirmacao: str) -> bool:
    remetente, senha_app = _obter_credenciais()

    if not remetente or not senha_app:
        current_app.logger.error("ERRO: Credenciais de e-mail ausentes")
        return False

    assunto = "Confirmação de Cadastro - Litro de Ouro"
    
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
        <h2 style="color: #d79b00; text-align: center;">Bem-vindo ao Litro de Ouro!</h2>
        <p>Olá,</p>
        <p>Falta muito pouco para começar a economizar e ajudar a comunidade.</p>
        <p>Utilize o código de confirmação abaixo no aplicativo para ativar a sua conta:</p>
        <div style="text-align: center; margin: 30px 0;">
            <span style="font-size: 20px; font-weight: bold; background-color: #f4f4f4; padding: 10px 20px; border-radius: 5px; word-break: break-all;">
                {codigo_confirmacao}
            </span>
        </div>
        <p style="font-size: 12px; color: #777;">Se não se cadastrou no Litro de Ouro, ignore este e-mail.</p>
    </div>
    """

    msg = MIMEMultipart()
    msg['From'] = f"Litro de Ouro <{remetente}>"
    msg['To'] = destinatario
    msg['Subject'] = assunto
    msg.attach(MIMEText(html, 'html'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
        server.starttls()
        server.login(remetente, senha_app)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        current_app.logger.exception(f"Falha ao enviar e-mail de confirmação para {destinatario}: {str(e)}")
        return False

def enviar_email_recuperacao(destinatario: str, codigo_recuperacao: str) -> bool:
    remetente, senha_app = _obter_credenciais()

    if not remetente or not senha_app:
        current_app.logger.error("ERRO: Credenciais de e-mail ausentes")
        return False

    assunto = "Recuperação de Senha - Litro de Ouro"
    
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
        <h2 style="color: #d79b00; text-align: center;">Litro de Ouro</h2>
        <p>Olá,</p>
        <p>Recebemos uma solicitação para redefinir a sua senha.</p>
        <p>Utilize o código de recuperação abaixo na aplicação:</p>
        <div style="text-align: center; margin: 30px 0;">
            <span style="font-size: 20px; font-weight: bold; background-color: #f4f4f4; padding: 10px 20px; border-radius: 5px; word-break: break-all;">
                {codigo_recuperacao}
            </span>
        </div>
        <p style="font-size: 12px; color: #777;">Se não solicitou esta alteração, ignore este e-mail.</p>
    </div>
    """

    msg = MIMEMultipart()
    msg['From'] = f"Litro de Ouro <{remetente}>"
    msg['To'] = destinatario
    msg['Subject'] = assunto
    msg.attach(MIMEText(html, 'html'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
        server.starttls()
        server.login(remetente, senha_app)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        current_app.logger.exception(f"Falha ao enviar e-mail de recuperação para {destinatario}: {str(e)}")
        return False