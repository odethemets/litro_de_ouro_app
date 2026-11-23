"""Solicitações com evidência privada e decisão administrativa transacional."""
import base64
from datetime import datetime, timedelta, timezone
import hashlib

from flask import Blueprint, current_app, jsonify, request

from app.db import get_db_connection
from app.utils.decorator import token_required
from app.utils.geofence import GeofenceError, validar_proximidade
from services import fotos_servicos
from services.leitura_totem import FotoTotemInvalida, MAX_BYTES, preparar_imagem
from services.servicos_postos import (
    RecusaServico, administradores, exigir_admin, oferta_efetiva,
    validar_decisao, validar_envio,
)

servicos_bp = Blueprint("servicos", __name__)
LIMITE_DIARIO = 10
LIMITE_PAGINA = 20


@servicos_bp.after_request
def privacidade(resposta):
    resposta.headers["Cache-Control"] = "no-store"
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    return resposta


def _erro(erro):
    if isinstance(erro, GeofenceError):
        corpo, status = erro.para_resposta()
        return jsonify(corpo), status
    return jsonify(error=str(erro), codigo=erro.codigo), erro.status


def _fechar(conn):
    if conn is not None:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


def _iniciar(conn):
    with conn.cursor() as cursor:
        cursor.execute("SELECT VERSION() AS versao")
        servidor = cursor.fetchone()
        if servidor is None:
            raise RuntimeError("Não foi possível identificar o servidor do banco.")
        versao = str(servidor["versao"])

    conn.rollback()

    with conn.cursor() as cursor:
        if "tidb" in versao.lower():
            cursor.execute("SET SESSION tidb_txn_mode = 'pessimistic'")
        cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")

    conn.begin()


def _publico(item, revisor=None):
    campos = (
        "id", "posto_id", "posto_nome", "posto_endereco", "codigo",
        "observacao", "estado", "motivo", "distancia_m", "precisao_m",
    )
    resultado = {c: item.get(c) for c in campos}

    for campo in ("distancia_m", "precisao_m"):
        resultado[campo] = float(resultado[campo])

    for campo in ("criado_em", "revisado_em"):
        data = item.get(campo)
        resultado[campo] = data.isoformat() + "Z" if data is not None else None

    resultado["pode_revisar"] = (
        revisor is not None
        and item["estado"] == "pendente"
        and item["usuario_id"] != revisor
    )

    return resultado


_SELECT = """
    SELECT s.*,s.combustivel_codigo AS codigo,p.nome AS posto_nome,
           p.endereco AS posto_endereco
    FROM solicitacoes_servicos s JOIN postos p ON p.id=s.posto_id
"""


def _buscar(cursor, solicitacao_id):
    cursor.execute(_SELECT + " WHERE s.id=%s", (solicitacao_id,))
    return cursor.fetchone()


