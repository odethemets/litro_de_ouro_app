import os
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import jwt
from flask import Blueprint, request, jsonify, current_app
from werkzeug.security import check_password_hash, generate_password_hash
from app.db import get_db_connection
from app.utils.decorator import token_required

auth_bp = Blueprint('auth', __name__)

# =========================================================
# MOTOR DE E-MAIL (SMTP GMAIL BLINDADO COM TIMEOUT)
# =========================================================
def enviar_email_codigo(destinatario, codigo, tipo="verificacao"):
    remetente = os.getenv("EMAIL_REMETENTE", "litrodeourooficial@gmail.com")
    senha_app = os.getenv("EMAIL_SENHA_APP", "qugsurxrqbgptkwq")
    
    assunto = "Litro de Ouro - Código de Acesso" if tipo == "verificacao" else "Litro de Ouro - Recuperação de Senha"
    
    mensagem_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; text-align: center; padding: 20px;">
        <h2>Litro de Ouro</h2>
        <p>Aqui está o seu código de segurança:</p>
        <h1 style="font-size: 32px; letter-spacing: 5px; color: #F59E0B; background: #1E1E1E; padding: 15px; border-radius: 8px; display: inline-block;">
          {codigo}
        </h1>
        <p style="color: #666; font-size: 12px; margin-top: 20px;">Este código expira em 15 minutos.</p>
      </body>
    </html>
    """

    try:
        msg = MIMEMultipart()
        msg['From'] = f"Litro de Ouro <{remetente}>"
        msg['To'] = destinatario
        msg['Subject'] = assunto
        msg.attach(MIMEText(mensagem_html, 'html'))

        # ADICIONADO timeout=10: Evita travamento de 15s no frontend Axios
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
        server.starttls()
        server.login(remetente, senha_app)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"[SMTP ERRO] Falha ao enviar e-mail para {destinatario}: {e}")
        return False

# =========================================================
# LOGIN
# =========================================================
@auth_bp.route('/login', methods=['POST'], strict_slashes=False)
def login():
    data = request.get_json(silent=True) or {}
    email = data.get('email', '').strip()
    senha = data.get('senha', '')

    if not email or not senha:
        return jsonify({"error": "Informe e-mail e senha."}), 400

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, senha, email_verificado FROM usuarios WHERE email = %s", (email,))
            usuario = cursor.fetchone()

            if not usuario:
                return jsonify({"error": "E-mail ou senha incorretos."}), 401

            try:
                senha_valida = check_password_hash(usuario['senha'], senha)
            except ValueError:
                senha_valida = False

            if not senha_valida:
                return jsonify({"error": "E-mail ou senha incorretos."}), 401

            # Lógica de Email não verificado
            if not usuario['email_verificado']:
                novo_codigo = str(random.randint(100000, 999999))
                expiracao = datetime.utcnow() + timedelta(minutes=15)
                
                cursor.execute(
                    "UPDATE usuarios SET token_verificacao = %s, token_expiracao = %s WHERE email = %s",
                    (novo_codigo, expiracao, email)
                )
                conn.commit()
                
                enviar_email_codigo(email, novo_codigo, "verificacao")
                
                return jsonify({
                    "error": "Conta não verificada. Enviámos um novo código.",
                    "require_validation": True
                }), 403

            segredo = current_app.config.get('SECRET_KEY') or 'segredo-padrao-temporario'
            token = jwt.encode({
                'usuario_id': usuario['id'],
                'exp': datetime.utcnow() + timedelta(days=7)
            }, segredo, algorithm='HS256')

            return jsonify({
                "message": "Login realizado com sucesso",
                "token": token
            }), 200

    except Exception as e:
        current_app.logger.exception('Erro no login')
        return jsonify({"error": "Erro interno ao processar o login."}), 500
    finally:
        if conn and conn.open:
            conn.close()

# =========================================================
# CONFIRMAR E-MAIL
# =========================================================
@auth_bp.route('/confirmar-email', methods=['POST'], strict_slashes=False)
def confirmar_email():
    data = request.get_json(silent=True) or {}
    email = data.get('email', '').strip()
    codigo = data.get('codigo', '').strip()

    if not email or not codigo:
        return jsonify({"error": "E-mail e código são obrigatórios."}), 400

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM usuarios WHERE email = %s AND token_verificacao = %s AND token_expiracao > %s",
                (email, codigo, datetime.utcnow())
            )
            if not cursor.fetchone():
                return jsonify({"error": "Código inválido ou expirado."}), 400
            
            cursor.execute(
                "UPDATE usuarios SET email_verificado = 1, token_verificacao = NULL WHERE email = %s",
                (email,)
            )
            conn.commit()
            return jsonify({"message": "E-mail confirmado com sucesso!"}), 200
    except Exception as e:
        current_app.logger.exception('Erro na confirmacao')
        return jsonify({"error": "Erro interno."}), 500
    finally:
        if conn and conn.open:
            conn.close()

# =========================================================
# RECUPERAR SENHA (GERAR CÓDIGO)
# =========================================================
@auth_bp.route('/recuperar-senha', methods=['POST'], strict_slashes=False)
def recuperar_senha():
    data = request.get_json(silent=True) or {}
    email = data.get('email', '').strip()
    
    if not email:
        return jsonify({"error": "Informe o e-mail."}), 400
        
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM usuarios WHERE email = %s", (email,))
            if not cursor.fetchone():
                return jsonify({"message": "Se o e-mail existir, receberá um código."}), 200
                
            codigo = str(random.randint(100000, 999999))
            expiracao = datetime.utcnow() + timedelta(minutes=15)
            
            cursor.execute(
                "UPDATE usuarios SET token_recuperacao = %s, token_expiracao = %s WHERE email = %s",
                (codigo, expiracao, email)
            )
            conn.commit()
            
            # Executa o envio de e-mail (com timeout de segurança de 10s)
            enviar_email_codigo(email, codigo, "recuperacao")
            
            return jsonify({"message": "Código de recuperação gerado com sucesso!"}), 200
            
    except Exception as e:
        current_app.logger.exception('Erro em recuperar-senha')
        return jsonify({"error": "Erro interno."}), 500
    finally:
        if conn and conn.open:
            conn.close()

# =========================================================
# REDEFINIR SENHA
# =========================================================
@auth_bp.route('/redefinir-senha', methods=['POST'], strict_slashes=False)
def redefinir_senha():
    data = request.get_json(silent=True) or {}
    email = data.get('email', '').strip()
    codigo = data.get('codigo', '').strip()
    nova_senha = data.get('nova_senha', '')
    
    if not email or not codigo or not nova_senha:
        return jsonify({"error": "Dados incompletos."}), 400
        
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM usuarios WHERE email = %s AND token_recuperacao = %s AND token_expiracao > %s",
                (email, codigo, datetime.utcnow())
            )
            if not cursor.fetchone():
                return jsonify({"error": "Código inválido ou expirado."}), 400
                
            senha_hash = generate_password_hash(nova_senha)
            
            cursor.execute(
                "UPDATE usuarios SET senha = %s, token_recuperacao = NULL, email_verificado = 1 WHERE email = %s",
                (senha_hash, email)
            )
            conn.commit()
            return jsonify({"message": "Palavra-passe redefinida com sucesso."}), 200
            
    except Exception as e:
        current_app.logger.exception('Erro em redefinir-senha')
        return jsonify({"error": "Erro interno."}), 500
    finally:
        if conn and conn.open:
            conn.close()

# =========================================================
# PERFIL DO UTILIZADOR
# =========================================================
@auth_bp.route('/perfil', methods=['GET'], strict_slashes=False)
@token_required
def obter_perfil(current_user_id):
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT nome, email, plano, karma, 
                       DATE_FORMAT(criado_em, '%%d/%%m/%%Y') as membro_desde 
                FROM usuarios 
                WHERE id = %s
            """, (current_user_id,))
            
            usuario = cursor.fetchone()
            
            if not usuario:
                return jsonify({"error": "Utilizador não encontrado."}), 404
                
            return jsonify(usuario), 200
            
    except Exception as e:
        current_app.logger.exception('Erro ao buscar perfil')
        return jsonify({"error": "Erro interno ao buscar os dados."}), 500
    finally:
        if conn and conn.open:
            conn.close()

