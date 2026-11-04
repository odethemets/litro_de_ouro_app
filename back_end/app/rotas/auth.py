# back_end/app/rotas/auth.py

import os
import re
import secrets
import smtplib
import ssl

from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import jwt

from flask import Blueprint, current_app, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

# Imports relativos ao pacote "app".
# Este arquivo deve ser carregado por run.py/Gunicorn, não executado diretamente.
from ..db import get_db_connection
from ..utils.decorator import token_required


auth_bp = Blueprint("auth", __name__)

# A resposta não confirma a existência da conta nem promete entrega do e-mail.
MENSAGEM_SOLICITACAO = (
    "Solicitação recebida. Se houver uma conta para este e-mail, "
    "você poderá receber um código. Se não chegar, confira o endereço "
    "e o spam ou tente novamente em instantes."
)


# =========================================================
# VALIDAÇÃO DOS DADOS
# =========================================================

def _validar_dados(*campos, senha_nova=None):
    """Valida o JSON antes de abrir uma conexão com o banco."""
    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        return None, "Envie um objeto JSON válido."

    for campo in campos:
        valor = dados.get(campo)

        if not isinstance(valor, str) or not valor.strip():
            return None, (
                f"O campo '{campo}' é obrigatório e deve ser texto."
            )

    # O limite corresponde ao VARCHAR(100) mostrado na tabela usuarios.
    email = dados.get("email", "").strip()

    if (
        len(email) > 100
        or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)
    ):
        return None, "Informe um e-mail válido com até 100 caracteres."

    # Copia os dados para normalizar o e-mail sem modificar o objeto original.
    dados = dict(dados, email=email)

    if "codigo" in campos:
        dados["codigo"] = dados["codigo"].strip()

        if not re.fullmatch(r"[0-9]{6}", dados["codigo"]):
            return None, "O código deve conter exatamente 6 dígitos."

    # Aplicado somente ao cadastro e à redefinição.
    # O login continua aceitando senhas antigas menores que seis caracteres.
    if senha_nova:
        senha = dados[senha_nova]

        if not 6 <= len(senha) <= 1024:
            return None, (
                "A nova senha deve ter entre 6 e 1024 caracteres."
            )

    return dados, None


# =========================================================
# CÓDIGOS DE CONFIRMAÇÃO E RECUPERAÇÃO
# =========================================================

def _gerar_codigo():
    """Gera seis dígitos usando um gerador criptograficamente seguro."""
    return str(100000 + secrets.randbelow(900000))


def _atualizar_codigo(cursor, email, finalidade):
    """
    Utiliza somente as colunas existentes.

    Como o banco possui um único token_expiracao, emitir um código
    invalida o da outra finalidade. Apenas a solicitação mais recente
    permanece válida.
    """
    codigo = _gerar_codigo()
    expiracao = datetime.utcnow() + timedelta(minutes=15)

    if finalidade == "recuperacao":
        sql = """
            UPDATE usuarios
            SET token_recuperacao = %s,
                token_verificacao = NULL,
                token_expiracao = %s
            WHERE email = %s
        """
    else:
        sql = """
            UPDATE usuarios
            SET token_verificacao = %s,
                token_recuperacao = NULL,
                token_expiracao = %s
            WHERE email = %s
        """

    cursor.execute(sql, (codigo, expiracao, email))

    return codigo


# =========================================================
# ENVIO DE E-MAIL
# =========================================================

