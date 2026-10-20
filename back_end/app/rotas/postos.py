from flask import Blueprint, jsonify, request
from app.db import get_db_connection

postos_bp = Blueprint('postos', __name__)

@postos_bp.route('', methods=['GET'])
def listar_postos():
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    p.id, p.nome, p.bairro, p.endereco, 
                    p.latitude, p.longitude,
                    (SELECT preco FROM registos_preco rp 
                     WHERE rp.posto_id = p.id 
                     ORDER BY data_registro DESC LIMIT 1) as preco_gasolina
                FROM postos p
            """)
            postos = cursor.fetchall()
            
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
        if conn: conn.close()

# NOVA ROTA: Alimenta a tela "Menor Preço" da Web com o Score de Confiança
@postos_bp.route('/menores-precos', methods=['GET'])
def menores_precos():
    tipo_combustivel = request.args.get('tipo_combustivel', 'Gasolina Comum')
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Traz o último preço de cada posto para aquele combustível, ordenado do mais barato para o mais caro
            cursor.execute("""
                SELECT 
                    p.id as posto_id, p.nome, p.bairro, 
                    rp.id as registo_id, rp.preco, rp.confianca_score, rp.data_registro
                FROM postos p
                JOIN registos_preco rp ON p.id = rp.posto_id
                WHERE rp.tipo_combustivel = %s
                  AND rp.data_registro = (
                      SELECT MAX(data_registro) FROM registos_preco rp2 
                      WHERE rp2.posto_id = p.id AND rp2.tipo_combustivel = %s
                  )
                ORDER BY rp.preco ASC
            """, (tipo_combustivel, tipo_combustivel))
            
            dados = cursor.fetchall()
            
            for d in dados:
                d['preco'] = float(d['preco'])
                d['distancia'] = d['bairro'] or 'João Pessoa'

        return jsonify(dados), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()