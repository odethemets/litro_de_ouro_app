"""Cadastro de varios precos do mesmo posto em uma unica transacao."""
import math
from decimal import Decimal, InvalidOperation

from flask import current_app, jsonify

from app.utils.geofence import GeofenceError, validar_proximidade
from services.catalogo_postos import NOMES
from services.servicos_postos import RecusaServico, produto_compativel
from services.politica_precos import politica_precos


class RecusaLote(Exception):
    def __init__(self, mensagem, status=400, codigo="LOTE_INVALIDO"):
        super().__init__(mensagem)
        self.status = status
        self.codigo = codigo


def validar_lote(dados, regras, administrativo=False):
    if not isinstance(dados, dict):
        raise RecusaLote("Envie um objeto JSON válido.")

    posto_id = regras._id_posto_valido(dados.get("posto_id"))
    if posto_id is None:
        raise RecusaLote("Informe um posto_id inteiro positivo válido.")

    bruto = dados.get("itens")
    if not isinstance(bruto, list) or not 1 <= len(bruto) <= 6:
        raise RecusaLote(
            "Selecione de um a seis combustíveis, sem repetições."
        )

    itens, vistos = [], set()

    for item in bruto:
        if not isinstance(item, dict) or set(item) - {
            "tipo_combustivel",
            "preco",
            "foto_url",
        }:
            raise RecusaLote(
                "Cada item deve conter combustível, preço e foto opcional."
            )

        tipo = item.get("tipo_combustivel")
        if (
            not isinstance(tipo, str)
            or tipo.strip() not in regras.COMBUSTIVEIS_VALIDOS
        ):
            raise RecusaLote("Combustível inválido no lote.")

        tipo = tipo.strip()
        if tipo in vistos:
            raise RecusaLote(
                "Cada combustível pode aparecer uma única vez no lote."
            )
        vistos.add(tipo)

        valor = item.get("preco")
        if isinstance(valor, bool) or not isinstance(
            valor, (int, float, str)
        ):
            raise RecusaLote(
                "Informe um preço numérico válido para " + tipo + "."
            )

        if len(str(valor)) > 40:
            raise RecusaLote("Preço inválido para " + tipo + ".")

        try:
            preco = Decimal(str(valor))

            if (
                not preco.is_finite()
                or not Decimal("0.01") <= preco <= Decimal("25.00")
            ):
                raise InvalidOperation

            if preco != preco.quantize(Decimal("0.01")):
                raise InvalidOperation

        except InvalidOperation:
            raise RecusaLote(
                "Informe um preço entre R$ 0,01 e R$ 25,00, "
                "com até duas casas decimais, para " + tipo + "."
            ) from None

        foto, erro = regras._validar_foto_url(item.get("foto_url"))
        if erro:
            raise RecusaLote(erro, codigo="FOTO_INVALIDA")

        itens.append({
            "tipo": tipo,
            "preco": preco,
            "foto": foto,
        })

    if administrativo:
        return posto_id, itens, None

    if "simulada" in dados and type(dados["simulada"]) is not bool:
        raise RecusaLote("O campo simulada deve ser booleano.")

    if dados.get("simulada") is True:
        raise RecusaLote(
            "Localização simulada não é aceita.",
            403,
            "GPS_SIMULADO",
        )

    precisao = dados.get("precisao_m")
    if precisao is not None:
        try:
            if isinstance(precisao, bool):
                raise ValueError

            precisao = float(precisao)

            if not math.isfinite(precisao) or precisao < 0:
                raise ValueError

        except (ValueError, TypeError, OverflowError):
            raise RecusaLote(
                "Precisão de localização inválida."
            ) from None

    return posto_id, itens, precisao


def _conferir_itens(
    cursor, usuario_id, posto_id, posto, itens, regras
):
    for item in itens:
        tipo = item["tipo"]

        cursor.execute("""
            SELECT
                COALESCE(disponivel_manual, disponivel_osm)
                    AS disponivel
            FROM postos_combustiveis
            WHERE posto_id=%s AND combustivel_codigo=%s
            FOR UPDATE
        """, (posto_id, NOMES[tipo]))

        oferta = cursor.fetchone()
        disponivel = oferta["disponivel"] if oferta else None

        if not produto_compativel(
            posto.get("tipo_posto"),
            NOMES[tipo],
            disponivel,
        ):
            raise RecusaLote(
                "O combustível " + tipo
                + " não corresponde ao tipo do posto "
                "ou aguarda confirmação."
            )

        if oferta and oferta["disponivel"] == 0:
            raise RecusaLote(
                tipo + " está marcado como indisponível. "
                "Revise a seleção.",
                409,
                "PRODUTO_INDISPONIVEL",
            )

        if regras.COOLDOWN_MINUTOS:
            cursor.execute("""
                SELECT 1
                FROM registos_preco
                WHERE usuario_id=%s
                  AND posto_id=%s
                  AND tipo_combustivel=%s
                  AND data_registro >
                      NOW() - INTERVAL %s MINUTE
                LIMIT 1
            """, (
                usuario_id,
                posto_id,
                tipo,
                regras.COOLDOWN_MINUTOS,
            ))

            if cursor.fetchone():
                raise RecusaLote(
                    "Você já registrou " + tipo
                    + " neste posto há menos de "
                    + str(regras.COOLDOWN_MINUTOS)
                    + " minutos. Revise o lote.",
                    429,
                    "REGISTRO_RECENTE",
                )


