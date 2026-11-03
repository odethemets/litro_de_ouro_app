import os

from flask import Blueprint, current_app, jsonify, request

from ..db import get_db_connection
from ..utils.decorator import token_required
from ..utils.geofence import GeofenceError, validar_coordenadas, haversine_m
from services.grid_postos import delta_graus, garantir_cobertura_async
from services.mapbox_service import buscar_postos_por_bbox

postos_bp = Blueprint('postos', __name__)

RAIO_PADRAO_KM = 25.0
RAIO_MAX_KM = 50.0
LIMITE_SEM_COORDENADAS = 500   # modo legado (sem lat/lng): tela de registrar preço lista todos
COMBUSTIVEL_PADRAO = 'Gasolina Comum'
COMBUSTIVEL_ELETRICO = 'Recarga Elétrica (kWh)'

# Preço e data vêm da MESMA linha (a mais recente do combustível principal do posto), numa só
# subconsulta correlacionada. Antes eram duas subconsultas separadas e sem filtro de combustível:
# um preço de Diesel recente era exibido como "gasolina" e pintava o pino.
# `{where}` recebe apenas texto fixo definido neste ficheiro; todos os valores vão por parâmetros.
SQL_POSTOS = """
    SELECT p.id, p.nome, p.bairro, p.endereco, p.latitude, p.longitude,
           p.horario_funcionamento, p.tipo_posto,
           rp.preco AS preco_gasolina, rp.data_registro AS data_atualizacao
    FROM postos p
    LEFT JOIN registos_preco rp ON rp.id = (
        SELECT r2.id FROM registos_preco r2
        WHERE r2.posto_id = p.id
          AND r2.tipo_combustivel = CASE WHEN p.tipo_posto = 'Eletroposto' THEN %s ELSE %s END
        ORDER BY r2.data_registro DESC, r2.id DESC
        LIMIT 1
    )
    {where}
    ORDER BY p.id
    LIMIT %s
"""


def _erro_coordenadas(e: GeofenceError):
    corpo, _ = e.para_resposta()
    return jsonify(corpo), 400


def _ler_raio_km():
    bruto = request.args.get('raio_km')
    if bruto is None:
        return RAIO_PADRAO_KM
    try:
        valor = float(bruto)
    except ValueError:
        return RAIO_PADRAO_KM
    if not (valor > 0):  # também descarta NaN
        return RAIO_PADRAO_KM
    return min(valor, RAIO_MAX_KM)


@postos_bp.route('', methods=['GET'], strict_slashes=False)

def listar_postos():
    lat_arg, lng_arg = request.args.get('lat'), request.args.get('lng')

    centro = None
    raio_km = RAIO_PADRAO_KM
    if lat_arg is not None or lng_arg is not None:
        try:
            centro = validar_coordenadas(lat_arg, lng_arg)
        except GeofenceError as e:
            return _erro_coordenadas(e)
        raio_km = _ler_raio_km()

    # 1. SINCRONIZAÇÃO COM O MAPBOX: em segundo plano, nunca bloqueia nem derruba esta rota.
    #    A resposta abaixo vem só do nosso banco; postos novos aparecem na próxima consulta.
    if centro and os.getenv('MAPBOX_TOKEN'):
        try:
            garantir_cobertura_async(get_db_connection, centro[0], centro[1], raio_km, buscar_postos_por_bbox)
        except Exception:
            current_app.logger.exception('Falha ao agendar sincronização com o Mapbox')

    # 2. LEITURA DO NOSSO BANCO
    conn = None
    try:
        if centro:
            dlat, dlon = delta_graus(centro[0], raio_km)
            where = 'WHERE p.latitude BETWEEN %s AND %s AND p.longitude BETWEEN %s AND %s'
            filtros = [centro[0] - dlat, centro[0] + dlat, centro[1] - dlon, centro[1] + dlon]
            limite = LIMITE_SEM_COORDENADAS
        else:
            where, filtros, limite = '', [], LIMITE_SEM_COORDENADAS

        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                SQL_POSTOS.format(where=where),
                [COMBUSTIVEL_ELETRICO, COMBUSTIVEL_PADRAO, *filtros, limite],
            )
            postos_db = cursor.fetchall()

        resultado = []
        for posto in postos_db:
            posto['preco_gasolina'] = float(posto['preco_gasolina']) if posto['preco_gasolina'] else 0.00
            posto['latitude'] = float(posto['latitude'])
            posto['longitude'] = float(posto['longitude'])
            if not posto.get('horario_funcionamento'):
                posto['horario_funcionamento'] = '24 Horas'
            data = posto.get('data_atualizacao')
            posto['data_atualizacao'] = data.isoformat() if data else None

            if centro:
                distancia = haversine_m(centro[0], centro[1], posto['latitude'], posto['longitude'])
                if distancia > raio_km * 1000:  # a caixa SQL é um quadrado; o corte real é circular
                    continue
                posto['distancia_m'] = round(distancia)
            resultado.append(posto)

        if centro:
            resultado.sort(key=lambda p: p['distancia_m'])

        return jsonify(resultado), 200
    except Exception:
        current_app.logger.exception('Erro ao listar postos')
        return jsonify({"error": "Erro interno ao listar postos."}), 500
    finally:
        if conn and conn.open:
            conn.close()


