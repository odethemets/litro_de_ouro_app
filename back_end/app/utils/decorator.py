from functools import wraps
from flask import request, jsonify, current_app
import jwt

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Verifica se o token veio no cabeçalho Authorization
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(" ")[1]

        if not token:
            return jsonify({'error': 'Token ausente. Faça login para acessar.'}), 401

        try:
            # ESTA É A LINHA MÁGICA: O mesmo segredo exato do auth.py
            segredo = current_app.config.get('SECRET_KEY') or 'segredo-padrao-temporario'
            
            dados = jwt.decode(token, segredo, algorithms=["HS256"])
            current_user_id = dados['usuario_id']
            
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expirado. Faça login novamente.'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Token de segurança inválido.'}), 401
        except Exception as e:
            current_app.logger.exception('Erro na validação do token')
            return jsonify({'error': 'Erro ao processar o token.'}), 401

        # Passa o ID do utilizador para a rota original
        return f(current_user_id, *args, **kwargs)
        
    return decorated