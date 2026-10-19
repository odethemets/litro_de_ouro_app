import os
import jwt
import datetime
import pymysql
from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from app.db import get_db_connection
from app.utils import token_obrigatorio  # IMPORTAÇÃO LIMPA

# Definição correta do Blueprint (Tem de bater certo com o run.py)
auth_bp = Blueprint('auth', __name__)

# ==========================================
# ROTA 1: LOGIN
# ==========================================
@auth_bp.route('/login', methods=['POST'])
def login():
    dados = request.get_json()
    email = dados.get('email')
    password = dados.get('password')

    if not email or not password:
        return jsonify({"message": "Por favor, preencha o email e a senha."}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Vai buscar o hash da senha à base de dados
            cursor.execute("SELECT id, senha FROM usuarios WHERE email = %s", (email,))
            user = cursor.fetchone()

            # Compara a senha digitada com a criptografia scrypt guardada
            if user and check_password_hash(user['senha'], password):
                # Gera o Token JWT para manter o utilizador autenticado
                token = jwt.encode({
                    'user_id': user['id'],
                    'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24) # Expira em 24h
                }, os.getenv('SECRET_KEY', 'chave_secreta_padrao'), algorithm='HS256')
                
                return jsonify({"token": token}), 200
            else:
                return jsonify({"message": "Credenciais inválidas. Verifique o email e a senha."}), 401
    except Exception as e:
        return jsonify({"message": f"Erro interno: {str(e)}"}), 500
    finally:
        conn.close()

# ==========================================
# ROTA 2: REGISTrAR
# ==========================================
@auth_bp.route('/registrar', methods=['POST'])
def registrar():
    dados = request.get_json()
    nome = dados.get('nome')
    email = dados.get('email')
    senha = dados.get('password')

    if not nome or not email or not senha:
        return jsonify({"message": "Por favor, preencha todos os campos."}), 400

    # Cria a criptografia militar idêntica à da base de dados
    senha = generate_password_hash(senha, method='scrypt')

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Verifica se o email já existe para evitar duplicados
            cursor.execute("SELECT id FROM usuarios WHERE email = %s", (email,))
            if cursor.fetchone():
                return jsonify({"message": "Este email já está registado."}), 409
            
            # Insere o novo utilizador com o plano gratuito
            sql = """INSERT INTO usuarios (nome, email, senha, plano, criado_em) 
                     VALUES (%s, %s, %s, 'gratuito', NOW())"""
            cursor.execute(sql, (nome, email, senha))
        
        conn.commit() # Salva definitivamente no banco de dados
        return jsonify({"message": "Conta criada com sucesso!"}), 201
    
    except Exception as e:
        conn.rollback() # Em caso de erro, desfaz a operação para não corromper o banco
        return jsonify({"message": f"Erro interno do servidor: {str(e)}"}), 500
    finally:
        conn.close()

# ==========================================
# ROTA 3: RECUPERAR SENHA
# ==========================================
@auth_bp.route('/recuperar-senha', methods=['POST'])
def recuperar_senha():
    dados = request.get_json()
    email = dados.get('email')

    if not email:
        return jsonify({"message": "O email é obrigatório."}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, nome FROM usuarios WHERE email = %s", (email,))
            user = cursor.fetchone()
            
            if user:
                # Aqui futuramente pode-se integrar o envio de email (Flask-Mail)
                pass
        
        # Por motivos de segurança, a mensagem de sucesso é igual quer o email exista ou não
        return jsonify({"message": "Se o email existir na nossa base, receberá um link de recuperação em breve."}), 200
    except Exception as e:
        return jsonify({"message": f"Erro interno do servidor: {str(e)}"}), 500
    finally:
        conn.close()

# ==========================================
# ROTA 4: PERFIL (VER E ATUALIZAR)
# ==========================================
@auth_bp.route('/perfil', methods=['GET', 'PUT'])
@token_obrigatorio  # AGORA USA APENAS O DO UTILS.PY
def perfil(current_user_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # GET: Devolver os dados do utilizador
            if request.method == 'GET':
                cursor.execute("SELECT id, nome, email, plano, criado_em FROM usuarios WHERE id = %s", (current_user_id,))
                user = cursor.fetchone()
                if not user:
                    return jsonify({'message': 'Utilizador não encontrado'}), 404
                return jsonify(user), 200

            # PUT: Atualizar os dados do utilizador
            if request.method == 'PUT':
                dados = request.get_json()
                novo_nome = dados.get('nome')
                
                if not novo_nome:
                    return jsonify({"message": "O nome não pode estar vazio."}), 400
                
                # Atualiza apenas o nome no MySQL (o email costuma ser estático por segurança)
                cursor.execute("UPDATE usuarios SET nome = %s WHERE id = %s", (novo_nome, current_user_id))
                conn.commit()
                return jsonify({"message": "Perfil atualizado com sucesso!"}), 200
                
    except Exception as e:
        conn.rollback()
        return jsonify({"message": f"Erro interno: {str(e)}"}), 500
    finally:
        conn.close()