@servicos_bp.post("/postos/<int:posto_id>/servicos/solicitacoes")
@token_required
def solicitar(usuario_id, posto_id):
    if request.content_length and request.content_length > MAX_BYTES + 512 * 1024:
        return jsonify(error="Envie uma foto de até 8 MB."), 413

    conn, nome, commit_iniciado = None, None, False

    try:
        if not 1 <= posto_id <= 2147483647:
            raise RecusaServico("Posto inválido.")

        codigo, chave, observacao, precisao = validar_envio(request.form)

        foto = request.files.get("foto")
        if foto is None:
            raise RecusaServico("Escolha a foto que comprova o serviço.")

        bruto = foto.read(MAX_BYTES + 1)
        if len(bruto) > MAX_BYTES:
            return jsonify(error="Envie uma foto de até 8 MB."), 413

        jpeg = preparar_imagem(bruto)
        if len(jpeg) > fotos_servicos.MAX_JPEG:
            raise RecusaServico(
                "Escolha uma foto menor ou com enquadramento mais próximo."
            )

        sha = hashlib.sha256(jpeg).hexdigest()

        conn = get_db_connection()
        _iniciar(conn)

        with conn.cursor() as cursor:
            # Mesma ordem de locks do cadastro: usuário e depois posto.
            cursor.execute(
                "SELECT id FROM usuarios WHERE id=%s FOR UPDATE",
                (usuario_id,),
            )
            if not cursor.fetchone():
                raise RecusaServico("Entre novamente na sua conta.", 401)

            cursor.execute(
                "SELECT latitude,longitude,tipo_posto FROM postos "
                "WHERE id=%s FOR UPDATE",
                (posto_id,),
            )
            posto = cursor.fetchone()
            if not posto:
                raise RecusaServico("Posto não encontrado.", 404)

            cursor.execute(
                _SELECT + " WHERE s.usuario_id=%s AND s.chave_cliente=%s",
                (usuario_id, chave),
            )
            anterior = cursor.fetchone()

            if anterior:
                if (
                    anterior["posto_id"],
                    anterior["codigo"],
                    anterior["foto_sha256"],
                    anterior["observacao"],
                ) != (posto_id, codigo, sha, observacao):
                    raise RecusaServico(
                        "O identificador já pertence a outro envio.",
                        409,
                        "CHAVE_REUTILIZADA",
                    )
                return jsonify(_publico(anterior)), 200

            if posto["tipo_posto"] == "Eletroposto" and codigo != "recarga_eletrica":
                raise RecusaServico(
                    "Selecione recarga elétrica para este eletroposto."
                )

            proximidade = validar_proximidade(
                request.form.get("latitude"),
                request.form.get("longitude"),
                precisao,
                posto["latitude"],
                posto["longitude"],
            )

            cursor.execute(
                """
                SELECT disponivel_manual,disponivel_osm
                FROM postos_combustiveis
                WHERE posto_id=%s AND combustivel_codigo=%s FOR UPDATE
                """,
                (posto_id, codigo),
            )
            if oferta_efetiva(cursor.fetchone() or {}) == 1:
                raise RecusaServico(
                    "Este serviço já está confirmado no catálogo.",
                    409,
                    "OFERTA_CONFIRMADA",
                )

            cursor.execute(
                """
                SELECT id FROM solicitacoes_servicos
                WHERE usuario_id=%s AND posto_id=%s
                  AND combustivel_codigo=%s AND estado='pendente'
                LIMIT 1
                """,
                (usuario_id, posto_id, codigo),
            )
            if cursor.fetchone():
                raise RecusaServico(
                    "Você já tem uma solicitação pendente para este serviço.",
                    409,
                    "SOLICITACAO_PENDENTE",
                )

            cursor.execute(
                """
                SELECT COUNT(*) AS total FROM solicitacoes_servicos
                WHERE usuario_id=%s
                  AND criado_em > UTC_TIMESTAMP() - INTERVAL 1 DAY
                """,
                (usuario_id,),
            )
            contagem = cursor.fetchone()
            if contagem is None:
                raise RuntimeError(
                    "Não foi possível verificar o limite de solicitações."
                )

            if contagem["total"] >= LIMITE_DIARIO:
                raise RecusaServico(
                    "Limite diário de solicitações atingido.",
                    429,
                    "LIMITE_SOLICITACOES",
                )

            # O storage não cria link compartilhado.
            # A foto só sai por rota autenticada.
            nome = fotos_servicos.guardar(jpeg)

            cursor.execute(
                """
                INSERT INTO solicitacoes_servicos
                    (usuario_id,posto_id,combustivel_codigo,chave_cliente,
                     foto_arquivo,foto_sha256,observacao,distancia_m,
                     precisao_m,estado,criado_em)
                VALUES
                    (%s,%s,%s,%s,%s,%s,%s,%s,%s,'pendente',UTC_TIMESTAMP())
                """,
                (
                    usuario_id,
                    posto_id,
                    codigo,
                    chave,
                    nome,
                    sha,
                    observacao,
                    round(proximidade.distancia_m, 2),
                    round(precisao, 2),
                ),
            )

            item = _buscar(cursor, cursor.lastrowid)
            if item is None:
                raise RuntimeError(
                    "Não foi possível consultar a solicitação criada."
                )

        commit_iniciado = True
        conn.commit()

        return jsonify(_publico(item)), 201

    except (RecusaServico, GeofenceError) as erro:
        return _erro(erro)

    except FotoTotemInvalida as erro:
        return jsonify(error=str(erro)), 400

    except fotos_servicos.FotoServicoIndisponivel:
        return jsonify(
            error="A foto não foi guardada. Tente novamente mais tarde.",
            codigo="FOTO_NAO_GUARDADA",
        ), 503

    except Exception:
        current_app.logger.warning(
            "Não foi possível confirmar a solicitação de serviço."
        )
        return jsonify(
            error="A confirmação não chegou. Confira suas solicitações antes de reenviar.",
            codigo="RESULTADO_INCERTO",
        ), 503

    finally:
        _fechar(conn)

        # Commit perdido pode ter persistido:
        # nesse caso a evidência é preservada.
        if nome is not None and not commit_iniciado:
            if not fotos_servicos.remover(nome):
                current_app.logger.warning(
                    "Limpeza de comprovante órfão pendente de revisão operacional."
                )