# >>> MANTENHA AQUI a sua rota GET /postos/menores-precos (o ficheiro enviado dizia "continua igual"
# >>> mas ela não veio no texto; o menor_preco.tsx do app depende dela). Não a apague.


@postos_bp.route('/<int:posto_id>/historico', methods=['GET'], strict_slashes=False)
def historico_precos(posto_id):
    tipo_combustivel = request.args.get('tipo_combustivel', 'Gasolina Comum')
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # '%%' no DATE_FORMAT para o PyMySQL não confundir com '%s'
            cursor.execute("""
                SELECT id as registo_id, preco,
                       DATE_FORMAT(data_registro, '%%d/%%m/%%Y %%H:%%i') as data_formatada
                FROM registos_preco
                WHERE posto_id = %s AND tipo_combustivel = %s
                ORDER BY data_registro DESC
                LIMIT 5
            """, (posto_id, tipo_combustivel))

            historico = cursor.fetchall()
            for h in historico:
                h['preco'] = float(h['preco'])

        return jsonify(historico), 200
    except Exception:
        current_app.logger.exception('Erro no histórico do posto %s', posto_id)
        return jsonify({"error": "Erro interno ao buscar o histórico."}), 500
    finally:
        if conn and conn.open:
            conn.close()

@postos_bp.route('/<int:posto_id>/precos', methods=['GET'], strict_slashes=False)
def precos_atuais_posto(posto_id):
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Busca o registo mais recente (MAX(id)) de CADA tipo de combustível para este posto
            cursor.execute("""
                SELECT tipo_combustivel, preco, DATE_FORMAT(data_registro, '%%d/%%m/%%Y') as data_formatada
                FROM registos_preco
                WHERE id IN (
                    SELECT MAX(id) 
                    FROM registos_preco 
                    WHERE posto_id = %s 
                    GROUP BY tipo_combustivel
                )
                ORDER BY tipo_combustivel
            """, (posto_id,))
            
            precos = cursor.fetchall()
            
            # Formata o preço para garantir que não dá erro no JSON
            for p in precos:
                p['preco'] = float(p['preco'])
                
        return jsonify(precos), 200
        
    except Exception:
        current_app.logger.exception('Erro ao buscar precos do posto %s', posto_id)
        return jsonify({"error": "Erro interno ao buscar preços."}), 500
    finally:
        if conn and conn.open:
            conn.close()

# app/rotas/postos.py (adicione no final do ficheiro)

@postos_bp.route('/<int:posto_id>/precos', methods=['POST'], strict_slashes=False)
@token_required
def cadastrar_preco(current_user_id, posto_id):
    data = request.get_json(silent=True) or {}
    tipo_combustivel = data.get('tipo_combustivel')
    preco = data.get('preco')

    if not tipo_combustivel or preco is None:
        return jsonify({"error": "Informe o tipo de combustível e o preço."}), 400

    try:
        preco_float = float(preco)
        if preco_float <= 0 or preco_float > 20:
            return jsonify({"error": "Preço fora dos limites permitidos."}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Valor de preço inválido."}), 400

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Verifica se o posto existe
            cursor.execute("SELECT id FROM postos WHERE id = %s", (posto_id,))
            if not cursor.fetchone():
                return jsonify({"error": "Posto não encontrado."}), 404

            # Regista o novo preço com data/hora UTC centralizada no servidor
            cursor.execute("""
                INSERT INTO registos_preco (posto_id, usuario_id, tipo_combustivel, preco, data_registro)
                VALUES (%s, %s, %s, %s, NOW())
            """, (posto_id, current_user_id, tipo_combustivel, preco_float))
            conn.commit()

        return jsonify({"message": "Preço registrado com sucesso!"}), 201

    except Exception:
        current_app.logger.exception('Erro ao cadastrar preço para posto %s', posto_id)
        return jsonify({"error": "Erro interno ao salvar preço."}), 500
    finally:
        if conn and conn.open:
            conn.close()