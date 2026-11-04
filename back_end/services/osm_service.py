"""
Busca postos e eletropostos no OpenStreetMap via Overpass.
"""

from __future__ import annotations

import json
import logging
import math
import os
import socket
import ssl
import threading
import time

from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from services.grid_postos import BBox, ResultadoBusca

# Permite trocar o servidor pelo .env.
OVERPASS_URL = (
    os.getenv("OSM_OVERPASS_URL", "").strip()
    or "https://overpass-api.de/api/interpreter"
)
ATRIBUICAO = "© OpenStreetMap contributors — ODbL"
LICENCA_URL = "https://www.openstreetmap.org/copyright"

TIMEOUT_SEGUNDOS = 20
MAX_RESPOSTA_BYTES = 4 * 1024 * 1024

INTERVALO_CONSULTAS_SEGUNDOS = 30
CACHE_SEGUNDOS = 86400

# Ordem: sul, oeste, norte, leste.
# Área inicial: João Pessoa e arredores.
AREA_PADRAO = (-7.30, -35.05, -6.95, -34.75)


class OSMIndisponivel(RuntimeError):
    """Falha de consulta ou limite temporário de utilização."""


def _validar_bbox(bbox) -> BBox:
    try:
        sul, oeste, norte, leste = map(float, bbox)
    except (TypeError, ValueError):
        raise ValueError(
            "Área inválida. Use sul,oeste,norte,leste."
        ) from None

    valores = (sul, oeste, norte, leste)

    if not all(math.isfinite(valor) for valor in valores):
        raise ValueError(
            "A área precisa conter coordenadas finitas."
        )

    if not (
        -90 <= sul < norte <= 90
        and -180 <= oeste < leste <= 180
    ):
        raise ValueError("Limites da área inválidos.")

    return sul, oeste, norte, leste


def area_configurada() -> BBox:
    bruto = os.getenv("OSM_AREA_BBOX", "").strip()

    return _validar_bbox(
        bruto.split(",") if bruto else AREA_PADRAO
    )


def dentro_da_area(lat: float, lon: float) -> bool:
    sul, oeste, norte, leste = area_configurada()

    return (
        sul <= lat <= norte
        and oeste <= lon <= leste
    )


def sincronizacao_habilitada() -> bool:
    # Desativada por padrão: testar a prévia não importa registros.
    valor = os.getenv(
        "OSM_SYNC_ENABLED",
        "false",
    ).strip().lower()

    return valor in ("1", "true", "yes")


def _texto(valor, limite: int) -> str:
    return str(valor or "").strip()[:limite]


