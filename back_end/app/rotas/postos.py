from flask import Blueprint, current_app, jsonify, request

from ..db import get_db_connection
from ..utils.decorator import token_required
from ..utils.geofence import (
    GeofenceError,
    validar_coordenadas,
    haversine_m,
)

from services.grid_postos import (
    delta_graus,
    garantir_cobertura_async,
)

# Nova fonte de descoberta: OpenStreetMap via Overpass.
from services.osm_service import (
    ATRIBUICAO,
    LICENCA_URL,
    OSMIndisponivel,
    buscar_postos_por_bbox,
    dentro_da_area,
    sincronizacao_habilitada,
)


postos_bp = Blueprint("postos", __name__)

RAIO_PADRAO_KM = 25.0
RAIO_MAX_KM = 50.0

LIMITE_SEM_COORDENADAS = 500

COMBUSTIVEL_PADRAO = "Gasolina Comum"
COMBUSTIVEL_ELETRICO = "Recarga Elétrica (kWh)"


# Mantém preço e data da mesma publicação.
# Para eletropostos, usa recarga elétrica; nos demais, gasolina comum.
#
# O trecho {where} recebe somente SQL fixo definido neste arquivo.
# Todos os valores recebidos são enviados como parâmetros.
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

    # A importação só acontece com OSM_SYNC_ENABLED=true.
    # Consultas fora da área configurada continuam lendo o banco,
    # mas não disparam descoberta externa.
    #
    # O trabalho ocorre em segundo plano. A resposta desta requisição
    # pode conter apenas os postos que já estavam cadastrados.
    if centro and sincronizacao_habilitada():
        try:
            if dentro_da_area(*centro):
                garantir_cobertura_async(
                    get_db_connection,
                    centro[0],
                    centro[1],
                    raio_km,
                    buscar_postos_por_bbox,
                )
        except Exception:
            current_app.logger.exception(
                "Falha ao agendar sincronização com OpenStreetMap"
            )

    # Mantém a listagem baseada nos registros locais.
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

            # Não apresentar funcionamento 24h sem essa informação.
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

                # O filtro SQL usa uma caixa.
                # Aqui mantemos somente o círculo solicitado.
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
    """
    Consulta autenticada de prévia.

    Não abre conexão com o MySQL.
    Não insere postos.
    Não inicia o sincronizador.
    """

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

        # Caixa pequena para o primeiro teste:
        # aproximadamente 2 km por lado.
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
            {"Retry-After": "30"},
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


# Se houver uma implementação adicional de /menores-precos
# no seu arquivo local, mantenha essa implementação aqui.
# Ela não estava presente no arquivo enviado.


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
    # Mantém o comportamento da rota existente.
    data = request.get_json(silent=True) or {}

    tipo_combustivel = data.get("tipo_combustivel")
    preco = data.get("preco")

    if not tipo_combustivel or preco is None:
        return jsonify({
            "error": "Informe o tipo de combustível e o preço."
        }), 400

    try:
        preco_float = float(preco)

        if preco_float <= 0 or preco_float > 20:
            return jsonify({
                "error": "Preço fora dos limites permitidos."
            }), 400

    except (ValueError, TypeError):
        return jsonify({
            "error": "Valor de preço inválido."
        }), 400

    conn = None

    try:
        conn = get_db_connection()

        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM postos WHERE id = %s",
                (posto_id,),
            )

            if not cursor.fetchone():
                return jsonify({
                    "error": "Posto não encontrado."
                }), 404

            cursor.execute(
                """
                INSERT INTO registos_preco (
                    posto_id,
                    usuario_id,
                    tipo_combustivel,
                    preco,
                    data_registro
                )
                VALUES (%s, %s, %s, %s, NOW())
                """,
                (
                    posto_id,
                    current_user_id,
                    tipo_combustivel,
                    preco_float,
                ),
            )

            conn.commit()

        return jsonify({
            "message": "Preço registrado com sucesso!"
        }), 201

    except Exception:
        current_app.logger.exception(
            "Erro ao cadastrar preço para posto %s",
            posto_id,
        )

        return jsonify({
            "error": "Erro interno ao salvar preço."
        }), 500

    finally:
        if conn and conn.open:
            conn.close()