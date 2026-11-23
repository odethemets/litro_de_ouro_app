import math
import os
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from flask import Blueprint, current_app, jsonify, request

from app.db import get_db_connection
from app.utils.decorator import token_required
from app.utils.geofence import GeofenceError, validar_proximidade
from services.atividade_alertas import registrar_karma
from services.catalogo_postos import NOMES
from services.servicos_postos import produto_compativel

precos_bp = Blueprint("precos", __name__)

COMBUSTIVEL_ELETRICO = "Recarga Elétrica (kWh)"

COMBUSTIVEIS_CONVENCIONAIS = (
    "Gasolina Comum",
    "Gasolina Aditivada",
    "Etanol",
    "Diesel",
    "GNV",
)

COMBUSTIVEIS_VALIDOS = (
    COMBUSTIVEIS_CONVENCIONAIS + (COMBUSTIVEL_ELETRICO,)
)

# Mesmo usuário, posto e combustível.
# O valor 0 desativa o intervalo para ambientes de teste.
try:
    COOLDOWN_MINUTOS = max(
        0,
        int(os.getenv("PRECO_COOLDOWN_MIN", "15")),
    )
except ValueError:
    COOLDOWN_MINUTOS = 15

FOTO_URL_MAX = 500

FOTO_HOSTS = (
    "dropbox.com",
    "www.dropbox.com",
    "dl.dropboxusercontent.com",
)


def _validar_foto_url(bruto):
    """Retorna (url, erro). Sem foto, retorna (None, None)."""
    if bruto is None:
        return None, None

    if not isinstance(bruto, str):
        return None, "O campo 'foto_url' deve ser texto."

    url = bruto.strip()

    if not url:
        return None, None

    if len(url) > FOTO_URL_MAX:
        return (
            None,
            f"O campo 'foto_url' excede {FOTO_URL_MAX} caracteres.",
        )

    if any(
        caractere.isspace()
        or ord(caractere) < 32
        or ord(caractere) == 127
        for caractere in url
    ):
        return None, "O campo 'foto_url' contém caracteres inválidos."

    try:
        partes = urlparse(url)
        host = partes.hostname
        partes.port
    except ValueError:
        return None, "O campo 'foto_url' não é uma URL válida."

    if (
        partes.scheme != "https"
        or host not in FOTO_HOSTS
        or partes.username
        or partes.password
    ):
        return (
            None,
            "A foto deve ser um link https do Dropbox "
            "gerado pela leitura do totem.",
        )

    return url, None


def _id_posto_valido(valor):
    """Aceita somente inteiros positivos compatíveis com INT do MySQL."""
    if isinstance(valor, bool) or not isinstance(valor, (int, str)):
        return None

    texto = str(valor).strip()

    if (
        not texto.isascii()
        or not texto.isdecimal()
        or len(texto) > 10
    ):
        return None

    numero = int(texto)

    return numero if 1 <= numero <= 2147483647 else None