def mapear_elemento(elemento) -> dict | None:
    if not isinstance(elemento, dict):
        return None

    tipo = elemento.get("type")
    ident = elemento.get("id")

    if (
        tipo not in ("node", "way", "relation")
        or type(ident) is not int
        or ident <= 0
    ):
        return None

    tags = elemento.get("tags") or {}

    if not isinstance(tags, dict):
        return None

    if tags.get("amenity") not in (
        "fuel",
        "charging_station",
    ):
        return None

    if tags.get("access") in ("private", "no"):
        return None

    # Nós possuem coordenadas diretamente.
    # Vias e relações usam o centro retornado pela Overpass.
    coords = (
        elemento
        if tipo == "node"
        else elemento.get("center")
    )

    if not isinstance(coords, dict):
        return None

    if any(
        isinstance(coords.get(chave), bool)
        for chave in ("lat", "lon")
    ):
        return None

    try:
        lat = float(coords["lat"])
        lon = float(coords["lon"])
    except (KeyError, TypeError, ValueError):
        return None

    if not (
        math.isfinite(lat)
        and math.isfinite(lon)
        and -90 <= lat <= 90
        and -180 <= lon <= 180
    ):
        return None

    id_externo = f"osm:{tipo}:{ident}"

    # A coluna existente aceita 100 caracteres.
    # Nunca cortar um identificador único.
    if len(id_externo) > 100:
        return None

    eletrico = tags["amenity"] == "charging_station"

    nome = (
        tags.get("name")
        or tags.get("brand")
        or tags.get("operator")
    )

    if not nome:
        nome = (
            "Eletroposto sem nome"
            if eletrico
            else "Posto sem nome"
        )

    rua = _texto(
        tags.get("addr:street") or tags.get("addr:place"),
        220,
    )

    numero = _texto(
        tags.get("addr:housenumber"),
        30,
    )

    endereco = ", ".join(
        parte for parte in (rua, numero) if parte
    )

    horario = _texto(
        tags.get("opening_hours"),
        500,
    )

    if horario == "24/7":
        horario = "24 Horas"
    elif not horario:
        horario = "Horário não informado"
    elif len(horario) > 50:
        # Evita cortar uma expressão de horários e mudar seu sentido.
        horario = "Consulte o posto"

    uf = str(
        tags.get("addr:state") or ""
    ).strip().upper()

    if uf == "PARAÍBA":
        uf = "PB"

    return {
        "id_externo": id_externo,
        "nome": _texto(nome, 150),
        "endereco": _texto(endereco, 255),
        "bairro": _texto(
            tags.get("addr:suburb")
            or tags.get("addr:neighbourhood"),
            100,
        ),
        "cidade": _texto(tags.get("addr:city"), 100),
        "uf": uf if len(uf) == 2 else "",
        "latitude": lat,
        "longitude": lon,
        "tipo_posto": (
            "Eletroposto" if eletrico else "Convencional"
        ),
        "horario_funcionamento": horario,
    }


def montar_consulta(bbox: BBox) -> str:
    sul, oeste, norte, leste = _validar_bbox(bbox)

    # Impede consultas excessivamente grandes.
    if norte - sul > 0.1 or leste - oeste > 0.1:
        raise ValueError(
            "Consulte uma área menor "
            "(até 0,1 grau por lado)."
        )

    caixa = (
        f"{sul:.7f},{oeste:.7f},"
        f"{norte:.7f},{leste:.7f}"
    )

    return (
        '[out:json][timeout:15];('
        f'nwr["amenity"="fuel"]({caixa});'
        f'nwr["amenity"="charging_station"]({caixa});'
        ');out center tags;'
    )


