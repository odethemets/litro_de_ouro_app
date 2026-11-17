# back_end/app/utils/decorator.py

from functools import wraps

import jwt

from flask import current_app, jsonify, request
from app.db import get_db_connection


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # split() trata espaços adicionais sem provocar IndexError.
        authorization = request.headers.get("Authorization", "")
        partes = authorization.split()

        if (
            len(partes) != 2
            or partes[0].lower() != "bearer"
        ):
            return jsonify({
                "error": "Token ausente ou cabeçalho inválido. Faça login."
            }), 401

        token = partes[1]

        # A chave é carregada por create_app(), sem fallback conhecido.
        segredo = current_app.config.get("SECRET_KEY")

        if (
            not isinstance(segredo, str)
            or len(segredo.strip().encode("utf-8")) < 32
            or segredo.strip() == "segredo-padrao-temporario"
        ):
            # Falha de configuração é erro do servidor, não do usuário.
            current_app.logger.error(
                "Chave de autenticação não configurada corretamente."
            )

            return jsonify({
                "error": "Autenticação temporariamente indisponível."
            }), 500

        try:
            dados = jwt.decode(
                token,
                segredo,
                algorithms=["HS256"],
                options={
                    # Exige os campos emitidos pelo login.
                    "require": ["exp", "usuario_id"],
                },
            )

            current_user_id = dados["usuario_id"]

            # bool é uma subclasse de int no Python, por isso é excluído.
            if (
                isinstance(current_user_id, bool)
                or not isinstance(current_user_id, int)
                or current_user_id <= 0
            ):
                return jsonify({
                    "error": "Token de segurança inválido."
                }), 401

        except jwt.ExpiredSignatureError:
            return jsonify({
                "error": "Token expirado. Faça login novamente."
            }), 401

        except jwt.InvalidTokenError:
            return jsonify({
                "error": "Token de segurança inválido."
            }), 401

        # JWT antigo é aceito apenas enquanto a versão da conta permanece zero.
        versao = dados.get("ver", 0)

        if isinstance(versao, bool) or not isinstance(versao, int) or versao < 0:
            return jsonify(error="Token de segurança inválido."), 401

        conn = None

        try:
            conn = get_db_connection()

            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT versao_token FROM usuarios WHERE id=%s",
                    (current_user_id,),
                )
                usuario = cursor.fetchone()

            if not usuario:
                return jsonify(
                    error="Conta removida.",
                    code="ACCOUNT_DELETED",
                ), 401

            if usuario["versao_token"] != versao:
                return jsonify(
                    error="Sua sessão foi encerrada. Entre novamente."
                ), 401

        except Exception:
            current_app.logger.exception("Falha ao verificar a sessão")

            return jsonify(
                error="Não foi possível verificar sua sessão. Tente novamente."
            ), 503

        finally:
            if conn is not None:
                conn.close()

        return f(current_user_id, *args, **kwargs)

    return decorated