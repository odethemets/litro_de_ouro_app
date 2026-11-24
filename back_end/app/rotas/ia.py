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
    genai = importlib.import_module('google.genai')
    types = importlib.import_module('google.genai.types')
except ModuleNotFoundError:
    genai = None
    types = None

ia_bp = Blueprint('ia', __name__)
log = logging.getLogger(__name__)


def _env_num(nome, padrao, tipo=float):
    try:
        valor = tipo(os.getenv(nome, ''))
    except ValueError:
        return padrao
    return valor if valor >= 0 else padrao


# ------------------------------------------------------------------ configuração
# Todos os modelos Gemini 3 ainda são "preview": o nome pode mudar. Por isso vem do ambiente.
# Padrão = Flash: ler um painel de preços não precisa do Pro (que custa ~4x mais por token).
# Para trocar: GEMINI_MODEL=gemini-3.1-pro-preview (ou o nome vigente em ai.google.dev/gemini-api/docs/models).
MODELO = os.getenv('GEMINI_MODEL') or 'gemini-3-flash-preview'
# Vazio = padrão da API, que no Gemini 3 já é "high". Valores aceitos: minimal|low|medium|high
# (o 3.1 Pro não aceita "minimal"). Para OCR de painel, "low" costuma bastar e responde mais rápido.
NIVEL_RACIOCINIO = (os.getenv('GEMINI_THINKING_LEVEL') or '').strip().lower()
TIMEOUT_IA_S = _env_num('GEMINI_TIMEOUT_S', 45.0)
LIMITE_POR_HORA = _env_num('IA_LIMITE_POR_HORA', 12, int)   # leituras por utilizador; 0 desativa
TAMANHO_MAX_FOTO = 8 * 1024 * 1024
TAMANHO_MAX_REQUISICAO = TAMANHO_MAX_FOTO + 512 * 1024
LADO_MAX_PX = 1600

COMBUSTIVEIS = ('Gasolina Comum', 'Gasolina Aditivada', 'Etanol', 'Diesel')

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
            raise RuntimeError('Dependência google-genai não instalada.')
        chave = os.getenv('GEMINI_API_KEY')
        if not chave:
            raise RuntimeError('GEMINI_API_KEY não definida.')
        _cliente_ia = genai.Client(
            api_key=chave,
            http_options=types.HttpOptions(timeout=int(TIMEOUT_IA_S * 1000)),  # milissegundos
        )
    return _cliente_ia


def _config_geracao():
    tipos = types
    if tipos is None:
        raise RuntimeError("Dependência google-genai não instalada.")

    # Não se define temperature: para o Gemini 3 o Google recomenda manter o padrão.
    kwargs = {'response_mime_type': 'application/json'}