def _consultar_overpass(consulta: str) -> dict:
    log = logging.getLogger(__name__)

    requisicao = Request(
        OVERPASS_URL,
        data=urlencode({
            "data": consulta,
        }).encode("utf-8"),
        headers={
            "Content-Type": (
                "application/x-www-form-urlencoded"
            ),
            "Accept": "application/json",
            "User-Agent": (
                "LitroDeOuro/1.0 "
                "(https://github.com/"
                "odethemets/litro_de_ouro_app)"
            ),
        },
        method="POST",
    )

    try:
        with urlopen(
            requisicao,
            timeout=TIMEOUT_SEGUNDOS,
        ) as resposta:
            dados = resposta.read(
                MAX_RESPOSTA_BYTES + 1
            )

        if len(dados) > MAX_RESPOSTA_BYTES:
            raise OSMIndisponivel(
                "Resposta muito grande; "
                "reduza a área consultada."
            )

    except HTTPError as erro:
        log.warning(
            "Overpass: etapa=http status=%s",
            erro.code,
        )

        raise OSMIndisponivel(
            f"Overpass indisponível (HTTP {erro.code})."
        ) from None

    except (URLError, TimeoutError, OSError) as erro:
        causa = (
            erro.reason
            if isinstance(erro, URLError)
            else erro
        )

        # Registra tipos e códigos, sem expor credenciais
        # ou configurações de proxy.
        log.warning(
            "Overpass: etapa=conexao_leitura "
            "tipo=%s causa=%s errno=%s tls_codigo=%s",
            type(erro).__name__,
            type(causa).__name__,
            getattr(causa, "errno", None),
            getattr(causa, "verify_code", None),
        )

        if isinstance(causa, ssl.SSLCertVerificationError):
            mensagem = (
                "Falha na verificação do certificado "
                "HTTPS da Overpass."
            )

        elif isinstance(causa, ssl.SSLError):
            mensagem = (
                "Falha na conexão TLS com a Overpass."
            )

        elif isinstance(causa, socket.gaierror):
            mensagem = (
                "Não foi possível resolver o endereço "
                "da Overpass (DNS)."
            )

        elif isinstance(causa, TimeoutError):
            mensagem = (
                "Tempo limite ao conectar ou receber "
                "dados da Overpass."
            )

        else:
            mensagem = (
                "Falha de conexão com a Overpass. "
                "Confira o diagnóstico no terminal."
            )

        raise OSMIndisponivel(mensagem) from None

    try:
        corpo = json.loads(dados)

    except (json.JSONDecodeError, UnicodeDecodeError) as erro:
        log.warning(
            "Overpass: etapa=json tipo=%s",
            type(erro).__name__,
        )

        raise OSMIndisponivel(
            "A Overpass retornou uma resposta "
            "que não é JSON válido."
        ) from None

    # Respostas parciais também podem chegar com HTTP 200.
    if (
        not isinstance(corpo, dict)
        or corpo.get("remark")
        or not isinstance(corpo.get("elements"), list)
    ):
        log.warning(
            "Overpass: etapa=resposta_incompleta"
        )

        raise OSMIndisponivel(
            "A Overpass não retornou "
            "uma resposta completa."
        )

    return corpo


_trava_consulta = threading.Lock()
_proxima_consulta = 0.0

_cache: dict[
    BBox,
    tuple[float, ResultadoBusca],
] = {}


# Esta é a função importada por app/rotas/postos.py.
def buscar_postos_por_bbox(
    bbox: BBox,
) -> ResultadoBusca:
    global _proxima_consulta

    sul, oeste, norte, leste = _validar_bbox(bbox)

    area_sul, area_oeste, area_norte, area_leste = (
        area_configurada()
    )

    # Recorta a consulta à região atendida pelo projeto.
    bbox = (
        max(sul, area_sul),
        max(oeste, area_oeste),
        min(norte, area_norte),
        min(leste, area_leste),
    )

    if bbox[0] >= bbox[2] or bbox[1] >= bbox[3]:
        return ResultadoBusca([])

    consulta = montar_consulta(bbox)

    if not _trava_consulta.acquire(blocking=False):
        raise OSMIndisponivel(
            "Já existe uma consulta em andamento; "
            "tente novamente depois."
        )

    try:
        agora = time.monotonic()
        entrada = _cache.get(bbox)

        if entrada and agora - entrada[0] < CACHE_SEGUNDOS:
            return entrada[1]

        if agora < _proxima_consulta:
            raise OSMIndisponivel(
                "Aguarde 30 segundos entre consultas "
                "a áreas diferentes."
            )

        try:
            corpo = _consultar_overpass(consulta)
        finally:
            _proxima_consulta = (
                time.monotonic()
                + INTERVALO_CONSULTAS_SEGUNDOS
            )

        unicos = {}

        for elemento in corpo["elements"]:
            lugar = mapear_elemento(elemento)

            if lugar is None:
                continue

            if (
                bbox[0] <= lugar["latitude"] <= bbox[2]
                and bbox[1] <= lugar["longitude"] <= bbox[3]
            ):
                unicos[lugar["id_externo"]] = lugar

        resultado = ResultadoBusca(
            list(unicos.values())
        )

        # Limita o número de áreas mantidas em memória.
        if len(_cache) >= 128:
            del _cache[next(iter(_cache))]

        _cache[bbox] = (
            time.monotonic(),
            resultado,
        )

        return resultado

    finally:
        _trava_consulta.release()