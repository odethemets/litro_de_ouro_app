import io
import importlib
import json
import logging
import math
import os
import re
import threading
import time
from collections import defaultdict, deque

from flask import Blueprint, jsonify, request
from PIL import Image, ImageOps, UnidentifiedImageError

from services.dropbox_services import upload_foto_totem
from services.politica_precos import politica_precos
from services.servicos_postos import RecusaServico
from services.leitura_totem import (
    FotoTotemInvalida,
    preparar_imagem as preparar_imagem_totem,
    normalizar_precos as normalizar_precos_totem,
)
from ..db import get_db_connection
from ..utils.decorator import token_required
from ..utils.geofence import GeofenceError, validar_proximidade

try:
    genai = importlib.import_module("google.genai")
    types = importlib.import_module("google.genai.types")
except ModuleNotFoundError:
    genai = None
    types = None

ia_bp = Blueprint("ia", __name__)
log = logging.getLogger(__name__)


def _env_num(nome, padrao, tipo=float):
    try:
        valor = tipo(os.getenv(nome, ""))
    except ValueError:
        return padrao

    return valor if valor >= 0 else padrao


MODELO = os.getenv("GEMINI_MODEL") or "gemini-3-flash-preview"

NIVEL_RACIOCINIO = (
    os.getenv("GEMINI_THINKING_LEVEL") or ""
).strip().lower()

TIMEOUT_IA_S = _env_num("GEMINI_TIMEOUT_S", 45.0)
LIMITE_POR_HORA = _env_num("IA_LIMITE_POR_HORA", 12, int)

TAMANHO_MAX_FOTO = 8 * 1024 * 1024
TAMANHO_MAX_REQUISICAO = TAMANHO_MAX_FOTO + 512 * 1024
LADO_MAX_PX = 1600

COMBUSTIVEIS = (
    "Gasolina Comum",
    "Gasolina Aditivada",
    "Etanol",
    "Diesel",
)

PROMPT = """
Você é um assistente especializado em ler painéis/totens de preços de postos de combustível no Brasil.
Extraia os preços visíveis na imagem e responda ESTRITAMENTE com um objeto JSON válido, sem texto extra
e sem markdown.
Use exatamente estas chaves: "Gasolina Comum", "Gasolina Aditivada", "Etanol", "Diesel".
Os valores são números em reais com ponto decimal (ex.: 5.89), nunca texto.
Se um combustível não estiver visível ou legível, NÃO o inclua. Nunca estime nem invente valores.
Ignore outros produtos (GNV, arla, lubrificantes) e qualquer número que não seja preço por litro.
"""

_cliente_ia = None


def _cliente():
    global _cliente_ia

    if _cliente_ia is None:
        if genai is None or types is None:
            raise RuntimeError(
                "Dependência google-genai não instalada."
            )

        chave = os.getenv("GEMINI_API_KEY")

        if not chave:
            raise RuntimeError("GEMINI_API_KEY não definida.")

        _cliente_ia = genai.Client(
            api_key=chave,
            http_options=types.HttpOptions(
                timeout=int(TIMEOUT_IA_S * 1000),
            ),
        )

    return _cliente_ia


def _config_geracao():
    tipos = types

    if tipos is None:
        raise RuntimeError(
            "Dependência google-genai não instalada."
        )

    kwargs = {
        "response_mime_type": "application/json",
    }

    if NIVEL_RACIOCINIO in (
        "minimal",
        "low",
        "medium",
        "high",
    ):
        kwargs["thinking_config"] = tipos.ThinkingConfig(
            thinking_level=NIVEL_RACIOCINIO,
        )

    return tipos.GenerateContentConfig(**kwargs)


_uso = defaultdict(deque)
_uso_trava = threading.Lock()


def _excedeu_limite(usuario_id):
    """Janela deslizante de uma hora, em memória do processo."""
    if LIMITE_POR_HORA <= 0:
        return False

    agora = time.monotonic()

    with _uso_trava:
        fila = _uso[usuario_id]

        while fila and agora - fila[0] > 3600:
            fila.popleft()

        if len(fila) >= LIMITE_POR_HORA:
            return True

        fila.append(agora)
        return False


class _FotoInvalida(Exception):
    pass


def _preparar_imagem(bruto):
    """Prepara JPEG sem metadados e preserva a exceção da rota."""
    try:
        return preparar_imagem_totem(bruto, LADO_MAX_PX)
    except FotoTotemInvalida as erro:
        raise _FotoInvalida(str(erro)) from erro


def _extrair_json(texto):
    texto = re.sub(
        r"^\s*```(?:json)?\s*|\s*```\s*$",
        "",
        texto or "",
        flags=re.I,
    ).strip()

    try:
        return json.loads(texto)

    except json.JSONDecodeError:
        trecho = re.search(r"\{.*\}", texto, re.S)

        if not trecho:
            raise

        return json.loads(trecho.group(0))


