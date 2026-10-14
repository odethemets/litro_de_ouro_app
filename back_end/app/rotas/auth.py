from flask import Blueprint, request, jsonify
import pymysql
import os
import jwt
import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from ..db import get_db_connection

bp = Blueprint('auth', __name__)

@bp.route('/registrar', methods=['POST'])
def registrar_usuario():
    data = request.get_json()
    if not data or not data.get('nome') or not data.get('email') or not data.get('senha'):
        return jsonify({"error": "Dados incompletos!"}), 400

    senha_criptografada = generate_password_hash(data['senha'])
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM usuarios WHERE email = %s", (data['email'],))
            if cursor.fetchone():
                return jsonify({"error": "Este email já está registado!"}), 409

            sql = "INSERT INTO usuarios (nome, email, senha_hash) VALUES (%s, %s, %s)"
            cursor.execute(sql, (data['nome'], data['email'], senha_criptografada))
            conn.commit()
            
        return jsonify({"message": "Utilizador registado com sucesso!"}), 201
    except pymysql.MySQLError as e:
        if conn: conn.rollback()
        return jsonify({"error": "Erro ao registar", "detalhes": str(e)}), 500
    finally:
        if conn: conn.close()

@bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or not data.get('email') or not data.get('senha'):
        return jsonify({"error": "Informe email e senha."}), 400

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, nome, email, senha_hash FROM usuarios WHERE email = %s", (data['email'],))
            usuario = cursor.fetchone()

            if not usuario or not check_password_hash(usuario['senha_hash'], data['senha']):
                return jsonify({"error": "Email ou senha incorretos."}), 401

            token = jwt.encode({
                'usuario_id': usuario['id'],
                'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=24)
            }, os.getenv('SECRET_KEY'), algorithm='HS256')

            return jsonify({
                "message": "Login realizado!",
                "token": token,
                "usuario": {"id": usuario['id'], "nome": usuario['nome'], "email": usuario['email']}
            }), 200
    except pymysql.MySQLError as e:
        return jsonify({"error": "Erro no login", "detalhes": str(e)}), 500
    finally:
        if conn: conn.close()