# back_end/app/rotas/auth.py

import re
import secrets

from datetime import datetime, timedelta

import jwt

from flask import Blueprint, current_app, jsonify, request
from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)

from ..db import get_db_connection
from ..utils.decorator import token_required

from services.email_services import (
    enviar_email_codigo as enviar_email_resend,
)


auth_bp = Blueprint("auth", __name__)

# Resposta neutra: não confirma se a conta existe
# nem promete que o e-mail foi entregue.
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

    # Limite correspondente ao VARCHAR(100) da tabela usuarios.
    email = dados.get("email", "").strip()

    if (
        len(email) > 100
        or not re.fullmatch(
            r"[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+",
            email,
        )
    ):
        return None, "Informe um e-mail válido com até 100 caracteres."

    dados = dict(dados, email=email.lower())

    if "nome" in campos and (
        len(dados["nome"].strip()) > 100
        or any(ord(c) < 32 for c in dados["nome"])
    ):
        return None, (
            "Informe um nome com até 100 caracteres, "
            "sem caracteres de controle."
        )

    if "senha" in campos and len(dados["senha"]) > 1024:
        return None, "Senha inválida."

    if "codigo" in campos:
        dados["codigo"] = dados["codigo"].strip()

        if not re.fullmatch(r"[0-9]{6}", dados["codigo"]):
            return None, "O código deve conter exatamente 6 dígitos."

    # Aplicado somente ao cadastro e à redefinição.
    # O login aceita senhas antigas menores que seis caracteres.
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
    """Gera seis dígitos com um gerador criptograficamente seguro."""
    return str(100000 + secrets.randbelow(900000))


def _atualizar_codigo(cursor, email, finalidade):
    agora = datetime.utcnow()

    cursor.execute(
        "SELECT codigo_emitido_em FROM usuarios WHERE email=%s FOR UPDATE",
        (email,),
    )
    usuario = cursor.fetchone()

    if not usuario or (
        usuario["codigo_emitido_em"]
        and (agora - usuario["codigo_emitido_em"]).total_seconds() < 60
    ):
        return None

    codigo = _gerar_codigo()

    verificacao = codigo if finalidade == "verificacao" else None
    recuperacao = codigo if finalidade == "recuperacao" else None

    cursor.execute(
        """
        UPDATE usuarios
        SET token_verificacao=%s,
            token_recuperacao=%s,
            token_expiracao=%s,
            tentativas_codigo=0,
            codigo_emitido_em=%s
        WHERE email=%s
        """,
        (
            verificacao,
            recuperacao,
            agora + timedelta(minutes=15),
            agora,
            email,
        ),
    )

    return codigo


def _consumir_codigo(cursor, email, codigo, finalidade):
    cursor.execute(
        """
        SELECT id,
               token_verificacao,
               token_recuperacao,
               token_expiracao,
               tentativas_codigo
        FROM usuarios
        WHERE email=%s
        FOR UPDATE
        """,
        (email,),
    )

    usuario = cursor.fetchone()

    if (
        not usuario
        or not usuario["token_expiracao"]
        or usuario["token_expiracao"] <= datetime.utcnow()
        or usuario["tentativas_codigo"] >= 5
    ):
        return None

    campo = (
        "token_recuperacao"
        if finalidade == "recuperacao"
        else "token_verificacao"
    )
    esperado = usuario[campo]

    if not esperado or not secrets.compare_digest(esperado, codigo):
        cursor.execute(
            """
            UPDATE usuarios
            SET tentativas_codigo=tentativas_codigo+1
            WHERE id=%s
            """,
            (usuario["id"],),
        )
        return None

    return usuario["id"]


# =========================================================
# ENVIO DE E-MAIL PELO SERVIÇO CONFIGURADO
# =========================================================