def _normalizar_precos(bruto):
    """Filtra sugestões sem fabricar preços nem arredondar frações."""
    return normalizar_precos_totem(bruto)


def _carregar_posto(posto_id):
    conn = None

    try:
        conn = get_db_connection()

        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT latitude, longitude, tipo_posto
                FROM postos
                WHERE id = %s
                """,
                (posto_id,),
            )
            return cursor.fetchone()

    finally:
        if conn and conn.open:
            conn.close()


@ia_bp.route(
    "/ler-totem",
    methods=["POST"],
    strict_slashes=False,
)
@token_required
def ler_totem(current_user_id):
    if (
        request.content_length
        and request.content_length > TAMANHO_MAX_REQUISICAO
    ):
        return jsonify(
            error="Foto muito grande. O limite é de 8 MB."
        ), 413

    # A permissão vem da conta autenticada no servidor.
    try:
        administrativo = politica_precos(
            current_user_id
        )["administrativo"]

    except RecusaServico as erro:
        return jsonify(
            error=str(erro),
            codigo=erro.codigo,
        ), erro.status

    foto = request.files.get("foto")

    if foto is None:
        return jsonify(error="Nenhuma foto enviada."), 400

    try:
        posto_id = int(request.form.get("posto_id", ""))

    except ValueError:
        return jsonify(
            error="Informe o posto (posto_id) junto com a foto."
        ), 400

    if (
        not administrativo
        and request.form.get(
            "simulada", ""
        ).strip().lower() == "true"
    ):
        return jsonify(
            error="Localização simulada não é aceite.",
            codigo="GPS_SIMULADO",
        ), 403

    try:
        posto = _carregar_posto(posto_id)

    except Exception:
        log.exception(
            "Erro ao carregar o posto %s para leitura de totem",
            posto_id,
        )
        return jsonify(
            error="Erro interno ao validar o posto."
        ), 500

    if not posto:
        return jsonify(error="Posto não encontrado."), 404

    if posto.get("tipo_posto") == "Eletroposto":
        return jsonify(
            error="A leitura por foto é só para postos de combustível."
        ), 400

    # Apenas o usuário comum precisa comprovar proximidade.
    if not administrativo:
        try:
            validar_proximidade(
                request.form.get("latitude"),
                request.form.get("longitude"),
                request.form.get("precisao_m"),
                posto["latitude"],
                posto["longitude"],
            )

        except GeofenceError as erro:
            corpo, status = erro.para_resposta()
            return jsonify(corpo), status

    bruto = foto.read(TAMANHO_MAX_FOTO + 1)

    if not bruto:
        return jsonify(
            error="A foto enviada está vazia."
        ), 400

    if len(bruto) > TAMANHO_MAX_FOTO:
        return jsonify(
            error="Foto muito grande. O limite é de 8 MB."
        ), 413

    try:
        jpeg = _preparar_imagem(bruto)

    except _FotoInvalida as erro:
        return jsonify(error=str(erro)), 400

    # O administrador também respeita o limite de uso da IA.
    if _excedeu_limite(current_user_id):
        return jsonify(
            error=(
                "Você atingiu o limite de leituras por foto "
                "desta hora. Digite o preço manualmente."
            ),
            codigo="LIMITE_IA",
        ), 429

    try:
        tipos = types

        if tipos is None:
            raise RuntimeError(
                "Dependência google-genai não instalada."
            )

        resposta = _cliente().models.generate_content(
            model=MODELO,
            contents=[
                tipos.Part.from_bytes(
                    data=jpeg,
                    mime_type="image/jpeg",
                ),
                PROMPT,
            ],
            config=_config_geracao(),
        )

    except Exception as erro:
        if getattr(erro, "code", None) == 404:
            log.error(
                'Modelo Gemini "%s" indisponível (404). '
                "Ajuste GEMINI_MODEL.",
                MODELO,
            )

        log.exception("Falha na chamada ao Gemini")

        return jsonify(error=(
            "A leitura por IA está indisponível agora. "
            "Tente novamente em instantes ou digite o preço."
        )), 502

    try:
        precos = _normalizar_precos(
            _extrair_json(getattr(resposta, "text", None))
        )

    except (json.JSONDecodeError, TypeError):
        precos = {}

    if not precos:
        return jsonify(
            error=(
                "Não consegui ler os preços na foto. "
                "Tire de mais perto, com o totem enquadrado "
                "e sem reflexos."
            ),
            codigo="LEITURA_VAZIA",
        ), 422

    foto_url = None

    # Armazenamento externo somente com consentimento.
    if request.form.get(
        "guardar_comprovante", ""
    ).strip().lower() == "true":
        try:
            foto_url = upload_foto_totem(
                io.BytesIO(jpeg),
                "totem.jpg",
            )

        except Exception:
            log.exception(
                "Falha ao guardar a prova no Dropbox"
            )

    return jsonify(
        sucesso=True,
        precos=precos,
        foto_url=foto_url,
    ), 200