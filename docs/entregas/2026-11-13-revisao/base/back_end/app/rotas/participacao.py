"""Favoritos, alertas e históricos por usuário autenticado."""

from flask import Blueprint, current_app, jsonify, request

from app.db import get_db_connection
from app.utils.decorator import token_required
from services.catalogo_postos import CATALOGO


participacao_bp = Blueprint("participacao", __name__)


def _executar(usuario_id, acao):
    conn = None

    try:
        conn = get_db_connection()

        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM usuarios WHERE id=%s FOR UPDATE",
                (usuario_id,),
            )

            if not cursor.fetchone():
                return jsonify(
                    error="Conta removida.",
                    code="ACCOUNT_DELETED",
                ), 401

            return acao(conn, cursor)

    except Exception:
        if conn is not None:
            conn.rollback()

        current_app.logger.exception("Falha na participação do usuário")

        return jsonify(
            error=(
                "Não foi possível confirmar a operação. "
                "Atualize os dados antes de repetir."
            )
        ), 500

    finally:
        if conn is not None:
            conn.close()


def _favoritos(cursor, usuario_id):
    cursor.execute(
        """
        SELECT posto_id
        FROM favoritos_postos
        WHERE usuario_id=%s
        ORDER BY posto_id
        """,
        (usuario_id,),
    )
    postos = [r["posto_id"] for r in cursor.fetchall()]

    cursor.execute(
        """
        SELECT combustivel_codigo
        FROM favoritos_combustiveis
        WHERE usuario_id=%s
        ORDER BY combustivel_codigo
        """,
        (usuario_id,),
    )
    combustiveis = [
        r["combustivel_codigo"]
        for r in cursor.fetchall()
    ]

    cursor.execute(
        """
        SELECT ativo,somente_quedas,intervalo_minutos
        FROM preferencias_alertas
        WHERE usuario_id=%s
        """,
        (usuario_id,),
    )

    prefs = cursor.fetchone() or {
        "ativo": 0,
        "somente_quedas": 1,
        "intervalo_minutos": 30,
    }

    return {
        "postos": postos,
        "combustiveis": combustiveis,
        "alertas": {
            "ativo": bool(prefs["ativo"]),
            "somente_quedas": bool(prefs["somente_quedas"]),
            "intervalo_minutos": prefs["intervalo_minutos"],
        },
    }


@participacao_bp.route(
    "/favoritos",
    methods=["GET"],
    strict_slashes=False,
)
@token_required
def favoritos(usuario_id):
    return _executar(
        usuario_id,
        lambda conn, cursor: (
            jsonify(_favoritos(cursor, usuario_id)),
            200,
        ),
    )


@participacao_bp.route(
    "/favoritos/postos/<int:posto_id>",
    methods=["PUT", "DELETE"],
    strict_slashes=False,
)
@token_required
def favoritar_posto(usuario_id, posto_id):
    if not 1 <= posto_id <= 2147483647:
        return jsonify(error="Posto inválido."), 400

    def salvar(conn, cursor):
        if request.method == "PUT":
            cursor.execute(
                "SELECT id FROM postos WHERE id=%s",
                (posto_id,),
            )

            if not cursor.fetchone():
                return jsonify(error="Posto não encontrado."), 404

            cursor.execute(
                """
                INSERT INTO favoritos_postos (
                    usuario_id, posto_id, criado_em
                )
                VALUES (%s,%s,UTC_TIMESTAMP())
                ON DUPLICATE KEY UPDATE posto_id=posto_id
                """,
                (usuario_id, posto_id),
            )
        else:
            cursor.execute(
                """
                DELETE FROM favoritos_postos
                WHERE usuario_id=%s AND posto_id=%s
                """,
                (usuario_id, posto_id),
            )

        dados = _favoritos(cursor, usuario_id)
        conn.commit()

        return jsonify(dados), 200

    return _executar(usuario_id, salvar)


