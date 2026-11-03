# app/rotas/atividade.py
from flask import Blueprint, jsonify, current_app
from app.db import get_db_connection
from app.utils.decorator import token_required

atividade_bp = Blueprint('atividade', __name__)

@atividade_bp.route('/meus-registos', methods=['GET'], strict_slashes=False)
@token_required
def meus_registos(current_user_id):
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT r.id, r.tipo_combustivel, r.preco, 
                       DATE_FORMAT(r.data_registro, '%%d/%%m/%%Y %%H:%%i') as data_formatada,
                       p.nome as posto_nome, p.endereco as posto_endereco
                FROM registos_preco r
                JOIN postos p ON p.id = r.posto_id
                WHERE r.usuario_id = %s
                ORDER BY r.data_registro DESC
                LIMIT 50
            """, (current_user_id,))
            registos = cursor.fetchall()

            for r in registos:
                r['preco'] = float(r['preco'])

        return jsonify(registos), 200
    except Exception:
        current_app.logger.exception('Erro ao buscar registros do usuário %s', current_user_id)
        return jsonify({"error": "Erro ao buscar histórico de preços."}), 500
    finally:
        if conn and conn.open:
            conn.close()