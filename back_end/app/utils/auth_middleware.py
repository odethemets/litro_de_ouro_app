import os
import jwt
from functools import wraps
from flask import request, jsonify

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(" ")[1]

        if not token:
            return jsonify({'error': 'Token ausente. Acesso não autorizado.'}), 401

        try:
            # O JWT_SECRET DEVE estar definido no seu arquivo .env
            secret = os.getenv('JWT_SECRET', 'senha_super_secreta_padrao')
            data = jwt.decode(token, secret, algorithms=["HS256"])
            current_user_id = data['user_id']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expirado. Faça login novamente.'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Token inválido. Acesso negado.'}), 401

        return f(current_user_id, *args, **kwargs)

    return decorated