@participacao_bp.route(
    "/favoritos/preferencias",
    methods=["PUT"],
    strict_slashes=False,
)
@token_required
def preferencias(usuario_id):
    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        return jsonify(error="Envie um objeto JSON válido."), 400

    combustiveis = dados.get("combustiveis")

    if (
        not isinstance(combustiveis, list)
        or len(combustiveis) > 6
        or any(
            not isinstance(c, str) or c not in CATALOGO
            for c in combustiveis
        )
    ):
        return jsonify(
            error="Selecione combustíveis válidos."
        ), 400

    if (
        type(dados.get("ativo")) is not bool
        or type(dados.get("somente_quedas")) is not bool
        or type(dados.get("intervalo_minutos")) is not int
        or dados["intervalo_minutos"] not in (0, 15, 30, 60, 120, 1440)
    ):
        return jsonify(
            error="Preferências de alerta inválidas."
        ), 400

    def salvar(conn, cursor):
        cursor.execute(
            """
            SELECT combustivel_codigo
            FROM favoritos_combustiveis
            WHERE usuario_id=%s
            """,
            (usuario_id,),
        )
        atuais = {
            r["combustivel_codigo"]
            for r in cursor.fetchall()
        }
        novos = set(combustiveis)

        for codigo in atuais - novos:
            cursor.execute(
                """
                DELETE FROM favoritos_combustiveis
                WHERE usuario_id=%s AND combustivel_codigo=%s
                """,
                (usuario_id, codigo),
            )

        for codigo in novos - atuais:
            cursor.execute(
                """
                INSERT INTO favoritos_combustiveis (
                    usuario_id, combustivel_codigo, criado_em
                )
                VALUES (%s,%s,UTC_TIMESTAMP())
                """,
                (usuario_id, codigo),
            )

        cursor.execute(
            """
            INSERT INTO preferencias_alertas (
                usuario_id, ativo, somente_quedas, intervalo_minutos
            )
            VALUES (%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
                ativo=VALUES(ativo),
                somente_quedas=VALUES(somente_quedas),
                intervalo_minutos=VALUES(intervalo_minutos)
            """,
            (
                usuario_id,
                dados["ativo"],
                dados["somente_quedas"],
                dados["intervalo_minutos"],
            ),
        )

        resultado = _favoritos(cursor, usuario_id)
        conn.commit()

        return jsonify(resultado), 200

    return _executar(usuario_id, salvar)


@participacao_bp.route(
    "/notificacoes",
    methods=["GET"],
    strict_slashes=False,
)
@token_required
def notificacoes(usuario_id):
    def consultar(conn, cursor):
        cursor.execute(
            """
            SELECT n.id,n.posto_id,p.nome AS posto_nome,
                   n.combustivel_codigo,n.preco_anterior,
                   n.preco_novo,n.criado_em,n.lida_em
            FROM notificacoes n
            JOIN postos p ON p.id=n.posto_id
            WHERE n.usuario_id=%s
            ORDER BY n.id DESC
            LIMIT 100
            """,
            (usuario_id,),
        )
        itens = cursor.fetchall()

        for item in itens:
            for campo in ("preco_anterior", "preco_novo"):
                item[campo] = (
                    float(item[campo])
                    if item[campo] is not None
                    else None
                )

            item["criado_em"] = item["criado_em"].isoformat() + "Z"
            item["lida"] = item.pop("lida_em") is not None

        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM notificacoes
            WHERE usuario_id=%s AND lida_em IS NULL
            """,
            (usuario_id,),
        )

        return jsonify(
            itens=itens,
            nao_lidas=cursor.fetchone()["total"],
        ), 200

    return _executar(usuario_id, consultar)


@participacao_bp.route(
    "/notificacoes/<int:notificacao_id>/lida",
    methods=["PUT"],
    strict_slashes=False,
)
@token_required
def marcar_lida(usuario_id, notificacao_id):
    def salvar(conn, cursor):
        cursor.execute(
            """
            SELECT id FROM notificacoes
            WHERE id=%s AND usuario_id=%s
            """,
            (notificacao_id, usuario_id),
        )

        if not cursor.fetchone():
            return jsonify(
                error="Notificação não encontrada."
            ), 404

        cursor.execute(
            """
            UPDATE notificacoes
            SET lida_em=COALESCE(lida_em,UTC_TIMESTAMP())
            WHERE id=%s AND usuario_id=%s
            """,
            (notificacao_id, usuario_id),
        )
        conn.commit()

        return jsonify(lida=True), 200

    return _executar(usuario_id, salvar)


@participacao_bp.route(
    "/atividade/karma",
    methods=["GET"],
    strict_slashes=False,
)
@token_required
def karma(usuario_id):
    def consultar(conn, cursor):
        cursor.execute(
            """
            SELECT COALESCE(karma,0) AS karma
            FROM usuarios WHERE id=%s
            """,
            (usuario_id,),
        )
        saldo = cursor.fetchone()["karma"]

        cursor.execute(
            """
            SELECT id,motivo,pontos,saldo_apos,registo_id,criado_em
            FROM historico_karma
            WHERE usuario_id=%s
            ORDER BY id DESC
            LIMIT 100
            """,
            (usuario_id,),
        )
        itens = cursor.fetchall()

        for item in itens:
            item["criado_em"] = item["criado_em"].isoformat() + "Z"

        return jsonify(saldo=saldo, itens=itens), 200

    return _executar(usuario_id, consultar)


@participacao_bp.route(
    "/ranking",
    methods=["GET"],
    strict_slashes=False,
)
def ranking():
    conn = None

    try:
        conn = get_db_connection(read_only=True)

        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT nome,COALESCE(karma,0) AS karma
                FROM usuarios
                WHERE email_verificado=1
                ORDER BY karma DESC,id
                LIMIT 50
                """
            )
            return jsonify(cursor.fetchall()), 200

    except Exception:
        current_app.logger.exception("Falha no ranking")

        return jsonify(
            error="Ranking temporariamente indisponível."
        ), 503

    finally:
        if conn is not None:
            conn.close()