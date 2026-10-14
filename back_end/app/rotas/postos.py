from flask import Blueprint, jsonify, request
import pymysql
from ..db import get_db_connection

bp = Blueprint('postos', __name__)

@bp.route('/status', methods=['GET'])
def status():
    return jsonify({"projeto": "Litro de Ouro", "status": "online"}), 200

@bp.route('/', methods=['GET'])
def listar_postos():
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, nome, endereco, bairro, cidade, uf, latitude, longitude FROM postos")
            postos = cursor.fetchall()
        return jsonify(postos), 200
    except pymysql.MySQLError as e:
        return jsonify({"error": "Erro ao procurar postos", "detalhes": str(e)}), 500
    finally:
        if conn: conn.close()

@bp.route('/<int:posto_id>/precos', methods=['GET'])
def listar_precos_posto(posto_id):
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql = """
                SELECT 
                    rp.id AS registo_id, 
                    rp.tipo_combustivel, 
                    rp.preco, 
                    rp.data_registro, 
                    u.nome AS reportado_por
                FROM registos_preco rp
                JOIN usuarios u ON rp.usuario_id = u.id
                WHERE rp.posto_id = %s
                ORDER BY rp.data_registro DESC
            """
            cursor.execute(sql, (posto_id,))
            precos = cursor.fetchall()
            
            if not precos:
                return jsonify({"message": "Nenhum preço registado para este posto ainda."}), 404

        return jsonify(precos), 200

    except pymysql.MySQLError as e:
        return jsonify({"error": "Erro ao buscar os preços", "detalhes": str(e)}), 500
    finally:
        if conn: conn.close()

@bp.route('/menor-preco', methods=['GET'])
def buscar_menor_preco():
    tipo_combustivel = request.args.get('tipo')

    if not tipo_combustivel:
        return jsonify({"error": "Informe o tipo de combustível. Exemplo de uso: /postos/menor-preco?tipo=gasolina_comum"}), 400

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql = """
                SELECT 
                    p.id AS posto_id, 
                    p.nome, 
                    p.endereco, 
                    p.bairro, 
                    rp.preco, 
                    rp.data_registro 
                FROM postos p
                JOIN registos_preco rp ON p.id = rp.posto_id
                INNER JOIN (
                    SELECT posto_id, MAX(data_registro) as data_recente
                    FROM registos_preco
                    WHERE tipo_combustivel = %s
                    GROUP BY posto_id
                ) ultimos ON rp.posto_id = ultimos.posto_id AND rp.data_registro = ultimos.data_recente
                WHERE rp.tipo_combustivel = %s
                ORDER BY rp.preco ASC
            """
            
            cursor.execute(sql, (tipo_combustivel, tipo_combustivel))
            resultados = cursor.fetchall()
            
            if not resultados:
                return jsonify({"message": f"Nenhum preço encontrado para {tipo_combustivel} neste momento."}), 404

        return jsonify(resultados), 200

    except pymysql.MySQLError as e:
        return jsonify({"error": "Erro ao procurar o menor preço", "detalhes": str(e)}), 500
    finally:
        if conn: conn.close()