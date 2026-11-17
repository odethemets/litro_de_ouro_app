from flask import Blueprint, current_app, jsonify, request

from ..db import get_db_connection
from ..utils.decorator import token_required
from ..utils.geofence import (
    GeofenceError,
    validar_coordenadas,
    haversine_m,
)
from .precos import registrar_preco_validado

from services.grid_postos import delta_graus
from services.catalogo_postos import consultar_catalogo, validar_filtros
from services.osm_service import (
    ATRIBUICAO,
    LICENCA_URL,
    OSMIndisponivel,
    buscar_postos_por_bbox,
    dentro_da_area,
)


postos_bp = Blueprint("postos", __name__)

RAIO_PADRAO_KM = 25.0
RAIO_MAX_KM = 50.0

LIMITE_SEM_COORDENADAS = 500

def _erro_coordenadas(erro: GeofenceError):
    corpo, _ = erro.para_resposta()
    return jsonify(corpo), 400


def _ler_raio_km():
    bruto = request.args.get("raio_km")

    if bruto is None:
        return RAIO_PADRAO_KM

    try:
        valor = float(bruto)
    except ValueError:
        return RAIO_PADRAO_KM

    # Também rejeita NaN.
    if not (valor > 0):
        return RAIO_PADRAO_KM

    return min(valor, RAIO_MAX_KM)


@postos_bp.route("", methods=["GET"], strict_slashes=False)
def listar_postos():
    lat_arg = request.args.get("lat")
    lng_arg = request.args.get("lng")

    centro = None
    raio_km = RAIO_PADRAO_KM

    if lat_arg is not None or lng_arg is not None:
        try:
            centro = validar_coordenadas(lat_arg, lng_arg)
        except GeofenceError as erro:
            return _erro_coordenadas(erro)

        raio_km = _ler_raio_km()

    try:
        filtros = validar_filtros(request.args)
    except ValueError as erro:
        return jsonify({"error": str(erro)}), 400

    conn = None
    try:
        conn = get_db_connection()
        resultado = consultar_catalogo(
            conn, centro, raio_km, LIMITE_SEM_COORDENADAS, filtros, haversine_m
        )
        return jsonify(resultado), 200

    except Exception:
        current_app.logger.exception("Erro ao listar postos")

        return jsonify({
            "error": "Erro interno ao listar postos."
        }), 500

    finally:
        if conn and conn.open:
            conn.close()


@postos_bp.route("/descoberta", methods=["GET"])
@token_required
def previa_descoberta(current_user_id):
    """Prévia autenticada da OSM, sem gravação no MySQL."""
    try:
        lat, lon = validar_coordenadas(
            request.args.get("lat"),
            request.args.get("lng"),
        )

    except GeofenceError as erro:
        return _erro_coordenadas(erro)

    try:
        if not dentro_da_area(lat, lon):
            return jsonify({
                "error": (
                    "Localização fora da área de descoberta "
                    "configurada."
                )
            }), 400

        # Caixa pequena de aproximadamente 2 km por lado.
        dlat, dlon = delta_graus(lat, 1.0)

        resultado = buscar_postos_por_bbox((
            lat - dlat,
            lon - dlon,
            lat + dlat,
            lon + dlon,
        ))

        return jsonify({
            "fonte": "OpenStreetMap",
            "atribuicao": ATRIBUICAO,
            "licenca_url": LICENCA_URL,
            "somente_previa": True,
            "total": len(resultado.lugares),
            "postos": resultado.lugares,
        }), 200

    except OSMIndisponivel as erro:
        return (
            jsonify({"error": str(erro)}),
            503,
            {"Retry-After": str(erro.retry_after)},
        )

    except ValueError:
        current_app.logger.error(
            "Confira a configuração OSM_AREA_BBOX."
        )

        return jsonify({
            "error": (
                "Área de descoberta configurada incorretamente."
            )
        }), 503


@postos_bp.route(
    "/<int:posto_id>/historico",
    methods=["GET"],
    strict_slashes=False,
)
def historico_precos(posto_id):
    tipo_combustivel = request.args.get(
        "tipo_combustivel",
        "Gasolina Comum",
    )

    conn = None

    try:
        conn = get_db_connection()

        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id AS registo_id,
                    preco,
                    DATE_FORMAT(
                        data_registro,
                        '%%d/%%m/%%Y %%H:%%i'
                    ) AS data_formatada
                FROM registos_preco
                WHERE posto_id = %s
                  AND tipo_combustivel = %s
                ORDER BY data_registro DESC
                LIMIT 5
                """,
                (posto_id, tipo_combustivel),
            )

            historico = cursor.fetchall()

            for registro in historico:
                registro["preco"] = float(registro["preco"])

        return jsonify(historico), 200

    except Exception:
        current_app.logger.exception(
            "Erro no histórico do posto %s",
            posto_id,
        )

        return jsonify({
            "error": "Erro interno ao buscar o histórico."
        }), 500

    finally:
        if conn and conn.open:
            conn.close()


@postos_bp.route(
    "/<int:posto_id>/precos",
    methods=["GET"],
    strict_slashes=False,
)
def precos_atuais_posto(posto_id):
    conn = None

    try:
        conn = get_db_connection()

        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    tipo_combustivel,
                    preco,
                    DATE_FORMAT(
                        data_registro,
                        '%%d/%%m/%%Y'
                    ) AS data_formatada
                FROM registos_preco
                WHERE id IN (
                    SELECT MAX(id)
                    FROM registos_preco
                    WHERE posto_id = %s
                    GROUP BY tipo_combustivel
                )
                ORDER BY tipo_combustivel
                """,
                (posto_id,),
            )

            precos = cursor.fetchall()

            for registro in precos:
                registro["preco"] = float(registro["preco"])

        return jsonify(precos), 200

    except Exception:
        current_app.logger.exception(
            "Erro ao buscar precos do posto %s",
            posto_id,
        )

        return jsonify({
            "error": "Erro interno ao buscar preços."
        }), 500

    finally:
        if conn and conn.open:
            conn.close()


@postos_bp.route(
    "/<int:posto_id>/precos",
    methods=["POST"],
    strict_slashes=False,
)
@token_required
def cadastrar_preco(current_user_id, posto_id):
    # Mantém a URL utilizada pelo aplicativo.
    # Todas as validações são compartilhadas com POST /precos.
    return registrar_preco_validado(
        current_user_id,
        request.get_json(silent=True),
        posto_id_rota=posto_id,
    )