# Valida o cadastro e confirma preço, Karma, histórico e evento em uma transação.
def registrar_preco_validado(
    usuario_id_token,
    data,
    posto_id_rota=None,
):
    """Lógica compartilhada pelas duas rotas autenticadas."""
    if not isinstance(data, dict):
        return jsonify({
            "error": "Envie um objeto JSON válido."
        }), 400

    origem_id = (
        posto_id_rota
        if posto_id_rota is not None
        else data.get("posto_id")
    )

    posto_id = _id_posto_valido(origem_id)

    if posto_id is None:
        return jsonify({
            "error": "Informe um posto_id inteiro positivo válido."
        }), 400

    # Impede divergência entre o posto da URL e o informado no corpo.
    if posto_id_rota is not None and "posto_id" in data:
        if _id_posto_valido(data["posto_id"]) != posto_id:
            return jsonify({
                "error": "O posto_id do corpo difere do posto da URL."
            }), 400

    tipo = data.get("tipo_combustivel")

    if (
        not isinstance(tipo, str)
        or tipo.strip() not in COMBUSTIVEIS_VALIDOS
    ):
        return jsonify({
            "error": "Combustível inválido.",
            "validos": list(COMBUSTIVEIS_VALIDOS),
        }), 400

    tipo = tipo.strip()

    bruto = data.get("preco")

    if (
        isinstance(bruto, bool)
        or not isinstance(bruto, (int, float, str))
    ):
        return jsonify({
            "error": "Informe um preço numérico válido."
        }), 400

    try:
        preco = Decimal(str(bruto))
    except InvalidOperation:
        return jsonify({
            "error": "Informe um preço numérico válido."
        }), 400

    if (
        not preco.is_finite()
        or not Decimal("0.01") <= preco <= Decimal("25.00")
    ):
        return jsonify({
            "error": "Informe um preço entre R$ 0,01 e R$ 25,00."
        }), 400

    if preco != preco.quantize(Decimal("0.01")):
        return jsonify({
            "error": "O preço deve ter no máximo duas casas decimais."
        }), 400

    foto_url, erro_foto = _validar_foto_url(data.get("foto_url"))

    if erro_foto:
        return jsonify({
            "error": erro_foto,
            "codigo": "FOTO_INVALIDA",
        }), 400

    if (
        "simulada" in data
        and not isinstance(data["simulada"], bool)
    ):
        return jsonify({
            "error": "O campo simulada deve ser booleano."
        }), 400

    if data.get("simulada") is True:
        return jsonify({
            "error": (
                "Localização simulada não é aceita "
                "para registrar preços."
            ),
            "codigo": "GPS_SIMULADO",
        }), 403

    precisao = data.get("precisao_m")

    if precisao is not None:
        try:
            if isinstance(precisao, bool):
                raise ValueError

            precisao = float(precisao)

            if not math.isfinite(precisao) or precisao < 0:
                raise ValueError

        except (TypeError, ValueError, OverflowError):
            return jsonify({
                "error": "Precisão de localização inválida."
            }), 400

    conn = None

    try:
        conn = get_db_connection()

        with conn.cursor() as cursor:
            # Serializa os cadastros do mesmo usuário.
            # Isso impede que duas requisições simultâneas contornem
            # a verificação do intervalo entre registros.
            cursor.execute(
                """
                SELECT id
                FROM usuarios
                WHERE id = %s
                FOR UPDATE
                """,
                (usuario_id_token,),
            )

            if not cursor.fetchone():
                return jsonify({
                    "error": (
                        "Usuário não encontrado. "
                        "Faça login novamente."
                    )
                }), 401

            cursor.execute(
                """
                SELECT latitude, longitude, nome, tipo_posto
                FROM postos
                WHERE id = %s
                FOR UPDATE
                """,
                (posto_id,),
            )

            posto = cursor.fetchone()

            if not posto:
                return jsonify({
                    "error": "Posto não encontrado."
                }), 404

            cursor.execute("""SELECT COALESCE(disponivel_manual,disponivel_osm) AS disponivel
                FROM postos_combustiveis WHERE posto_id=%s AND combustivel_codigo=%s FOR UPDATE""",
                (posto_id, NOMES[tipo]))
            oferta = cursor.fetchone()
            disponivel = oferta["disponivel"] if oferta else None
            if disponivel == 0:
                return jsonify(error="Este produto está marcado como indisponível.", codigo="PRODUTO_INDISPONIVEL"), 409

            if not produto_compativel(posto.get("tipo_posto"), NOMES[tipo], disponivel):
                return jsonify({
                    "error": (
                        "Este combustível não corresponde "
                        "ao tipo do posto."
                    )
                }), 400

            # A localização deve ser a do aparelho do usuário.
            try:
                resultado = validar_proximidade(
                    data.get("latitude"),
                    data.get("longitude"),
                    precisao,
                    posto["latitude"],
                    posto["longitude"],
                )

            except GeofenceError as erro:
                corpo, status = erro.para_resposta()
                return jsonify(corpo), status

            if COOLDOWN_MINUTOS:
                cursor.execute(
                    """
                    SELECT 1
                    FROM registos_preco
                    WHERE usuario_id = %s
                      AND posto_id = %s
                      AND tipo_combustivel = %s
                      AND data_registro >
                          NOW() - INTERVAL %s MINUTE
                    LIMIT 1
                    """,
                    (
                        usuario_id_token,
                        posto_id,
                        tipo,
                        COOLDOWN_MINUTOS,
                    ),
                )

                if cursor.fetchone():
                    return jsonify({
                        "error": (
                            "Você já registrou este combustível "
                            "neste posto há menos de "
                            f"{COOLDOWN_MINUTOS} minutos."
                        ),
                        "codigo": "REGISTRO_RECENTE",
                    }), 429

            cursor.execute(
                """
                SELECT preco FROM registos_preco
                WHERE posto_id=%s AND tipo_combustivel=%s
                ORDER BY data_registro DESC,id DESC LIMIT 1
                """, (posto_id, tipo),
            )
            anterior = cursor.fetchone()

            cursor.execute(
                """
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
                """,
                (
                    posto_id,
                    usuario_id_token,
                    tipo,
                    preco,
                    foto_url,
                ),
            )

            registo_id = cursor.lastrowid

            registrar_karma(
                cursor, usuario_id_token, 5, f"preco:{registo_id}",
                "Cadastro de preço", registo_id,
            )
            cursor.execute("""
                INSERT INTO eventos_preco (registo_id,preco_anterior,criado_em)
                VALUES (%s,%s,UTC_TIMESTAMP())
            """, (registo_id, anterior["preco"] if anterior else None))

            # Confirma o preço e os pontos na mesma transação.
            conn.commit()

        return jsonify({
            "message": (
                "Preço registrado com sucesso! "
                "Ganhou +5 pontos de Karma!"
            ),
            "registo_id": registo_id,
            "posto_id": posto_id,
            "karma_ganho": 5,
            "distancia_verificada_metros": round(
                resultado.distancia_m,
                2,
            ),
        }), 201

    except Exception:
        if conn is not None:
            conn.rollback()

        current_app.logger.exception("Erro ao registrar preço")

        return jsonify({
            "error": "Erro interno ao registrar o preço."
        }), 500

    finally:
        if conn is not None:
            conn.close()


@precos_bp.route("", methods=["POST"], strict_slashes=False)
@token_required
# Encaminha o JSON e a conta autenticada à regra compartilhada com o alias por posto.
def registrar_preco(usuario_id_token):
    return registrar_preco_validado(
        usuario_id_token,
        request.get_json(silent=True),
    )


@precos_bp.route("/lote", methods=["POST"], strict_slashes=False)
@token_required
def registrar_precos_lote(usuario_id_token):
    from services.precos_lote import registrar_lote_validado

    if request.content_length and request.content_length > 16384:
        return jsonify(error="Lote muito grande."), 413
    return registrar_lote_validado(
        usuario_id_token,
        request.get_json(silent=True),
    )