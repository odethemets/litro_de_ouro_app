import os
from urllib.parse import urlparse

from flask import Blueprint, jsonify, request

from app.db import get_db_connection
from app.utils.decorator import token_required
from services.atividade_alertas import registrar_karma
from services.politica_precos import politica_precos
from services.servicos_postos import RecusaServico

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
    COMBUSTIVEIS_CONVENCIONAIS
    + (COMBUSTIVEL_ELETRICO,)
)

# Mesmo usuário, posto e combustível.
# Zero desativa o intervalo em ambientes de teste.
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
        return (
            None,
            "O campo 'foto_url' contém caracteres inválidos.",
        )

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
    """Aceita inteiros positivos compatíveis com INT do MySQL."""
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
    """O cadastro individual compartilha transação e política do lote."""
    from services.precos_lote import registrar_lote_validado

    if not isinstance(data, dict):
        return jsonify(
            error="Envie um objeto JSON válido."
        ), 400

    origem_id = (
        posto_id_rota
        if posto_id_rota is not None
        else data.get("posto_id")
    )
    posto_id = _id_posto_valido(origem_id)

    if posto_id is None:
        return jsonify(
            error="Informe um posto_id inteiro positivo válido."
        ), 400

    if posto_id_rota is not None and "posto_id" in data:
        if _id_posto_valido(data["posto_id"]) != posto_id:
            return jsonify(
                error="O posto_id do corpo difere do posto da URL."
            ), 400

    pedido = {
        **data,
        "posto_id": posto_id,
        "itens": [{
            k: data[k]
            for k in ("tipo_combustivel", "preco", "foto_url")
            if k in data
        }],
    }

    resposta, status = registrar_lote_validado(
        usuario_id_token,
        pedido,
    )

    if status != 201:
        return resposta, status

    dados = resposta.get_json()
    registro = dados["registros"][0]

    return jsonify(
        message=(
            "Preço registrado com sucesso."
            if dados["administrativo"]
            else "Preço registrado com sucesso! "
                 "Ganhou +5 pontos de Karma!"
        ),
        registo_id=registro["registo_id"],
        posto_id=posto_id,
        karma_ganho=registro["karma_ganho"],
        administrativo=dados["administrativo"],
        distancia_verificada_metros=(
            dados["distancia_verificada_metros"]
        ),
    ), 201


@precos_bp.route(
    "/permissoes",
    methods=["GET"],
    strict_slashes=False,
)
@token_required
def permissoes_precos(usuario_id_token):
    try:
        resposta = jsonify(politica_precos(usuario_id_token))
        resposta.headers["Cache-Control"] = "no-store"
        return resposta, 200

    except RecusaServico as erro:
        return jsonify(
            error=str(erro),
            codigo=erro.codigo,
        ), erro.status


@precos_bp.route(
    "",
    methods=["POST"],
    strict_slashes=False,
)
@token_required
def registrar_preco(usuario_id_token):
    if request.content_length and request.content_length > 16384:
        return jsonify(error="Cadastro muito grande."), 413

    return registrar_preco_validado(
        usuario_id_token,
        request.get_json(silent=True),
    )


@precos_bp.route(
    "/lote",
    methods=["POST"],
    strict_slashes=False,
)
@token_required
def registrar_precos_lote(usuario_id_token):
    from services.precos_lote import registrar_lote_validado

    if request.content_length and request.content_length > 16384:
        return jsonify(error="Lote muito grande."), 413

    return registrar_lote_validado(
        usuario_id_token,
        request.get_json(silent=True),
    )