def _pagina(usuario_id, admin=False):
    conn = None

    try:
        if admin:
            exigir_admin(usuario_id)

        estado = request.args.get("estado", "pendente" if admin else "todos")
        if estado not in ("pendente", "aprovada", "rejeitada", "todos"):
            raise RecusaServico("Estado de solicitação inválido.")

        antes = request.args.get("antes_de")
        if antes is not None and (
            not antes.isascii()
            or not antes.isdecimal()
            or len(antes) > 10
            or not 1 <= int(antes) <= 2147483647
        ):
            raise RecusaServico("Página inválida.")

        filtros, valores = [], []

        if not admin:
            filtros.append("s.usuario_id=%s")
            valores.append(usuario_id)

        if estado != "todos":
            filtros.append("s.estado=%s")
            valores.append(estado)

        if antes is not None:
            filtros.append("s.id<%s")
            valores.append(int(antes))

        where = " WHERE " + " AND ".join(filtros) if filtros else ""

        conn = get_db_connection()

        with conn.cursor() as cursor:
            cursor.execute(
                _SELECT + where + " ORDER BY s.id DESC LIMIT %s",
                (*valores, LIMITE_PAGINA),
            )
            itens = cursor.fetchall()

        return jsonify(
            itens=[
                _publico(i, usuario_id if admin else None)
                for i in itens
            ],
            antes_de=itens[-1]["id"] if len(itens) == LIMITE_PAGINA else None,
        ), 200

    except RecusaServico as erro:
        return _erro(erro)

    except Exception:
        current_app.logger.warning("Consulta de solicitações indisponível.")
        return jsonify(error="Não foi possível consultar as solicitações."), 503

    finally:
        _fechar(conn)


@servicos_bp.get("/servicos/solicitacoes/minhas")
@token_required
def minhas(usuario_id):
    return _pagina(usuario_id)


@servicos_bp.get("/admin/servicos/acesso")
@token_required
def acesso(usuario_id):
    try:
        return jsonify(pode_moderar=usuario_id in administradores()), 200
    except RecusaServico as erro:
        return _erro(erro)


@servicos_bp.get("/admin/servicos/solicitacoes")
@token_required
def pendencias(usuario_id):
    return _pagina(usuario_id, admin=True)


@servicos_bp.get("/admin/servicos/solicitacoes/<int:solicitacao_id>/foto")
@token_required
def comprovante(usuario_id, solicitacao_id):
    conn = None

    try:
        exigir_admin(usuario_id)

        conn = get_db_connection()
        with conn.cursor() as cursor:
            item = _buscar(cursor, solicitacao_id)

        if not item:
            raise RecusaServico("Solicitação não encontrada.", 404)

        nome = item["foto_arquivo"]

        _fechar(conn)
        conn = None

        jpeg = fotos_servicos.ler(nome)

        if hashlib.sha256(jpeg).hexdigest() != item["foto_sha256"]:
            raise fotos_servicos.FotoServicoIndisponivel(
                "Comprovante divergente do envio original."
            )

        return jsonify(
            mime="image/jpeg",
            base64=base64.b64encode(jpeg).decode("ascii"),
        ), 200

    except RecusaServico as erro:
        return _erro(erro)

    except Exception:
        current_app.logger.warning("Comprovante de serviço indisponível.")
        return jsonify(
            error="Não foi possível abrir a foto. Tente novamente."
        ), 503

    finally:
        _fechar(conn)


