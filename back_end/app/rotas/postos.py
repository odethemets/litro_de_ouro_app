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

COMBUSTIVEL_PADRAO = "Gasolina Comum"
COMBUSTIVEL_ELETRICO = "Recarga Elétrica (kWh)"


# Preço e data pertencem à mesma publicação.
# O trecho {where} recebe somente SQL fixo definido neste arquivo.
SQL_POSTOS = """
    SELECT
        p.id,
        p.nome,
        p.bairro,
        p.endereco,
        p.latitude,
        p.longitude,
        p.horario_funcionamento,
        p.tipo_posto,
        rp.preco AS preco_gasolina,
        rp.data_registro AS data_atualizacao
    FROM postos p
    LEFT JOIN registos_preco rp ON rp.id = (
        SELECT r2.id
        FROM registos_preco r2
        WHERE r2.posto_id = p.id
          AND r2.tipo_combustivel = CASE
              WHEN p.tipo_posto = 'Eletroposto' THEN %s
              ELSE %s
          END
        ORDER BY r2.data_registro DESC, r2.id DESC
        LIMIT 1
    )
    {where}
    ORDER BY p.id
    LIMIT %s
"""


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

    # A listagem pública consulta somente o MySQL.
    # A importação OSM é executada pelo script administrativo.
    conn = None

    try:
        if centro:
            dlat, dlon = delta_graus(centro[0], raio_km)

            where = (
                "WHERE p.latitude BETWEEN %s AND %s "
                "AND p.longitude BETWEEN %s AND %s"
            )

            filtros = [
                centro[0] - dlat,
                centro[0] + dlat,
                centro[1] - dlon,
                centro[1] + dlon,
            ]

            limite = LIMITE_SEM_COORDENADAS

        else:
            where = ""
            filtros = []
            limite = LIMITE_SEM_COORDENADAS

        conn = get_db_connection()

        with conn.cursor() as cursor:
            cursor.execute(
                SQL_POSTOS.format(where=where),
                [
                    COMBUSTIVEL_ELETRICO,
                    COMBUSTIVEL_PADRAO,
                    *filtros,
                    limite,
                ],
            )

            postos_db = cursor.fetchall()

        resultado = []

        for posto in postos_db:
            posto["preco_gasolina"] = (
                float(posto["preco_gasolina"])
                if posto["preco_gasolina"]
                else 0.00
            )

            posto["latitude"] = float(posto["latitude"])
            posto["longitude"] = float(posto["longitude"])

            if not posto.get("horario_funcionamento"):
                posto["horario_funcionamento"] = (
                    "Horário não informado"
                )

            data = posto.get("data_atualizacao")

            posto["data_atualizacao"] = (
                data.isoformat() if data else None
            )

            if centro:
                distancia = haversine_m(
                    centro[0],
                    centro[1],
                    posto["latitude"],
                    posto["longitude"],
                )

                # A caixa SQL é refinada para o raio circular.
                if distancia > raio_km * 1000:
                    continue

                posto["distancia_m"] = round(distancia)

            resultado.append(posto)

        if centro:
            resultado.sort(
                key=lambda posto: posto["distancia_m"]
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