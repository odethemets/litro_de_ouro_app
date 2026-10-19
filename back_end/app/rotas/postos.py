from flask import Blueprint, jsonify
from ..db import get_db_connection
import pymysql

bp = Blueprint('postos', __name__)

# Como o prefixo '/postos' já está no create_app(), a rota base aqui é vazia ou '/'
@bp.route('', methods=['GET'], strict_slashes=False)
@bp.route('/', methods=['GET'], strict_slashes=False)
def listar_postos():
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT id, nome, endereco, bairro, cidade, uf, latitude, longitude, preco_gasolina FROM postos")
            linhas = cursor.fetchall()

        resultado = []
        for row in linhas:
            resultado.append({
                'id': row['id'],
                'nome': str(row.get('nome', 'Posto')),
                'endereco': str(row.get('endereco', '')),
                'bairro': str(row.get('bairro', '')),
                'cidade': str(row.get('cidade', '')),
                'uf': str(row.get('uf', '')),
                'latitude': float(row['latitude']) if row.get('latitude') is not None else 0.0,
                'longitude': float(row['longitude']) if row.get('longitude') is not None else 0.0,
                'preco_gasolina': float(row['preco_gasolina']) if row.get('preco_gasolina') is not None else 0.0
            })

        return jsonify(resultado), 200

    except Exception as e:
        print(f"\n[ERRO NA ROTA POSTOS]: {e}\n")
        return jsonify({'error': str(e)}), 500

    finally:
        if conn:
            conn.close()