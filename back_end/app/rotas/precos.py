import math
import os
from urllib.parse import urlparse

import pymysql
from flask import Blueprint, current_app, jsonify, request

from app.db import get_db_connection
from app.utils.decorator import token_required
from app.utils.geofence import GeofenceError, validar_proximidade

precos_bp = Blueprint('precos', __name__)

COMBUSTIVEL_ELETRICO = 'Recarga Elétrica (kWh)'
COMBUSTIVEIS_CONVENCIONAIS = ('Gasolina Comum', 'Gasolina Aditivada', 'Etanol', 'Diesel')
COMBUSTIVEIS_VALIDOS = COMBUSTIVEIS_CONVENCIONAIS + (COMBUSTIVEL_ELETRICO,)

# Evita "karma farming": mesmo utilizador, mesmo posto, mesmo combustível. 0 desativa (testes).
try:
    COOLDOWN_MINUTOS = max(0, int(os.getenv('PRECO_COOLDOWN_MIN', '15')))
except ValueError:
    COOLDOWN_MINUTOS = 15

# Prova fotográfica (Dropbox). O valor vem do CLIENTE, então nunca é gravado sem validação.
FOTO_URL_MAX = 500  # tamanho da coluna registos_preco.foto_url (VARCHAR(500))
FOTO_HOSTS = ('dropbox.com', 'www.dropbox.com', 'dl.dropboxusercontent.com')


def _validar_foto_url(bruto):
    """Devolve (url, erro). url=None sem erro significa "registro manual, sem foto"."""
    if bruto is None:
        return None, None
    if not isinstance(bruto, str):
        return None, "O campo 'foto_url' deve ser texto."
    
    url = bruto.strip()
    if not url:
        return None, None
        
    if len(url) > FOTO_URL_MAX:
        return None, f"O campo 'foto_url' excede {FOTO_URL_MAX} caracteres."
        
    if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url):
        return None, "O campo 'foto_url' contém caracteres inválidos."
        
    try:
        partes = urlparse(url)
        host = partes.hostname  # já em minúsculas; levanta ValueError se a porta for inválida
        partes.port
    except ValueError:
        return None, "O campo 'foto_url' não é uma URL válida."
        
    if partes.scheme != 'https' or host not in FOTO_HOSTS or partes.username or partes.password:
        return None, "A foto deve ser um link https do Dropbox gerado pela leitura do totem."
        
    return url, None


@precos_bp.route('', methods=['POST'], strict_slashes=False)
@token_required
def registrar_preco(usuario_id_token):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Envie um JSON válido."}), 400

    campos_necessarios = ['posto_id', 'tipo_combustivel', 'preco', 'latitude', 'longitude']
    if not all(campo in data for campo in campos_necessarios):
        return jsonify({"error": "Dados incompletos! Informe posto_id, tipo_combustivel, preco, latitude e longitude."}), 400

    try:
        posto_id = int(data['posto_id'])
    except (TypeError, ValueError):
        return jsonify({"error": "O campo 'posto_id' deve ser um número inteiro."}), 400

    tipo_combustivel = str(data['tipo_combustivel']).strip()
    if tipo_combustivel not in COMBUSTIVEIS_VALIDOS:
        return jsonify({"error": "Combustível inválido.", "validos": list(COMBUSTIVEIS_VALIDOS)}), 400

    try:
        preco_informado = float(data['preco'])
    except (TypeError, ValueError):
        return jsonify({"error": "O campo 'preco' deve ser um número válido."}), 400

    if not math.isfinite(preco_informado) or not (1.00 <= preco_informado <= 25.00):
        return jsonify({"error": "O preço informado está fora dos limites aceitáveis (entre R$ 1,00 e R$ 25,00)."}), 400

    foto_url, erro_foto = _validar_foto_url(data.get('foto_url'))
    if erro_foto:
        return jsonify({"error": erro_foto, "codigo": "FOTO_INVALIDA"}), 400

    # Android informa quando a localização vem de app de "localização falsa". É declarado pelo
    # próprio cliente, então só barra o uso casual; não substitui outras defesas.
    if data.get('simulada') is True:
        return jsonify({"error": "Localização simulada não é aceite para registrar preços.", "codigo": "GPS_SIMULADO"}), 403

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT latitude, longitude, nome, tipo_posto FROM postos WHERE id = %s", (posto_id,))
            posto = cursor.fetchone()

            if not posto or posto['latitude'] is None or posto['longitude'] is None:
                return jsonify({"error": "Posto não encontrado ou sem coordenadas geográficas."}), 404

            eletroposto = posto.get('tipo_posto') == 'Eletroposto'
            if eletroposto != (tipo_combustivel == COMBUSTIVEL_ELETRICO):
                return jsonify({"error": "Este combustível não corresponde ao tipo do posto selecionado."}), 400

            # 1. GEOFENCING (antes de qualquer escrita). Aqui `latitude`/`longitude` DEVEM ser
            #    as do aparelho do utilizador, não as do posto.
            try:
                resultado = validar_proximidade(
                    data.get('latitude'), data.get('longitude'), data.get('precisao_m'),
                    posto['latitude'], posto['longitude'],
                )
            except GeofenceError as e:
                corpo, status = e.para_resposta()
                return jsonify(corpo), status

            # 2. Limite de frequência
            if COOLDOWN_MINUTOS:
                cursor.execute(
                    """
                    SELECT 1 FROM registos_preco
                    WHERE usuario_id = %s AND posto_id = %s AND tipo_combustivel = %s
                      AND data_registro > NOW() - INTERVAL %s MINUTE
                    LIMIT 1
                    """,
                    (usuario_id_token, posto_id, tipo_combustivel, COOLDOWN_MINUTOS),
                )
                if cursor.fetchone():
                    return jsonify({
                        "error": f"Você já registrou este combustível neste posto há menos de {COOLDOWN_MINUTOS} minutos.",
                        "codigo": "REGISTRO_RECENTE",
                    }), 429

            # 3. Inserir preço
            cursor.execute(
                """
                INSERT INTO registos_preco (posto_id, usuario_id, tipo_combustivel, preco, confianca_score, foto_url, data_registro)
                VALUES (%s, %s, %s, %s, 1, %s, NOW())
                """,
                (posto_id, usuario_id_token, tipo_combustivel, preco_informado, foto_url),
            )

            # 4. RECOMPENSA DE KARMA: +5 Pontos
            cursor.execute("UPDATE usuarios SET karma = karma + 5 WHERE id = %s", (usuario_id_token,))

            conn.commit()

        return jsonify({
            "message": "Preço registrado com sucesso! Ganhou +5 pontos de Karma!",
            "distancia_verificada_metros": round(resultado.distancia_m, 2),
        }), 201

    except pymysql.MySQLError:
        if conn: conn.rollback()
        current_app.logger.exception('Erro MySQL ao registrar preço')
        return jsonify({"error": "Erro ao salvar o preço."}), 500
    except Exception:
        if conn: conn.rollback()
        current_app.logger.exception('Erro inesperado ao registrar preço')
        return jsonify({"error": "Erro interno ao registrar o preço."}), 500
    finally:
        if conn: conn.close()


