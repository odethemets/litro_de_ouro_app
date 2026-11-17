"""Votos sobre registros exatos, sem limiar automático de validação."""
from flask import Blueprint, current_app, jsonify, request

from app.db import get_db_connection
from app.utils.decorator import token_required
from services.atividade_alertas import registrar_karma

votos_bp = Blueprint("votos", __name__)


# Reúne contagens e voto da sessão para o registro exato exibido na interface.
def resumo(cursor, registo_id, usuario_id):
    cursor.execute("""
        SELECT r.id AS registo_id,r.usuario_id,r.confianca_score,
               COALESCE(SUM(v.tipo_voto='positivo'),0) AS positivos,
               COALESCE(SUM(v.tipo_voto='negativo'),0) AS negativos,
               MAX(CASE WHEN v.usuario_id=%s THEN v.tipo_voto END) AS meu_voto
        FROM registos_preco r LEFT JOIN votos_registos v ON v.registo_id=r.id
        WHERE r.id=%s GROUP BY r.id,r.usuario_id,r.confianca_score
    """, (usuario_id, registo_id))
    item = cursor.fetchone()
    if item:
        item["pode_votar"] = item.pop("usuario_id") != usuario_id
        for campo in ("positivos", "negativos", "confianca_score"):
            item[campo] = int(item[campo] or 0)
    return item


# Consulta ou grava avaliações; concentra locks, repetição/troca e efeito no Karma.
@votos_bp.route("/precos/<int:registo_id>/votos", methods=["GET"])
@votos_bp.route("/precos/<int:registo_id>/votar", methods=["POST"])
@token_required
def votos(usuario_id, registo_id):
    gravar = request.method == "POST"
    dados = request.get_json(silent=True) if gravar else None
    if gravar and (not isinstance(dados, dict) or dados.get("voto") not in ("positivo", "negativo")):
        return jsonify(error="Envie voto positivo ou negativo."), 400
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Ordem igual ao cadastro: conta autora, depois registro.
            cursor.execute("SELECT usuario_id FROM registos_preco WHERE id=%s", (registo_id,))
            registro = cursor.fetchone()
            if not registro:
                return jsonify(error="Registro de preço não encontrado."), 404
            if gravar:
                autor = registro["usuario_id"]
                if autor == usuario_id:
                    return jsonify(error="Não pode votar no próprio preço."), 400
                # Descarta o snapshot da consulta inicial antes de aguardar locks.
                # Trocas concorrentes devem enxergar todo o histórico já confirmado.
                conn.rollback()
                cursor.execute("SELECT id FROM usuarios WHERE id=%s FOR UPDATE", (autor,))
                cursor.execute("SELECT usuario_id FROM registos_preco WHERE id=%s FOR UPDATE", (registo_id,))
                if not cursor.fetchone():
                    return jsonify(error="Registro de preço não encontrado."), 404
                cursor.execute("SELECT id,tipo_voto FROM votos_registos WHERE usuario_id=%s AND registo_id=%s FOR UPDATE", (usuario_id, registo_id))
                anterior = cursor.fetchone()
                novo = dados["voto"]
                if not anterior or anterior["tipo_voto"] != novo:
                    delta = (1 if novo == "positivo" else -1) * (2 if anterior else 1)
                    if anterior:
                        cursor.execute("UPDATE votos_registos SET tipo_voto=%s WHERE id=%s", (novo, anterior["id"]))
                        voto_id = anterior["id"]
                    else:
                        cursor.execute("INSERT INTO votos_registos (registo_id,usuario_id,tipo_voto) VALUES (%s,%s,%s)", (registo_id, usuario_id, novo))
                        voto_id = cursor.lastrowid
                    cursor.execute("UPDATE registos_preco SET confianca_score=COALESCE(confianca_score,1)+%s WHERE id=%s", (delta, registo_id))
                    # Sequência persiste no histórico, inclusive em trocas de volta.
                    cursor.execute("SELECT COUNT(*) AS total FROM historico_karma WHERE usuario_id=%s AND registo_id=%s AND origem LIKE %s", (autor, registo_id, f"voto:{voto_id}:%"))
                    sequencia = cursor.fetchone()["total"] + 1
                    registrar_karma(cursor, autor, delta * 2, f"voto:{voto_id}:{sequencia}", "Avaliação de preço pela comunidade", registo_id)
                item = resumo(cursor, registo_id, usuario_id)
                conn.commit()
            else:
                item = resumo(cursor, registo_id, usuario_id)
            return jsonify(item), 200
    except Exception:
        if conn is not None:
            conn.rollback()
        current_app.logger.exception("Falha na avaliação do preço")
        return jsonify(error="Não foi possível consultar ou salvar o voto. Consulte as avaliações antes de repetir."), 503
    finally:
        if conn is not None:
            conn.close()
