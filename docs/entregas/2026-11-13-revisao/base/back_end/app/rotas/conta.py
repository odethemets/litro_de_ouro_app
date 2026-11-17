"""Gestão da conta autenticada. Códigos e senhas nunca aparecem na resposta."""

import hashlib
import hmac
import re
import secrets

from datetime import datetime, timedelta

import pymysql

from flask import Blueprint, current_app, jsonify, request
from werkzeug.security import check_password_hash

from app.db import get_db_connection
from app.utils.decorator import token_required
from services.email_services import enviar_email_codigo


conta_bp = Blueprint("conta", __name__)


def _hash_codigo(usuario_id, email, codigo):
    corpo = f"troca-email:{usuario_id}:{email}:{codigo}".encode()

    return hmac.new(
        current_app.config["SECRET_KEY"].encode(),
        corpo,
        hashlib.sha256,
    ).hexdigest()


def _senha_confere(usuario, senha):
    try:
        return (
            isinstance(senha, str)
            and 0 < len(senha) <= 1024
            and isinstance(usuario.get("senha"), str)
            and check_password_hash(usuario["senha"], senha)
        )

    except (ValueError, TypeError):
        return False


def _autorizar_senha(conn, cursor, usuario, senha):
    agora = datetime.utcnow()

    if (
        usuario["login_bloqueado_ate"]
        and usuario["login_bloqueado_ate"] > agora
    ):
        return False

    if _senha_confere(usuario, senha):
        cursor.execute(
            """
            UPDATE usuarios
            SET falhas_login=0,
                login_bloqueado_ate=NULL
            WHERE id=%s
            """,
            (usuario["id"],),
        )
        return True

    falhas = usuario["falhas_login"] + 1

    bloqueio = (
        agora + timedelta(minutes=15)
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

    return False


def _executar(usuario_id, acao):
    conn = None

    try:
        conn = get_db_connection()

        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id,
                       nome,
                       email,
                       senha,
                       falhas_login,
                       login_bloqueado_ate
                FROM usuarios
                WHERE id=%s
                FOR UPDATE
                """,
                (usuario_id,),
            )

            usuario = cursor.fetchone()

            if not usuario:
                return jsonify(
                    error="Conta removida.",
                    code="ACCOUNT_DELETED",
                ), 401

            return acao(conn, cursor, usuario)

    except pymysql.IntegrityError:
        if conn is not None:
            conn.rollback()

        return jsonify(
            error="Não foi possível concluir. Confira os dados e tente novamente."
        ), 409

    except Exception:
        if conn is not None:
            conn.rollback()

        current_app.logger.exception("Falha na gestão da conta")

        return jsonify(
            error=(
                "Não foi possível confirmar a alteração. "
                "Atualize os dados antes de repetir."
            )
        ), 500

    finally:
        if conn is not None:
            conn.close()


@conta_bp.route("/nome", methods=["PATCH"], strict_slashes=False)
@token_required
def alterar_nome(usuario_id):
    dados = request.get_json(silent=True)

    nome = (
        dados.get("nome")
        if isinstance(dados, dict)
        else None
    )

    if (
        not isinstance(nome, str)
        or not 1 <= len(nome.strip()) <= 100
        or any(ord(c) < 32 or ord(c) == 127 for c in nome)
    ):
        return jsonify(
            error=(
                "Informe um nome de 1 a 100 caracteres, "
                "sem caracteres de controle."
            )
        ), 400

    def salvar(conn, cursor, usuario):
        cursor.execute(
            "UPDATE usuarios SET nome=%s WHERE id=%s",
            (nome.strip(), usuario_id),
        )
        conn.commit()

        return jsonify(
            message="Nome atualizado.",
            nome=nome.strip(),
        ), 200

    return _executar(usuario_id, salvar)


@conta_bp.route(
    "/email/solicitar",
    methods=["POST"],
    strict_slashes=False,
)
@token_required
def solicitar_email(usuario_id):
    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        return jsonify(error="Envie um objeto JSON válido."), 400

    email = dados.get("novo_email")

    if (
        not isinstance(email, str)
        or len(email.strip()) > 100
        or not re.fullmatch(
            r"[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+",
            email.strip(),
        )
    ):
        return jsonify(
            error="Informe um e-mail válido com até 100 caracteres."
        ), 400

    email = email.strip().lower()

    def solicitar(conn, cursor, usuario):
        if not _autorizar_senha(
            conn,
            cursor,
            usuario,
            dados.get("senha"),
        ):
            return jsonify(
                error=(
                    "Senha atual incorreta ou tentativas "
                    "temporariamente bloqueadas."
                )
            ), 403

        if email == usuario["email"].lower():
            return jsonify(
                error="Informe um e-mail diferente do atual."
            ), 400

        cursor.execute(
            "SELECT id FROM usuarios WHERE email=%s",
            (email,),
        )

        if cursor.fetchone():
            return jsonify(
                error="Não é possível usar este e-mail."
            ), 409

        cursor.execute(
            """
            SELECT solicitado_em
            FROM trocas_email
            WHERE usuario_id=%s
            """,
            (usuario_id,),
        )
        anterior = cursor.fetchone()

        agora = datetime.utcnow()

        if (
            anterior
            and (agora - anterior["solicitado_em"]).total_seconds() < 60
        ):
            return jsonify(
                error="Aguarde um minuto antes de solicitar outro código."
            ), 429

        codigo = str(100000 + secrets.randbelow(900000))

        cursor.execute(
            """
            INSERT INTO trocas_email (
                usuario_id,
                novo_email,
                codigo_hash,
                expira_em,
                solicitado_em,
                tentativas
            )
            VALUES (%s,%s,%s,%s,%s,0)
            ON DUPLICATE KEY UPDATE
                novo_email=VALUES(novo_email),
                codigo_hash=VALUES(codigo_hash),
                expira_em=VALUES(expira_em),
                solicitado_em=VALUES(solicitado_em),
                tentativas=0
            """,
            (
                usuario_id,
                email,
                _hash_codigo(usuario_id, email, codigo),
                agora + timedelta(minutes=15),
                agora,
            ),
        )
        conn.commit()

        # O endereço atual só muda depois da confirmação.
        # O envio não é repetido automaticamente.
        enviado = enviar_email_codigo(
            email,
            codigo,
            "verificacao",
        )

        mensagem = (
            "Código solicitado para o novo e-mail. Confira também o spam."
            if enviado
            else (
                "Solicitação salva, mas o envio não foi confirmado. "
                "Aguarde um minuto e solicite novamente."
            )
        )

        return jsonify(
            email_sent=enviado,
            message=mensagem,
        ), 202

    return _executar(usuario_id, solicitar)


@conta_bp.route(
    "/email/confirmar",
    methods=["POST"],
    strict_slashes=False,
)
@token_required
def confirmar_email(usuario_id):
    dados = request.get_json(silent=True)

    codigo = (
        dados.get("codigo")
        if isinstance(dados, dict)
        else None
    )

    if (
        not isinstance(codigo, str)
        or not re.fullmatch(r"[0-9]{6}", codigo)
    ):
        return jsonify(
            error="Informe o código de seis dígitos."
        ), 400

    def confirmar(conn, cursor, usuario):
        cursor.execute(
            """
            SELECT *
            FROM trocas_email
            WHERE usuario_id=%s
            FOR UPDATE
            """,
            (usuario_id,),
        )
        troca = cursor.fetchone()

        if (
            not troca
            or troca["expira_em"] <= datetime.utcnow()
            or troca["tentativas"] >= 5
        ):
            return jsonify(
                error="Código inválido ou expirado. Solicite outro."
            ), 400

        esperado = _hash_codigo(
            usuario_id,
            troca["novo_email"],
            codigo,
        )

        if not hmac.compare_digest(
            troca["codigo_hash"],
            esperado,
        ):
            cursor.execute(
                """
                UPDATE trocas_email
                SET tentativas=tentativas+1
                WHERE usuario_id=%s
                """,
                (usuario_id,),
            )
            conn.commit()

            return jsonify(
                error="Código inválido ou expirado."
            ), 400

        cursor.execute(
            """
            UPDATE usuarios
            SET email=%s,
                email_verificado=1,
                token_verificacao=NULL,
                token_recuperacao=NULL,
                token_expiracao=NULL,
                versao_token=versao_token+1
            WHERE id=%s
            """,
            (troca["novo_email"], usuario_id),
        )

        cursor.execute(
            "DELETE FROM trocas_email WHERE usuario_id=%s",
            (usuario_id,),
        )
        conn.commit()

        return jsonify(
            message="E-mail atualizado. Entre novamente com o novo endereço.",
            sessao_encerrada=True,
        ), 200

    return _executar(usuario_id, confirmar)


@conta_bp.route("", methods=["DELETE"], strict_slashes=False)
@token_required
def apagar_conta(usuario_id):
    dados = request.get_json(silent=True)

    if (
        not isinstance(dados, dict)
        or dados.get("confirmacao") != "APAGAR"
    ):
        return jsonify(
            error="Digite APAGAR para confirmar a exclusão."
        ), 400

    def apagar(conn, cursor, usuario):
        if not _autorizar_senha(
            conn,
            cursor,
            usuario,
            dados.get("senha"),
        ):
            return jsonify(
                error=(
                    "Senha atual incorreta ou tentativas "
                    "temporariamente bloqueadas."
                )
            ), 403

        # Preserva os postos e a disponibilidade revisada.
        cursor.execute(
            """
            UPDATE postos_combustiveis
            SET manual_atualizado_por=NULL
            WHERE manual_atualizado_por=%s
            """,
            (usuario_id,),
        )

        # As relações pessoais seguem as cascatas do schema.
        cursor.execute(
            "DELETE FROM usuarios WHERE id=%s",
            (usuario_id,),
        )
        conn.commit()

        return jsonify(
            message="Conta excluída.",
            conta_excluida=True,
        ), 200

    return _executar(usuario_id, apagar)