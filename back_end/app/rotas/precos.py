from flask import Blueprint, request, jsonify
import pymysql
import math
from app.db import get_db_connection
from app.utils.auth_middleware import token_required

precos_bp = Blueprint('precos', __name__)

def calcular_distancia_metros(lat1, lon1, lat2, lon2):
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
         
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

@precos_bp.route('', methods=['POST'], strict_slashes=False)
@token_required
def registrar_preco(usuario_id_token):
    data = request.get_json()

    campos_necessarios = ['posto_id', 'tipo_combustivel', 'preco', 'latitude', 'longitude']
    if not data or not all(campo in data for campo in campos_necessarios):
        return jsonify({"error": "Dados incompletos! Informe posto_id, tipo_combustivel, preco, latitude e longitude."}), 400

    try:
        preco_informado = float(data['preco'])
    except ValueError:
        return jsonify({"error": "O campo 'preco' deve ser um número válido."}), 400

    if not (1.00 <= preco_informado <= 25.00):
        return jsonify({"error": "O preço informado está fora dos limites aceitáveis (entre R$ 1,00 e R$ 25,00)."}), 400

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 1. Geofencing (máximo 200m)
            cursor.execute("SELECT latitude, longitude, nome FROM postos WHERE id = %s", (data['posto_id'],))
            posto = cursor.fetchone()

            if not posto or posto['latitude'] is None or posto['longitude'] is None:
                return jsonify({"error": "Posto não encontrado ou sem coordenadas geográficas."}), 404

            distancia = calcular_distancia_metros(
                float(data['latitude']), 
                float(data['longitude']), 
                float(posto['latitude']), 
                float(posto['longitude'])
            )

            LIMITE_METROS = 600000.0
            if distancia > LIMITE_METROS:
                return jsonify({
                    "error": "Você está muito longe deste posto para registrar o preço.",
                    "distancia_atual_metros": round(distancia, 2)
                }), 403

            # 2. Inserir preço
            sql_insert = """
                INSERT INTO registos_preco (posto_id, usuario_id, tipo_combustivel, preco, confianca_score, data_registro)
                VALUES (%s, %s, %s, %s, 1, NOW())
            """
            cursor.execute(sql_insert, (data['posto_id'], usuario_id_token, data['tipo_combustivel'], preco_informado))

            # 3. RECOMPENSA DE KARMA: +5 Pontos por contribuir com um preço válido!
            cursor.execute("UPDATE usuarios SET karma = karma + 5 WHERE id = %s", (usuario_id_token,))

            conn.commit()
            
        return jsonify({
            "message": f"Preço registrado com sucesso! Você ganhou +5 pontos de Karma!",
            "distancia_verificada_metros": round(distancia, 2)
        }), 201

    except pymysql.MySQLError as e:
        if conn: conn.rollback()
        return jsonify({"error": "Erro ao salvar o preço", "detalhes": str(e)}), 500
    finally:
        if conn: conn.close()

@precos_bp.route('/<int:registo_id>/votar', methods=['POST'], strict_slashes=False)
@token_required
def votar_preco(usuario_id_token, registo_id):
    data = request.get_json()
    if not data or data.get('voto') not in ['positivo', 'negativo']:
        return jsonify({"error": "Envie 'voto' com o valor 'positivo' ou 'negativo'."}), 400

    novo_voto = data['voto']
    
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 1. Verifica se o registro de preço existe e descobre quem é o autor
            cursor.execute("SELECT usuario_id FROM registos_preco WHERE id = %s", (registo_id,))
            registo = cursor.fetchone()
            
            if not registo:
                return jsonify({"error": "Registro de preço não encontrado."}), 404

            autor_id = registo['usuario_id']

            # Trava: Não permite votar no próprio registro
            if autor_id == usuario_id_token:
                return jsonify({"error": "Você não pode votar na sua própria publicação de preço."}), 400

            # 2. Verifica se o usuário já votou neste preço
            cursor.execute("SELECT tipo_voto FROM votos_registos WHERE usuario_id = %s AND registo_id = %s", (usuario_id_token, registo_id))
            voto_existente = cursor.fetchone()

            if not voto_existente:
                # PRIMEIRO VOTO
                delta_score = 1 if novo_voto == 'positivo' else -1
                delta_karma = 2 if novo_voto == 'positivo' else -2

                cursor.execute("""
                    INSERT INTO votos_registos (registo_id, usuario_id, tipo_voto)
                    VALUES (%s, %s, %s)
                """, (registo_id, usuario_id_token, novo_voto))

            elif voto_existente['tipo_voto'] == novo_voto:
                return jsonify({"message": "Você já registrou este mesmo voto para este preço."}), 200

            else:
                # MUDANÇA DE VOTO (Ex: De Negativo para Positivo -> Delta x 2)
                delta_score = 2 if novo_voto == 'positivo' else -2
                delta_karma = 4 if novo_voto == 'positivo' else -4

                cursor.execute("""
                    UPDATE votos_registos SET tipo_voto = %s
                    WHERE usuario_id = %s AND registo_id = %s
                """, (novo_voto, usuario_id_token, registo_id))

            # 3. Atualiza a confiança do preço e o Karma do AUTOR do preço
            cursor.execute("UPDATE registos_preco SET confianca_score = confianca_score + %s WHERE id = %s", (delta_score, registo_id))
            cursor.execute("UPDATE usuarios SET karma = karma + %s WHERE id = %s", (delta_karma, autor_id))

            conn.commit()
            
        return jsonify({
            "message": f"Voto '{novo_voto}' registrado com sucesso!"
        }), 200

    except pymysql.MySQLError as e:
        if conn: conn.rollback()
        return jsonify({"error": "Erro ao processar o voto", "detalhes": str(e)}), 500
    finally:
        if conn: conn.close()