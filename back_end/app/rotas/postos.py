from flask import Blueprint, jsonify
from app.db import get_db_connection

postos_bp = Blueprint('postos', __name__)

@postos_bp.route('', methods=['GET'])
def listar_postos():
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Busca os postos e o último preço registrado (se houver)
            cursor.execute("""
                SELECT 
                    p.id, p.nome, p.bairro, p.endereco, 
                    p.latitude, p.longitude,
                    (SELECT preco FROM registos_preco rp 
                     WHERE rp.posto_id = p.id 
                     ORDER BY data_atualizacao DESC LIMIT 1) as preco_gasolina
                FROM postos p
            """)
            postos = cursor.fetchall()
            
            # Se preco_gasolina for None, define como 0 para não quebrar o frontend
            for posto in postos:
                if posto['preco_gasolina'] is None:
                     posto['preco_gasolina'] = 0.00
                else:
                     posto['preco_gasolina'] = float(posto['preco_gasolina'])
                
                posto['latitude'] = float(posto['latitude'])
                posto['longitude'] = float(posto['longitude'])

        return jsonify(postos), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if 'conn' in locals() and conn.open:
            conn.close()