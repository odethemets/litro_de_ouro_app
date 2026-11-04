# back_end/app/utils/decorator.py

from functools import wraps

import jwt

from flask import current_app, jsonify, request


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

            # Evita encaminhar um identificador inválido às consultas.
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

        # Mantém a assinatura das rotas protegidas existentes.
        return f(current_user_id, *args, **kwargs)

    return decorated