@servicos_bp.post("/admin/servicos/solicitacoes/<int:solicitacao_id>/decidir")
@token_required
def decidir(usuario_id, solicitacao_id):
    conn, commit_iniciado = None, False

    try:
        exigir_admin(usuario_id)

        if request.content_length and request.content_length > 4096:
            return jsonify(error="Decisão muito grande."), 413

        estado, motivo = validar_decisao(request.get_json(silent=True))

        conn = get_db_connection()
        with conn.cursor() as cursor:
            item = _buscar(cursor, solicitacao_id)

        if not item:
            raise RecusaServico("Solicitação não encontrada.", 404)

        posto_id = item["posto_id"]

        # Descarta o snapshot inicial antes de aguardar os locks.
        conn.rollback()
        _iniciar(conn)

        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM usuarios WHERE id=%s FOR UPDATE",
                (usuario_id,),
            )
            if not cursor.fetchone():
                raise RecusaServico("Entre novamente na sua conta.", 401)

            cursor.execute(
                "SELECT id FROM postos WHERE id=%s FOR UPDATE",
                (posto_id,),
            )
            if not cursor.fetchone():
                raise RecusaServico("Posto não encontrado.", 404)

            cursor.execute(
                "SELECT id FROM solicitacoes_servicos WHERE id=%s FOR UPDATE",
                (solicitacao_id,),
            )
            if not cursor.fetchone():
                raise RecusaServico("Solicitação não encontrada.", 404)

            item = _buscar(cursor, solicitacao_id)
            if item is None:
                raise RecusaServico("Solicitação não encontrada.", 404)

            if item["usuario_id"] == usuario_id:
                raise RecusaServico(
                    "Outro administrador deve revisar sua própria solicitação.",
                    409,
                    "REVISAO_PROPRIA",
                )

            if item["estado"] != "pendente":
                if (
                    item["estado"],
                    item["motivo"],
                    item["revisado_por"],
                ) == (estado, motivo, usuario_id):
                    return jsonify(_publico(item, usuario_id)), 200

                raise RecusaServico(
                    "A solicitação já foi decidida. Atualize a lista.",
                    409,
                    "DECISAO_EXISTENTE",
                )

            if estado == "aprovada":
                idade = (
                    datetime.now(timezone.utc).replace(tzinfo=None)
                    - item["criado_em"]
                )
                if idade > timedelta(days=30):
                    raise RecusaServico(
                        "A solicitação tem mais de 30 dias. "
                        "Rejeite e solicite uma evidência atual.",
                        409,
                        "EVIDENCIA_ANTIGA",
                    )

                cursor.execute(
                    """
                    INSERT INTO postos_combustiveis
                        (posto_id,combustivel_codigo,disponivel_manual,
                         manual_atualizado_em,manual_atualizado_por)
                    VALUES (%s,%s,1,UTC_TIMESTAMP(),%s)
                    ON DUPLICATE KEY UPDATE
                        disponivel_manual=1,
                        manual_atualizado_em=UTC_TIMESTAMP(),
                        manual_atualizado_por=VALUES(manual_atualizado_por)
                    """,
                    (posto_id, item["codigo"], usuario_id),
                )

            cursor.execute(
                """
                UPDATE solicitacoes_servicos
                SET estado=%s,motivo=%s,revisado_por=%s,
                    revisado_em=UTC_TIMESTAMP()
                WHERE id=%s AND estado='pendente'
                """,
                (estado, motivo, usuario_id, solicitacao_id),
            )
            if cursor.rowcount != 1:
                raise RecusaServico("A decisão mudou. Atualize a lista.", 409)

            resultado = _buscar(cursor, solicitacao_id)
            if resultado is None:
                raise RuntimeError(
                    "Não foi possível consultar a decisão registrada."
                )

        commit_iniciado = True
        conn.commit()

        return jsonify(_publico(resultado, usuario_id)), 200

    except RecusaServico as erro:
        return _erro(erro)

    except Exception:
        current_app.logger.warning(
            "Não foi possível confirmar a revisão de serviço."
        )
        return jsonify(
            error="Consulte a lista antes de repetir a decisão.",
            codigo=(
                "RESULTADO_INCERTO"
                if commit_iniciado
                else "REVISAO_INDISPONIVEL"
            ),
        ), 503

    finally:
        _fechar(conn)