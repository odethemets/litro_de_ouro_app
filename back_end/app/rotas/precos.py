from flask import Blueprint, request, jsonify
import pymysql
import math
from ..db import get_db_connection
from ..utils import token_obrigatorio

bp = Blueprint('precos', __name__)

def calcular_distancia_metros(lat1, lon1, lat2, lon2):
    """
    Calcula a distância em metros entre duas coordenadas geográficas 
    usando a Fórmula de Haversine.
    """
    R = 6371000  # Raio da Terra em metros
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = (math.sin(dlat / 2) * math.sin(dlat / 2) +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) * math.sin(dlon / 2))
         
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

@bp.route('/', methods=['POST'])
@token_obrigatorio
def registrar_preco(usuario_id_token):
    data = request.get_json()

    # 1. Validação de campos obrigatórios
    campos_necessarios = ['posto_id', 'tipo_combustivel', 'preco', 'latitude', 'longitude']
    if not data or not all(campo in data for campo in campos_necessarios):
        return jsonify({"error": "Dados incompletos! Informe posto_id, tipo_combustivel, preco, latitude e longitude."}), 400

    try:
        preco_informado = float(data['preco'])
    except ValueError:
        return jsonify({"error": "O campo 'preco' deve ser um número válido."}), 400

    # 2. Limites Absolutos de Segurança (Filtro anti-absurdos)
    if not (1.00 <= preco_informado <= 25.00):
        return jsonify({"error": "O preço informado está fora dos limites aceitáveis (entre R$ 1,00 e R$ 25,00)."}), 400

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 3. Validação de Proximidade GPS (Trava de Geofencing: máx 200 metros)
            cursor.execute("SELECT latitude, longitude, nome FROM postos WHERE id = %s", (data['posto_id'],))
            posto = cursor.fetchone()

            if not posto:
                return jsonify({"error": "Posto de combustível não encontrado."}), 404

            if posto['latitude'] is None or posto['longitude'] is None:
                return jsonify({"error": "Este posto ainda não possui coordenadas GPS cadastradas no sistema."}), 400

            distancia = calcular_distancia_metros(
                float(data['latitude']), 
                float(data['longitude']), 
                float(posto['latitude']), 
                float(posto['longitude'])
            )

            LIMITE_METROS = 200.0
            if distancia > LIMITE_METROS:
                return jsonify({
                    "error": "Você está muito longe deste posto para registrar o preço.",
                    "distancia_atual_metros": round(distancia, 2),
                    "limite_permitido_metros": LIMITE_METROS
                }), 403

            # 4. Filtro de Preços Anómalos (Outliers baseados na média dos últimos 7 dias)
            sql_media = """
                SELECT AVG(preco) as media_preco 
                FROM registos_preco 
                WHERE tipo_combustivel = %s AND data_registro >= NOW() - INTERVAL 7 DAY
            """
            cursor.execute(sql_media, (data['tipo_combustivel'],))
            resultado_media = cursor.fetchone()

            if resultado_media and resultado_media['media_preco']:
                media_recente = float(resultado_media['media_preco'])
                
                # Tolerância de 40% para cima ou para baixo da média
                limite_inferior = media_recente * 0.6
                limite_superior = media_recente * 1.4

                if not (limite_inferior <= preco_informado <= limite_superior):
                    return jsonify({
                        "error": "Preço rejeitado por anomalia. Valor difere drasticamente da média recente.",
                        "media_recente_estimada": round(media_recente, 2),
                        "limites_aceitaveis": f"Entre R$ {round(limite_inferior, 2)} e R$ {round(limite_superior, 2)}"
                    }), 422

            # 5. Passou em todas as travas -> Insere no banco
            sql_insert = """
                INSERT INTO registos_preco (posto_id, usuario_id, tipo_combustivel, preco, confianca_score, data_registro)
                VALUES (%s, %s, %s, %s, 1, NOW())
            """
            cursor.execute(sql_insert, (data['posto_id'], usuario_id_token, data['tipo_combustivel'], preco_informado))
            conn.commit()
            
        return jsonify({
            "message": f"Preço registado com sucesso para o posto {posto['nome']}!",
            "distancia_verificada_metros": round(distancia, 2)
        }), 201

    except pymysql.MySQLError as e:
        if conn: conn.rollback()
        return jsonify({"error": "Erro ao salvar o preço", "detalhes": str(e)}), 500
    finally:
        if conn: conn.close()

@bp.route('/<int:registo_id>/votar', methods=['POST'])
@token_obrigatorio
def votar_preco(usuario_id_token, registo_id):
    data = request.get_json()
    
    if not data or data.get('voto') not in ['positivo', 'negativo']:
        return jsonify({"error": "Envie 'voto' com o valor 'positivo' ou 'negativo'."}), 400

    ajuste = 1 if data['voto'] == 'positivo' else -1
    
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql = "UPDATE registos_preco SET confianca_score = confianca_score + %s WHERE id = %s"
            cursor.execute(sql, (ajuste, registo_id))
            
            if cursor.rowcount == 0:
                return jsonify({"error": "Registo de preço não encontrado."}), 404
            
            conn.commit()
            
        return jsonify({"message": f"Voto {data['voto']} registado com sucesso para o preço #{registo_id}!"}), 200

    except pymysql.MySQLError as e:
        if conn: conn.rollback()
        return jsonify({"error": "Erro ao processar o voto", "detalhes": str(e)}), 500
    finally:
        if conn: conn.close()