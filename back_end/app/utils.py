from flask import request, jsonify
import jwt
import os
from functools import wraps

def token_obrigatorio(f):
    @wraps(f)
    def decorador(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            partes = request.headers['Authorization'].split()
            if len(partes) == 2 and partes[0] == 'Bearer':
                token = partes[1]
        
        if not token:
            return jsonify({"error": "Token ausente! Faça login para aceder."}), 401
        
        try:
            dados_token = jwt.decode(token, os.getenv('SECRET_KEY'), algorithms=['HS256'])
            usuario_id_token = dados_token['usuario_id']
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "O Token expirou! Faça login novamente."}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Token inválido ou corrompido!"}), 401
        
        return f(usuario_id_token, *args, **kwargs)
    return decorador