def enviar_email_codigo(destinatario, codigo, tipo="verificacao"):
    """
    Mantém a interface utilizada pelas rotas.
    O envio HTTPS fica centralizado em services/email_services.py.
    """
    return enviar_email_resend(destinatario, codigo, tipo)


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
                SELECT id,
                       senha,
                       email_verificado,
                       versao_token,
                       falhas_login,
                       login_bloqueado_ate
                FROM usuarios
                WHERE email = %s
                FOR UPDATE
                """,
                (email,),
            )

            usuario = cursor.fetchone()

            if not usuario:
                return jsonify({
                    "error": "E-mail ou senha incorretos."
                }), 401

            if (
                usuario["login_bloqueado_ate"]
                and usuario["login_bloqueado_ate"] > datetime.utcnow()
            ):
                return jsonify(
                    error=(
                        "E-mail ou senha incorretos. "
                        "Aguarde antes de tentar novamente."
                    )
                ), 401

            # Senha NULL ou hash inválido resultam em
            # credenciais inválidas, sem erro interno.
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
                falhas = usuario["falhas_login"] + 1

                bloqueio = (
                    datetime.utcnow() + timedelta(minutes=15)
                    if falhas >= 5
                    else None
                )

                cursor.execute(
                    """
                    UPDATE usuarios
                    SET falhas_login=%s,
                        login_bloqueado_ate=%s
                    WHERE id=%s
                    """,
                    (
                        0 if bloqueio else falhas,
                        bloqueio,
                        usuario["id"],
                    ),
                )
                conn.commit()

                return jsonify({
                    "error": "E-mail ou senha incorretos."
                }), 401

            cursor.execute(
                """
                UPDATE usuarios
                SET falhas_login=0,
                    login_bloqueado_ate=NULL
                WHERE id=%s
                """,
                (usuario["id"],),
            )

            if not usuario["email_verificado"]:
                codigo = _atualizar_codigo(
                    cursor,
                    email,
                    "verificacao",
                )
                conn.commit()

                enviado = bool(codigo) and enviar_email_codigo(
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

                return jsonify({
                    "error": mensagem,
                    "require_validation": True,
                    "email_sent": enviado,
                }), 403

            conn.commit()

            # Deve ser a mesma chave usada pelo decorator JWT.
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
                    "ver": usuario["versao_token"],
                    "iat": datetime.utcnow(),
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
            usuario_id = _consumir_codigo(
                cursor,
                email,
                codigo,
                "verificacao",
            )

            if usuario_id is None:
                conn.commit()
                return jsonify(
                    error="Código inválido ou expirado."
                ), 400

            cursor.execute(
                """
                UPDATE usuarios
                SET email_verificado=1,
                    token_verificacao=NULL,
                    token_recuperacao=NULL,
                    token_expiracao=NULL,
                    tentativas_codigo=0
                WHERE id=%s
                """,
                (usuario_id,),
            )

            conn.commit()

            return jsonify({
                "message": "E-mail confirmado com sucesso!"
            }), 200

    except Exception:
        current_app.logger.exception(
            "Erro na confirmação de e-mail."
        )

        return jsonify({
            "error": "Erro interno."
        }), 500

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

                if codigo:
                    enviar_email_codigo(
                        email,
                        codigo,
                        "recuperacao",
                    )

        # Mantém a resposta neutra, inclusive quando o envio falha.
        return jsonify({
            "message": MENSAGEM_SOLICITACAO
        }), 202

    except Exception:
        current_app.logger.exception(
            "Erro na solicitação de recuperação."
        )

        return jsonify({
            "error": "Erro interno."
        }), 500

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
        senha_hash = generate_password_hash(nova_senha)

        conn = get_db_connection()

        with conn.cursor() as cursor:
            usuario_id = _consumir_codigo(
                cursor,
                email,
                codigo,
                "recuperacao",
            )

            if usuario_id is None:
                conn.commit()
                return jsonify(
                    error="Código inválido ou expirado."
                ), 400

            cursor.execute(
                """
                UPDATE usuarios
                SET senha=%s,
                    token_recuperacao=NULL,
                    token_verificacao=NULL,
                    token_expiracao=NULL,
                    email_verificado=1,
                    versao_token=versao_token+1,
                    tentativas_codigo=0,
                    falhas_login=0,
                    login_bloqueado_ate=NULL
                WHERE id=%s
                """,
                (senha_hash, usuario_id),
            )

            conn.commit()

            return jsonify({
                "message": "Palavra-passe redefinida com sucesso."
            }), 200

    except Exception:
        current_app.logger.exception(
            "Erro ao redefinir a senha."
        )

        return jsonify({
            "error": "Erro interno."
        }), 500

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
                SELECT id, nome, email, plano, karma,
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
                    token_expiracao,
                    codigo_emitido_em
                )
                VALUES (%s, %s, %s, 'gratis', 0, 0, %s, %s, %s)
                """,
                (
                    nome,
                    email,
                    senha_hash,
                    codigo,
                    expiracao,
                    datetime.utcnow(),
                ),
            )
            conn.commit()

        enviado = enviar_email_codigo(
            email,
            codigo,
            "verificacao",
        )

        # A conta permanece criada se o envio falhar.
        # A interface permite solicitar outro código.
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

                if codigo:
                    enviar_email_codigo(
                        email,
                        codigo,
                        "verificacao",
                    )

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
            "error": (
                "Não foi possível solicitar o código. "
                "Tente novamente."
            )
        }), 500

    finally:
        if conn and conn.open:
            conn.close()