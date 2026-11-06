import math
import os
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import pymysql
from flask import Blueprint, current_app, jsonify, request

from app.db import get_db_connection
from app.utils.decorator import token_required
from app.utils.geofence import GeofenceError, validar_proximidade

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
                """,
                (posto_id,),
            )

            posto = cursor.fetchone()

            if not posto:
                return jsonify({
                    "error": "Posto não encontrado."
                }), 404

            eletrico = posto.get("tipo_posto") == "Eletroposto"

            if eletrico != (tipo == COMBUSTIVEL_ELETRICO):
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

            cursor.execute(
                """
                UPDATE usuarios
                SET karma = COALESCE(karma, 0) + 5
                WHERE id = %s
                """,
                (usuario_id_token,),
            )

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
def registrar_preco(usuario_id_token):
    return registrar_preco_validado(
        usuario_id_token,
        request.get_json(silent=True),
    )

@precos_bp.route(
    "/<int:registo_id>/votar",
    methods=["POST"],
    strict_slashes=False,
)
@token_required
def votar_preco(usuario_id_token, registo_id):
    # Mantém a lógica de votação existente.
    data = request.get_json()

    if not data or data.get("voto") not in ["positivo", "negativo"]:
        return jsonify({
            "error": "Envie 'voto' com o valor 'positivo' ou 'negativo'."
        }), 400

    novo_voto = data["voto"]
    conn = None

    try:
        conn = get_db_connection()

        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT usuario_id
                FROM registos_preco
                WHERE id = %s
                """,
                (registo_id,),
            )

            registo = cursor.fetchone()

            if not registo:
                return jsonify({
                    "error": "Registro de preço não encontrado."
                }), 404

            autor_id = registo["usuario_id"]

            if autor_id == usuario_id_token:
                return jsonify({
                    "error": (
                        "Não pode votar na sua própria "
                        "publicação de preço."
                    )
                }), 400

            cursor.execute(
                """
                SELECT tipo_voto
                FROM votos_registos
                WHERE usuario_id = %s
                  AND registo_id = %s
                """,
                (usuario_id_token, registo_id),
            )

            voto_existente = cursor.fetchone()

            if not voto_existente:
                delta_score = 1 if novo_voto == "positivo" else -1
                delta_karma = 2 if novo_voto == "positivo" else -2

                cursor.execute(
                    """
                    INSERT INTO votos_registos (
                        registo_id,
                        usuario_id,
                        tipo_voto
                    )
                    VALUES (%s, %s, %s)
                    """,
                    (
                        registo_id,
                        usuario_id_token,
                        novo_voto,
                    ),
                )

            elif voto_existente["tipo_voto"] == novo_voto:
                return jsonify({
                    "message": "Já registrou este mesmo voto para este preço."
                }), 200

            else:
                delta_score = 2 if novo_voto == "positivo" else -2
                delta_karma = 4 if novo_voto == "positivo" else -4

                cursor.execute(
                    """
                    UPDATE votos_registos
                    SET tipo_voto = %s
                    WHERE usuario_id = %s
                      AND registo_id = %s
                    """,
                    (
                        novo_voto,
                        usuario_id_token,
                        registo_id,
                    ),
                )

            cursor.execute(
                """
                UPDATE registos_preco
                SET confianca_score = confianca_score + %s
                WHERE id = %s
                """,
                (delta_score, registo_id),
            )

            cursor.execute(
                """
                UPDATE usuarios
                SET karma = karma + %s
                WHERE id = %s
                """,
                (delta_karma, autor_id),
            )

            conn.commit()

        return jsonify({
            "message": (
                f"Voto '{novo_voto}' registrado com sucesso!"
            )
        }), 200

    except pymysql.MySQLError as erro:
        if conn:
            conn.rollback()

        return jsonify({
            "error": "Erro ao processar o voto",
            "detalhes": str(erro),
        }), 500

    finally:
        if conn:
            conn.close()