# =========================================================
# CADASTRO (CRIAR CONTA)
# =========================================================
@auth_bp.route('/cadastro', methods=['POST'], strict_slashes=False)
def cadastro():
    data = request.get_json(silent=True) or {}
    nome = data.get('nome', '').strip()
    email = data.get('email', '').strip()
    senha = data.get('senha', '')

    if not nome or not email or not senha:
        return jsonify({"error": "Preencha todos os campos obrigatórios."}), 400

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM usuarios WHERE email = %s", (email,))
            if cursor.fetchone():
                return jsonify({"error": "Este e-mail já está registado."}), 400

            senha_hash = generate_password_hash(senha)
            codigo = str(random.randint(100000, 999999))
            expiracao = datetime.utcnow() + timedelta(minutes=15)

            cursor.execute("""
                INSERT INTO usuarios (nome, email, senha, plano, karma, email_verificado, token_verificacao, token_expiracao)
                VALUES (%s, %s, %s, 'gratis', 0, 0, %s, %s)
            """, (nome, email, senha_hash, codigo, expiracao))
            conn.commit()

            enviar_email_codigo(email, codigo, "verificacao")

            return jsonify({"message": "Conta criada com sucesso! Verifique o seu e-mail."}), 201

    except Exception as e:
        current_app.logger.exception('Erro no cadastro')
        return jsonify({"error": "Erro interno ao criar a conta."}), 500
    finally:
        if conn and conn.open:
            conn.close()