def enviar_email_codigo(destinatario, codigo, tipo="verificacao"):
    # Credenciais somente no ambiente, sem valores padrão no código.
    remetente = os.getenv("EMAIL_REMETENTE")
    senha_app = os.getenv("EMAIL_SENHA_APP")

    if not remetente or not senha_app:
        current_app.logger.error(
            "Credenciais de e-mail não configuradas."
        )
        return False

    assunto = (
        "Litro de Ouro - Código de Acesso"
        if tipo == "verificacao"
        else "Litro de Ouro - Recuperação de Senha"
    )

    mensagem_html = f"""
    <html>
      <body style="
          font-family: Arial, sans-serif;
          color: #333;
          text-align: center;
          padding: 20px;
      ">
        <h2>Litro de Ouro</h2>
        <p>Aqui está o seu código de segurança:</p>
        <h1 style="
            font-size: 32px;
            letter-spacing: 5px;
            color: #F59E0B;
            background: #1E1E1E;
            padding: 15px;
            border-radius: 8px;
            display: inline-block;
        ">
          {codigo}
        </h1>
        <p style="color: #666; font-size: 12px; margin-top: 20px;">
          Este código expira em 15 minutos.
          Ao solicitar outro código, utilize o mais recente.
        </p>
      </body>
    </html>
    """

    try:
        mensagem = MIMEMultipart()
        mensagem["From"] = f"Litro de Ouro <{remetente}>"
        mensagem["To"] = destinatario
        mensagem["Subject"] = assunto
        mensagem.attach(MIMEText(mensagem_html, "html", "utf-8"))

        # O contexto TLS verifica o certificado e a identidade do servidor.
        # O bloco "with" encerra a conexão SMTP ao terminar.
        with smtplib.SMTP(
            "smtp.gmail.com",
            587,
            timeout=10,
        ) as servidor:
            servidor.starttls(context=ssl.create_default_context())
            servidor.login(remetente, senha_app)
            servidor.send_message(mensagem)

        return True

    except Exception as erro:
        # Registra somente o tipo da falha e o status SMTP.
        # Não expõe senha, destinatário, código ou resposta do servidor.
        codigo_smtp = getattr(erro, "smtp_code", None)

        if not isinstance(codigo_smtp, int):
            codigo_smtp = None

        current_app.logger.error(
            "Falha no envio de código por e-mail: "
            "tipo=%s; codigo_smtp=%s",
            type(erro).__name__,
            codigo_smtp,
        )

        return False


# =========================================================
# LOGIN
# =========================================================