@precos_bp.route('/<int:registo_id>/votar', methods=['POST'], strict_slashes=False)
@token_required
def votar_preco(usuario_id_token, registo_id):
    # Lógica de votação original, intocada.
    data = request.get_json()
    if not data or data.get('voto') not in ['positivo', 'negativo']:
        return jsonify({"error": "Envie 'voto' com o valor 'positivo' ou 'negativo'."}), 400

    novo_voto = data['voto']

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT usuario_id FROM registos_preco WHERE id = %s", (registo_id,))
            registo = cursor.fetchone()

            if not registo:
                return jsonify({"error": "Registro de preço não encontrado."}), 404

            autor_id = registo['usuario_id']

            if autor_id == usuario_id_token:
                return jsonify({"error": "Não pode votar na sua própria publicação de preço."}), 400

            cursor.execute("SELECT tipo_voto FROM votos_registos WHERE usuario_id = %s AND registo_id = %s", (usuario_id_token, registo_id))
            voto_existente = cursor.fetchone()

            if not voto_existente:
                delta_score = 1 if novo_voto == 'positivo' else -1
                delta_karma = 2 if novo_voto == 'positivo' else -2
                cursor.execute("INSERT INTO votos_registos (registo_id, usuario_id, tipo_voto) VALUES (%s, %s, %s)", (registo_id, usuario_id_token, novo_voto))
            elif voto_existente['tipo_voto'] == novo_voto:
                return jsonify({"message": "Já registrou este mesmo voto para este preço."}), 200
            else:
                delta_score = 2 if novo_voto == 'positivo' else -2
                delta_karma = 4 if novo_voto == 'positivo' else -4
                cursor.execute("UPDATE votos_registos SET tipo_voto = %s WHERE usuario_id = %s AND registo_id = %s", (novo_voto, usuario_id_token, registo_id))

            cursor.execute("UPDATE registos_preco SET confianca_score = confianca_score + %s WHERE id = %s", (delta_score, registo_id))
            cursor.execute("UPDATE usuarios SET karma = karma + %s WHERE id = %s", (delta_karma, autor_id))

            conn.commit()

        return jsonify({"message": f"Voto '{novo_voto}' registrado com sucesso!"}), 200

    except pymysql.MySQLError as e:
        if conn: conn.rollback()
        return jsonify({"error": "Erro ao processar o voto", "detalhes": str(e)}), 500
    finally:
        if conn: conn.close()