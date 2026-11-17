"""Confirmação explícita de oferta; não modifica registros de preço."""
import math

from flask import Blueprint, current_app, jsonify, request

from app.db import get_db_connection
from app.utils.decorator import token_required
from app.utils.geofence import GeofenceError, validar_proximidade
from services.catalogo_postos import CATALOGO

ofertas_bp = Blueprint("ofertas", __name__)


@ofertas_bp.post("/postos/<int:posto_id>/ofertas/<codigo>/confirmar")
@token_required
def confirmar_oferta(usuario_id, posto_id, codigo):
    dados = request.get_json(silent=True)
    if codigo not in CATALOGO or not isinstance(dados, dict):
        return jsonify(error="Informe um produto e objeto JSON válidos."), 400
    if dados.get("confirmado") is not True:
        return jsonify(error="Confirme explicitamente que verificou a oferta."), 400
    if dados.get("simulada") is not False:
        return jsonify(error="Localização simulada ou não verificada."), 403
    precisao = dados.get("precisao_m")
    if (isinstance(precisao, bool) or not isinstance(precisao, (int, float))
            or not math.isfinite(precisao) or precisao < 0):
        return jsonify(error="Informe a precisão da localização atual."), 400
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Serializa confirmações inclusive quando a relação ainda não existe.
            cursor.execute("SELECT latitude,longitude,tipo_posto FROM postos WHERE id=%s FOR UPDATE", (posto_id,))
            posto = cursor.fetchone()
            if not posto:
                return jsonify(error="Posto não encontrado."), 404
            if (posto["tipo_posto"] == "Eletroposto") != (codigo == "recarga_eletrica"):
                return jsonify(error="Produto incompatível com o tipo do posto."), 400
            try:
                validar_proximidade(dados.get("latitude"), dados.get("longitude"), precisao,
                                    posto["latitude"], posto["longitude"])
            except GeofenceError as erro:
                corpo, status = erro.para_resposta()
                return jsonify(corpo), status
            cursor.execute("""
                SELECT disponivel_manual,disponivel_osm FROM postos_combustiveis
                WHERE posto_id=%s AND combustivel_codigo=%s FOR UPDATE
            """, (posto_id, codigo))
            oferta = cursor.fetchone() or {}
            manual, osm = oferta.get("disponivel_manual"), oferta.get("disponivel_osm")
            efetivo = manual if manual is not None else osm
            if efetivo == 0:
                return jsonify(error="Oferta marcada como indisponível. Requer revisão."), 409
            if efetivo is None:
                cursor.execute("""
                    INSERT INTO postos_combustiveis
                        (posto_id,combustivel_codigo,disponivel_manual,manual_atualizado_em,manual_atualizado_por)
                    VALUES (%s,%s,1,UTC_TIMESTAMP(),%s)
                    ON DUPLICATE KEY UPDATE disponivel_manual=1,
                        manual_atualizado_em=UTC_TIMESTAMP(),manual_atualizado_por=VALUES(manual_atualizado_por)
                """, (posto_id, codigo, usuario_id))
            conn.commit()
            return jsonify(posto_id=posto_id, codigo=codigo, disponivel=True,
                           origem="manual" if manual is not None or efetivo is None else "osm"), 200
    except Exception:
        if conn is not None:
            conn.rollback()
        current_app.logger.exception("Falha ao confirmar oferta")
        return jsonify(error="Não foi possível confirmar a oferta. Atualize os dados antes de repetir."), 503
    finally:
        if conn is not None:
            conn.close()