def _gravar(
    cursor, usuario_id, posto_id, item, regras, karma_ganho=5
):
    cursor.execute("""
        SELECT preco
        FROM registos_preco
        WHERE posto_id=%s AND tipo_combustivel=%s
        ORDER BY data_registro DESC, id DESC
        LIMIT 1
    """, (posto_id, item["tipo"]))

    anterior = cursor.fetchone()

    cursor.execute("""
        INSERT INTO registos_preco (
            posto_id,
            usuario_id,
            tipo_combustivel,
            preco,
            confianca_score,
            foto_url,
            data_registro
        )
        VALUES (%s, %s, %s, %s, 1, %s, NOW())
    """, (
        posto_id,
        usuario_id,
        item["tipo"],
        item["preco"],
        item["foto"],
    ))

    registo_id = cursor.lastrowid

    if karma_ganho:
        regras.registrar_karma(
            cursor,
            usuario_id,
            karma_ganho,
            f"preco:{registo_id}",
            "Cadastro de preço",
            registo_id,
        )

    cursor.execute("""
        INSERT INTO eventos_preco (
            registo_id,
            preco_anterior,
            criado_em
        )
        VALUES (%s, %s, UTC_TIMESTAMP())
    """, (
        registo_id,
        anterior["preco"] if anterior else None,
    ))

    return {
        "registo_id": registo_id,
        "tipo_combustivel": item["tipo"],
        "preco": format(item["preco"], ".2f"),
        "karma_ganho": karma_ganho,
    }


def _reverter(conn):
    if conn is not None:
        try:
            conn.rollback()
        except Exception:
            current_app.logger.warning(
                "Falha ao encerrar a transacao de precos."
            )


def registrar_lote_validado(usuario_id, dados):
    # Importacao tardia evita import circular.
    from app.rotas import precos as regras

    conn = None

    try:
        politica = politica_precos(usuario_id)

        posto_id, itens, precisao = validar_lote(
            dados,
            regras,
            politica["administrativo"],
        )

        conn = regras.get_db_connection()
        conn.begin()

        with conn.cursor() as cursor:
            # Ordem de locks: conta, depois posto.
            cursor.execute("""
                SELECT id
                FROM usuarios
                WHERE id=%s
                FOR UPDATE
            """, (usuario_id,))

            if not cursor.fetchone():
                raise RecusaLote(
                    "Usuário não encontrado. Entre novamente.",
                    401,
                    "SESSAO_INVALIDA",
                )

            cursor.execute("""
                SELECT latitude, longitude, nome, tipo_posto
                FROM postos
                WHERE id=%s
                FOR UPDATE
            """, (posto_id,))

            posto = cursor.fetchone()

            if not posto:
                raise RecusaLote(
                    "Posto não encontrado.",
                    404,
                    "POSTO_AUSENTE",
                )

            proximidade = None

            if politica["exige_gps"]:
                proximidade = validar_proximidade(
                    dados.get("latitude"),
                    dados.get("longitude"),
                    precisao,
                    posto["latitude"],
                    posto["longitude"],
                )

            # Confere todos os produtos antes do primeiro INSERT.
            _conferir_itens(
                cursor,
                usuario_id,
                posto_id,
                posto,
                itens,
                regras,
            )

            registros = [
                _gravar(
                    cursor,
                    usuario_id,
                    posto_id,
                    item,
                    regras,
                    politica["karma_por_preco"],
                )
                for item in itens
            ]

        conn.commit()

        return jsonify(
            posto_id=posto_id,
            registros=registros,
            total=len(registros),
            karma_ganho=sum(
                r["karma_ganho"] for r in registros
            ),
            administrativo=politica["administrativo"],
            distancia_verificada_metros=(
                round(proximidade.distancia_m, 2)
                if proximidade is not None
                else None
            ),
        ), 201

    except (RecusaLote, GeofenceError, RecusaServico) as erro:
        _reverter(conn)

        if isinstance(erro, GeofenceError):
            corpo, status = erro.para_resposta()
            return jsonify(corpo), status

        return jsonify(
            error=str(erro),
            codigo=erro.codigo,
        ), erro.status

    except Exception:
        _reverter(conn)

        current_app.logger.warning(
            "Nao foi possivel confirmar o cadastro do lote."
        )

        return jsonify(error=(
            "Não foi possível confirmar o lote. "
            "Confira sua atividade antes de tentar novamente."
        )), 500

    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                current_app.logger.warning(
                    "Falha ao encerrar conexao do cadastro de precos."
                )