@auth_bp.route("/login", methods=["POST"], strict_slashes=False)
def login():
    dados, erro = _validar_dados("email", "senha")

    if erro:
        return jsonify({"error": erro}), 400

    email = dados["email"]
    senha = dados["senha"]

    conn = None

    try:
        conn = get_db_connection()

        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, senha, email_verificado
                FROM usuarios
                WHERE email = %s
                """,
                (email,),
            )
            usuario = cursor.fetchone()

            if not usuario:
                return jsonify({
                    "error": "E-mail ou senha incorretos."
                }), 401

            # A coluna senha permite NULL: isso deve resultar em
            # credenciais inválidas, não em erro interno.
            try:
                senha_valida = (
                    isinstance(usuario["senha"], str)
                    and check_password_hash(
                        usuario["senha"],
                        senha,
                    )
                )
            except (ValueError, TypeError):
                senha_valida = False

            if not senha_valida:
                return jsonify({
                    "error": "E-mail ou senha incorretos."
                }), 401

            if not usuario["email_verificado"]:
                codigo = _atualizar_codigo(
                    cursor,
                    email,
                    "verificacao",
                )
                conn.commit()

                enviado = enviar_email_codigo(
                    email,
                    codigo,
                    "verificacao",
                )

                mensagem = (
                    "Conta não verificada. Enviamos um novo código."
                    if enviado
                    else (
                        "Conta não verificada. Não foi possível enviar "
                        "o código. Tente reenviar em instantes."
                    )
                )

                # Mantém o contrato que abre a tela ValidarCodigo.
                return jsonify({
                    "error": mensagem,
                    "require_validation": True,
                    "email_sent": enviado,
                }), 403

            # Esta chave deve ser carregada na fábrica da aplicação.
            # Não existe fallback para uma chave conhecida.
            segredo = current_app.config["SECRET_KEY"]

            if (
                not isinstance(segredo, str)
                or len(segredo.strip().encode("utf-8")) < 32
                or segredo.strip() == "segredo-padrao-temporario"
            ):
                raise RuntimeError(
                    "SECRET_KEY não configurada corretamente."
                )

            token = jwt.encode(
                {
                    "usuario_id": usuario["id"],
                    "exp": datetime.utcnow() + timedelta(days=7),
                },
                segredo,
                algorithm="HS256",
            )

            return jsonify({
                "message": "Login realizado com sucesso",
                "token": token,
            }), 200

    except Exception:
        current_app.logger.exception("Erro no login.")
        return jsonify({
            "error": "Erro interno ao processar o login."
        }), 500

    finally:
        if conn and conn.open:
            conn.close()


# =========================================================
# CONFIRMAR E-MAIL
# =========================================================

@auth_bp.route(
    "/confirmar-email",
    methods=["POST"],
    strict_slashes=False,
)
def confirmar_email():
    dados, erro = _validar_dados("email", "codigo")

    if erro:
        return jsonify({"error": erro}), 400

    email = dados["email"]
    codigo = dados["codigo"]
    conn = None

    try:
        conn = get_db_connection()

        with conn.cursor() as cursor:
            # Confere e consome o código na mesma atualização.
            # Um código já utilizado deixa de corresponder à condição.
            cursor.execute(
                """
                UPDATE usuarios
                SET email_verificado = 1,
                    token_verificacao = NULL,
                    token_recuperacao = NULL,
                    token_expiracao = NULL
                WHERE email = %s
                  AND token_verificacao = %s
                  AND token_expiracao > %s
                """,
                (email, codigo, datetime.utcnow()),
            )

            if cursor.rowcount != 1:
                return jsonify({
                    "error": "Código inválido ou expirado."
                }), 400

            conn.commit()

            return jsonify({
                "message": "E-mail confirmado com sucesso!"
            }), 200

    except Exception:
        current_app.logger.exception(
            "Erro na confirmação de e-mail."
        )
        return jsonify({"error": "Erro interno."}), 500

    finally:
        if conn and conn.open:
            conn.close()


# =========================================================
# RECUPERAR SENHA
# =========================================================

@auth_bp.route(
    "/recuperar-senha",
    methods=["POST"],
    strict_slashes=False,
)
def recuperar_senha():
    dados, erro = _validar_dados("email")

    if erro:
        return jsonify({"error": erro}), 400

    email = dados["email"]
    conn = None

    try:
        conn = get_db_connection()

        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM usuarios WHERE email = %s",
                (email,),
            )
            usuario = cursor.fetchone()

            if usuario:
                codigo = _atualizar_codigo(
                    cursor,
                    email,
                    "recuperacao",
                )
                conn.commit()

                enviar_email_codigo(
                    email,
                    codigo,
                    "recuperacao",
                )

        # A mesma resposta é usada se a conta não existir ou se o
        # envio falhar. Não afirma que o e-mail foi entregue.
        return jsonify({
            "message": MENSAGEM_SOLICITACAO
        }), 202

    except Exception:
        current_app.logger.exception(
            "Erro na solicitação de recuperação."
        )
        return jsonify({"error": "Erro interno."}), 500

    finally:
        if conn and conn.open:
            conn.close()


# =========================================================
# REDEFINIR SENHA
# =========================================================

@auth_bp.route(
    "/redefinir-senha",
    methods=["POST"],
    strict_slashes=False,
)
def redefinir_senha():
    dados, erro = _validar_dados(
        "email",
        "codigo",
        "nova_senha",
        senha_nova="nova_senha",
    )

    if erro:
        return jsonify({"error": erro}), 400

    email = dados["email"]
    codigo = dados["codigo"]
    nova_senha = dados["nova_senha"]
    conn = None

    try:
        # Continua utilizando o hashing do Werkzeug.
        senha_hash = generate_password_hash(nova_senha)

        conn = get_db_connection()

        with conn.cursor() as cursor:
            # A senha só muda se o código ainda for válido.
            # O código é consumido na mesma atualização.
            cursor.execute(
                """
                UPDATE usuarios
                SET senha = %s,
                    token_recuperacao = NULL,
                    token_verificacao = NULL,
                    token_expiracao = NULL,
                    email_verificado = 1
                WHERE email = %s
                  AND token_recuperacao = %s
                  AND token_expiracao > %s
                """,
                (
                    senha_hash,
                    email,
                    codigo,
                    datetime.utcnow(),
                ),
            )

            if cursor.rowcount != 1:
                return jsonify({
                    "error": "Código inválido ou expirado."
                }), 400

            conn.commit()

            return jsonify({
                "message": "Palavra-passe redefinida com sucesso."
            }), 200

    except Exception:
        current_app.logger.exception(
            "Erro ao redefinir a senha."
        )
        return jsonify({"error": "Erro interno."}), 500

    finally:
        if conn and conn.open:
            conn.close()


# =========================================================
# PERFIL DO USUÁRIO
# =========================================================

@auth_bp.route("/perfil", methods=["GET"], strict_slashes=False)
@token_required
def obter_perfil(current_user_id):
    conn = None

    try:
        conn = get_db_connection()

        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT nome, email, plano, karma,
                       DATE_FORMAT(
                           criado_em,
                           '%%d/%%m/%%Y'
                       ) AS membro_desde
                FROM usuarios
                WHERE id = %s
                """,
                (current_user_id,),
            )
            usuario = cursor.fetchone()

        if not usuario:
            return jsonify({
                "error": "Utilizador não encontrado."
            }), 404

        return jsonify(usuario), 200

    except Exception:
        current_app.logger.exception(
            "Erro ao buscar perfil."
        )
        return jsonify({
            "error": "Erro interno ao buscar os dados."
        }), 500

    finally:
        if conn and conn.open:
            conn.close()


