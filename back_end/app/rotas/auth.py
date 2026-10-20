from flask import Blueprint, request, jsonify
import bcrypt
import jwt
import datetime
import os
from app.db import get_db_connection
from app.utils.auth_middleware import token_required

auth_bp = Blueprint('auth', __name__)
SECRET_KEY = os.getenv("JWT_SECRET") or os.getenv("SECRET_KEY") or "chave_super_secreta_para_tokens_jwt"

@auth_bp.route('/registrar', methods=['POST'])
def registrar_usuario():
    dados = request.get_json()
    nome = dados.get('nome')
    email = dados.get('email')
    senha = dados.get('senha')

    if not nome or not email or not senha:
        return jsonify({"error": "Todos os campos (nome, email, senha) são obrigatórios."}), 400

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM usuarios WHERE email = %s", (email,))
            if cursor.fetchone():
                return jsonify({"error": "E-mail já está em uso."}), 409

            senha_hash = bcrypt.hashpw(senha.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            cursor.execute("""
                INSERT INTO usuarios (nome, email, senha_hash, karma)
                VALUES (%s, %s, %s, 0)
            """, (nome, email, senha_hash))
            conn.commit()
            
        return jsonify({"mensagem": "Usuário registrado com sucesso!"}), 201
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

@auth_bp.route('/login', methods=['POST'])
def login():
    dados = request.get_json()
    email = dados.get('email')
    senha = dados.get('senha')

    if not email or not senha:
        return jsonify({"error": "E-mail e senha são obrigatórios."}), 400

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, senha_hash FROM usuarios WHERE email = %s", (email,))
            usuario = cursor.fetchone()

            if usuario and bcrypt.checkpw(senha.encode('utf-8'), usuario['senha_hash'].encode('utf-8')):
                token = jwt.encode({
                    'user_id': usuario['id'],
                    'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
                }, SECRET_KEY, algorithm="HS256")

                return jsonify({"mensagem": "Login efetuado.", "token": token}), 200
            else:
                return jsonify({"error": "Credenciais inválidas."}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

@auth_bp.route('/perfil', methods=['GET'])
@token_required
def obter_perfil(current_user_id):
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, nome, email, plano, karma FROM usuarios WHERE id = %s", (current_user_id,))
            usuario = cursor.fetchone()
            
            if usuario:
                return jsonify(usuario), 200
            return jsonify({"error": "Usuário não encontrado."}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()