# =========================================================
# CADASTRO
# =========================================================

@auth_bp.route("/cadastro", methods=["POST"], strict_slashes=False)
def cadastro():
    dados, erro = _validar_dados(
        "nome",
        "email",
        "senha",
        senha_nova="senha",
    )

    if erro:
        return jsonify({"error": erro}), 400

    nome = dados["nome"].strip()
    email = dados["email"]
    senha = dados["senha"]
    conn = None

    try:
        conn = get_db_connection()

        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM usuarios WHERE email = %s",
                (email,),
            )

            if cursor.fetchone():
                return jsonify({
                    "error": "Este e-mail já está registado."
                }), 400

            senha_hash = generate_password_hash(senha)
            codigo = _gerar_codigo()
            expiracao = datetime.utcnow() + timedelta(minutes=15)

            cursor.execute(
                """
                INSERT INTO usuarios (
                    nome,
                    email,
                    senha,
                    plano,
                    karma,
                    email_verificado,
                    token_verificacao,
                    token_expiracao
                )
                VALUES (%s, %s, %s, 'gratis', 0, 0, %s, %s)
                """,
                (
                    nome,
                    email,
                    senha_hash,
                    codigo,
                    expiracao,
                ),
            )
            conn.commit()

        enviado = enviar_email_codigo(
            email,
            codigo,
            "verificacao",
        )

        # A conta já existe, mesmo se o SMTP falhar.
        # A interface deverá permitir reenviar o código.
        mensagem = (
            "Conta criada. Verifique o e-mail para confirmar."
            if enviado
            else (
                "Conta criada, mas o envio falhou. "
                "Reenvie o código na tela de verificação."
            )
        )

        return jsonify({
            "message": mensagem,
            "email_sent": enviado,
        }), 201

    except Exception:
        current_app.logger.exception(
            "Erro no cadastro."
        )
        return jsonify({
            "error": "Erro interno ao criar a conta."
        }), 500

    finally:
        if conn and conn.open:
            conn.close()


# =========================================================
# REENVIAR CÓDIGO DE CONFIRMAÇÃO
# =========================================================

@auth_bp.route(
    "/reenviar-codigo",
    methods=["POST"],
    strict_slashes=False,
)
def reenviar_codigo():
    dados, erro = _validar_dados("email")

    if erro:
        return jsonify({"error": erro}), 400

    email = dados["email"]
    conn = None

    try:
        conn = get_db_connection()

        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id
                FROM usuarios
                WHERE email = %s
                  AND email_verificado = 0
                """,
                (email,),
            )
            usuario = cursor.fetchone()

            if usuario:
                codigo = _atualizar_codigo(
                    cursor,
                    email,
                    "verificacao",
                )
                conn.commit()

                enviar_email_codigo(
                    email,
                    codigo,
                    "verificacao",
                )

        # Não recria a conta nem revela seu estado na resposta pública.
        return jsonify({
            "message": (
                "Solicitação recebida. Se houver uma conta pendente "
                "para este e-mail, você poderá receber um novo código. "
                "Se não chegar, confira o spam ou tente novamente "
                "em instantes."
            )
        }), 202

    except Exception:
        current_app.logger.exception(
            "Erro ao solicitar reenvio de código."
        )
        return jsonify({
            "error": "Não foi possível solicitar o código. Tente novamente."
        }), 500

    finally:
        if conn and conn.open:
            conn.close()