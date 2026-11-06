"""Consulta de postos OSM via Overpass.

Mantém as funções usadas pela prévia existente e acrescenta a consulta
administrativa de João Pessoa, com User-Agent e contingência entre mirrors.
Este módulo não grava no MySQL.
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
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from services.grid_postos import BBox, ResultadoBusca


OVERPASS_URL = (
    os.getenv("OSM_OVERPASS_URL", "").strip()
    or "https://overpass-api.de/api/interpreter"
)

MIRRORS_PADRAO = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)

ATRIBUICAO = "© OpenStreetMap contributors — ODbL"
LICENCA_URL = "https://www.openstreetmap.org/copyright"

CODIGO_IBGE = "2507507"
MUNICIPIO = "João Pessoa"

TIMEOUT_SEGUNDOS = 20
MAX_RESPOSTA_BYTES = 4 * 1024 * 1024
INTERVALO_CONSULTAS_SEGUNDOS = 30
CACHE_SEGUNDOS = 86400

# Somente para a prévia legada por coordenadas.
# A importação municipal utiliza a área administrativa OSM.
AREA_PADRAO = (-7.30, -35.05, -6.95, -34.75)


class OSMIndisponivel(RuntimeError):
    def __init__(
        self,
        mensagem,
        status_http=None,
        retry_after=30,
        transitoria=False,
    ):
        super().__init__(mensagem)
        self.status_http = status_http
        self.retry_after = max(1, int(retry_after))
        self.transitoria = transitoria


def interpretar_retry_after(valor):
    """Aceita quantidade de segundos ou data no formato HTTP."""
    try:
        segundos = int(valor)
    except (TypeError, ValueError):
        try:
            data = parsedate_to_datetime(valor)

            if data.tzinfo is None:
                data = data.replace(tzinfo=timezone.utc)

            segundos = math.ceil(
                (data - datetime.now(timezone.utc)).total_seconds()
            )

        except (TypeError, ValueError, OverflowError):
            segundos = 30

    return max(1, segundos)


def user_agent_configurado():
    valor = os.getenv("OSM_USER_AGENT", "").strip() or (
        "LitroDeOuro/1.1 "
        "(+https://github.com/odethemets/litro_de_ouro_app)"
    )

    if (
        not 1 <= len(valor) <= 256
        or any(not 32 <= ord(c) <= 126 for c in valor)
    ):
        raise ValueError(
            "OSM_USER_AGENT deve ser ASCII, sem quebras de linha, "
            "até 256 caracteres."
        )

    return valor


def urls_configuradas():
    bruto = os.getenv("OSM_OVERPASS_URLS", "").strip()

    if bruto:
        urls = [
            parte.strip()
            for parte in bruto.split(",")
            if parte.strip()
        ]
    else:
        principal = (
            os.getenv("OSM_OVERPASS_URL", "").strip()
            or OVERPASS_URL
        )
        urls = [principal, *MIRRORS_PADRAO]

    urls = list(dict.fromkeys(urls))

    if not 1 <= len(urls) <= 3:
        raise ValueError(
            "Configure de um a três URLs Overpass."
        )

    for url in urls:
        partes = urlsplit(url)
        caminho = partes.path.rstrip("/")

        # Aceita o caminho habitual e o endpoint
        # específico identificado no Overpass Turbo.
        caminho_valido = (
            caminho == "/api/interpreter"
            or (
                partes.hostname == "api.overpass-turbo.eu"
                and caminho == "/interpreter"
            )
        )

        if (
            partes.scheme != "https"
            or not partes.hostname
            or partes.username
            or partes.password
            or partes.query
            or partes.fragment
            or partes.port not in (None, 443)
            or not caminho_valido
            or any(
                ord(caractere) < 33
                or ord(caractere) > 126
                for caractere in url
            )
        ):
            raise ValueError(
                "Configure URLs HTTPS Overpass com "
                "caminho permitido e sem credenciais."
            )

    return urls


def _validar_bbox(bbox) -> BBox:
    try:
        sul, oeste, norte, leste = map(float, bbox)
    except (TypeError, ValueError):
        raise ValueError(
            "Área inválida. Use sul,oeste,norte,leste."
        ) from None

    if not all(
        math.isfinite(valor)
        for valor in (sul, oeste, norte, leste)
    ):
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

    return sul <= lat <= norte and oeste <= lon <= leste


def sincronizacao_habilitada() -> bool:
    # Mantida por compatibilidade. GET /postos não usa esta flag.
    return os.getenv(
        "OSM_SYNC_ENABLED", "false"
    ).strip().lower() in ("1", "true", "yes")


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

    if (
        not isinstance(tags, dict)
        or tags.get("amenity") not in (
            "fuel",
            "charging_station",
        )
    ):
        return None

    if tags.get("access") in ("private", "no"):
        return None

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

    if len(id_externo) > 100:
        return None

    eletrico = tags["amenity"] == "charging_station"

    nome = (
        tags.get("name")
        or tags.get("brand")
        or tags.get("operator")
    )

    rua = _texto(
        tags.get("addr:street")
        or tags.get("addr:place"),
        220,
    )
    numero = _texto(tags.get("addr:housenumber"), 30)

    endereco = ", ".join(
        parte for parte in (rua, numero) if parte
    )

    horario = _texto(tags.get("opening_hours"), 500)

    if horario == "24/7":
        horario = "24 Horas"
    elif not horario:
        horario = "Horário não informado"
    elif len(horario) > 50:
        horario = "Consulte o posto"

    uf = str(tags.get("addr:state") or "").strip().upper()

    if uf == "PARAÍBA":
        uf = "PB"

    return {
        "id_externo": id_externo,
        "nome": _texto(
            nome or (
                "Eletroposto sem nome"
                if eletrico
                else "Posto sem nome"
            ),
            150,
        ),
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
            "Eletroposto"
            if eletrico
            else "Convencional"
        ),
        "horario_funcionamento": horario,
    }


def converter_resposta(corpo, bbox=None):
    """Parser compartilhado entre HTTP e arquivos JSON."""
    if (
        not isinstance(corpo, dict)
        or corpo.get("remark")
        or not isinstance(corpo.get("elements"), list)
    ):
        raise OSMIndisponivel(
            "A Overpass não retornou uma resposta completa."
        )

    unicos = {}
    descartados = 0

    for elemento in corpo["elements"]:
        lugar = mapear_elemento(elemento)

        if lugar is None:
            descartados += 1
            continue

        if bbox and not (
            bbox[0] <= lugar["latitude"] <= bbox[2]
            and bbox[1] <= lugar["longitude"] <= bbox[3]
        ):
            descartados += 1
            continue

        ident = lugar["id_externo"]

        if ident in unicos:
            if unicos[ident] != lugar:
                raise ValueError(
                    "Mesmo identificador OSM com "
                    "dados conflitantes no arquivo."
                )

            descartados += 1

        unicos[ident] = lugar

    return ResultadoBusca(list(unicos.values())), descartados


def montar_consulta(bbox: BBox) -> str:
    """Mantém a prévia existente por uma caixa pequena."""
    sul, oeste, norte, leste = _validar_bbox(bbox)

    if norte - sul > 0.1 or leste - oeste > 0.1:
        raise ValueError(
            "Consulte uma área menor: até 0,1 grau por lado."
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


def montar_consulta_municipio():
    """Busca a área administrativa e seus postos na mesma resposta."""
    return (
        '[out:json][timeout:30];'
        'area["boundary"="administrative"]["admin_level"="8"]'
        f'["IBGE:GEOCODIGO"="{CODIGO_IBGE}"]->.municipio;'
        '.municipio out tags;('
        'nwr["amenity"="fuel"](area.municipio);'
        'nwr["amenity"="charging_station"](area.municipio);'
        ');out center tags;'
    )


def validar_municipio(corpo):
    if (
        not isinstance(corpo, dict)
        or corpo.get("remark")
        or not isinstance(corpo.get("elements"), list)
    ):
        raise OSMIndisponivel(
            "Resposta municipal incompleta.",
            transitoria=True,
        )

    areas = [
        elemento
        for elemento in corpo["elements"]
        if isinstance(elemento, dict)
        and elemento.get("type") == "area"
    ]

    if len(areas) != 1:
        raise OSMIndisponivel(
            "Área administrativa ausente ou ambígua; "
            "nenhuma importação autorizada.",
            transitoria=True,
        )

    area = areas[0]
    tags = area.get("tags") or {}

    if (
        not isinstance(tags, dict)
        or tags.get("IBGE:GEOCODIGO") != CODIGO_IBGE
        or tags.get("boundary") != "administrative"
        or tags.get("admin_level") != "8"
        or type(area.get("id")) is not int
        or area["id"] <= 0
    ):
        raise OSMIndisponivel(
            "A resposta não comprova a área "
            "administrativa de João Pessoa."
        )

    return {
        "nome": MUNICIPIO,
        "codigo_ibge": CODIGO_IBGE,
        "osm_area_id": area["id"],
    }


def _consultar_overpass(
    consulta: str,
    url=None,
    timeout=None,
) -> dict:
    log = logging.getLogger(__name__)

    requisicao = Request(
        url or OVERPASS_URL,
        data=urlencode({
            "data": consulta,
        }).encode("utf-8"),
        headers={
            "Content-Type": (
                "application/x-www-form-urlencoded"
            ),
            "Accept": "application/json",
            "User-Agent": user_agent_configurado(),
        },
        method="POST",
    )

    limite_tempo = (
        TIMEOUT_SEGUNDOS
        if timeout is None
        else timeout
    )

    try:
        with urlopen(
            requisicao,
            timeout=limite_tempo,
        ) as resposta:
            dados = resposta.read(MAX_RESPOSTA_BYTES + 1)

        if len(dados) > MAX_RESPOSTA_BYTES:
            raise OSMIndisponivel(
                "Resposta muito grande; "
                "reduza a área consultada."
            )

    except HTTPError as erro:
        status = erro.code

        espera = interpretar_retry_after(
            erro.headers.get("Retry-After")
            if erro.headers
            else None
        )

        erro.close()

        log.warning(
            "Overpass: etapa=http status=%s",
            status,
        )

        raise OSMIndisponivel(
            f"Overpass indisponível (HTTP {status}).",
            status_http=status,
            retry_after=espera,
            transitoria=status in (
                406,
                408,
                429,
                500,
                502,
                503,
                504,
            ),
        ) from None

    except (URLError, TimeoutError, OSError) as erro:
        causa = (
            erro.reason
            if isinstance(erro, URLError)
            else erro
        )

        log.warning(
            "Overpass: etapa=conexao_leitura "
            "tipo=%s causa=%s errno=%s tls_codigo=%s",
            type(erro).__name__,
            type(causa).__name__,
            getattr(causa, "errno", None),
            getattr(causa, "verify_code", None),
        )

        if isinstance(
            causa,
            ssl.SSLCertVerificationError,
        ):
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

        raise OSMIndisponivel(
            mensagem,
            transitoria=not isinstance(
                causa,
                ssl.SSLError,
            ),
        ) from None

    try:
        corpo = json.loads(dados)
    except (
        json.JSONDecodeError,
        UnicodeDecodeError,
    ) as erro:
        log.warning(
            "Overpass: etapa=json tipo=%s",
            type(erro).__name__,
        )

        raise OSMIndisponivel(
            "A Overpass retornou uma resposta "
            "que não é JSON válido.",
            transitoria=True,
        ) from None

    if (
        not isinstance(corpo, dict)
        or corpo.get("remark")
        or not isinstance(corpo.get("elements"), list)
    ):
        log.warning(
            "Overpass: etapa=resposta_incompleta"
        )

        raise OSMIndisponivel(
            "A Overpass não retornou uma "
            "resposta completa.",
            transitoria=True,
        )

    return corpo


def consultar_com_contingencia(
    consulta,
    tentativas=2,
    max_espera=120,
    dormir=time.sleep,
    validador=None,
    timeout=45,
):
    """Limita tentativas e respeita a espera antes de trocar de mirror."""
    if (
        not 1 <= tentativas <= 3
        or not 0 <= max_espera <= 300
    ):
        raise ValueError(
            "Tentativas/espera fora dos limites."
        )

    urls = urls_configuradas()
    user_agent_configurado()

    for indice in range(tentativas):
        url = urls[indice % len(urls)]

        try:
            corpo = _consultar_overpass(
                consulta,
                url=url,
                timeout=timeout,
            )

            if validador:
                validador(corpo)

            return corpo, {
                "servidor": urlsplit(url).hostname,
                "tentativas": indice + 1,
            }

        except OSMIndisponivel as erro:
            espera = max(
                erro.retry_after,
                INTERVALO_CONSULTAS_SEGUNDOS
                * (2 ** indice),
            )

            if (
                not erro.transitoria
                or indice + 1 >= tentativas
                or espera > max_espera
            ):
                raise

            logging.getLogger(__name__).warning(
                "Overpass indisponível; próxima "
                "tentativa %s/%s após %ss.",
                indice + 2,
                tentativas,
                espera,
            )

            dormir(espera)


def buscar_municipio(
    tentativas=2,
    max_espera=120,
    dormir=time.sleep,
):
    return consultar_com_contingencia(
        montar_consulta_municipio(),
        tentativas,
        max_espera,
        dormir,
        validador=validar_municipio,
    )


def testar_conexao(
    tentativas=1,
    max_espera=120,
    dormir=time.sleep,
):
    # Consulta mínima. Não acessa o MySQL.
    _, metadados = consultar_com_contingencia(
        '[out:json][timeout:5];node(1);out ids;',
        tentativas,
        max_espera,
        dormir,
        timeout=15,
    )

    return metadados


_trava_consulta = threading.Lock()
_proxima_consulta = 0.0
_cache: dict[BBox, tuple[float, ResultadoBusca]] = {}


def buscar_postos_por_bbox(
    bbox: BBox,
) -> ResultadoBusca:
    """Prévia legada por coordenadas, com cache e limite de frequência."""
    global _proxima_consulta

    sul, oeste, norte, leste = _validar_bbox(bbox)
    a, b, c, d = area_configurada()

    bbox = (
        max(sul, a),
        max(oeste, b),
        min(norte, c),
        min(leste, d),
    )

    if bbox[0] >= bbox[2] or bbox[1] >= bbox[3]:
        return ResultadoBusca([])

    consulta = montar_consulta(bbox)

    if not _trava_consulta.acquire(blocking=False):
        raise OSMIndisponivel(
            "Já existe uma consulta em andamento; "
            "tente novamente depois.",
            transitoria=True,
        )

    try:
        agora = time.monotonic()
        entrada = _cache.get(bbox)

        if (
            entrada
            and agora - entrada[0] < CACHE_SEGUNDOS
        ):
            return entrada[1]

        if agora < _proxima_consulta:
            raise OSMIndisponivel(
                "Aguarde entre consultas "
                "a áreas diferentes.",
                retry_after=math.ceil(
                    _proxima_consulta - agora
                ),
                transitoria=True,
            )

        try:
            corpo = _consultar_overpass(consulta)

        except OSMIndisponivel as erro:
            _proxima_consulta = (
                time.monotonic()
                + max(
                    INTERVALO_CONSULTAS_SEGUNDOS,
                    min(86400, erro.retry_after),
                )
            )
            raise

        else:
            _proxima_consulta = (
                time.monotonic()
                + INTERVALO_CONSULTAS_SEGUNDOS
            )

        resultado, _ = converter_resposta(
            corpo,
            bbox,
        )

        if len(_cache) >= 128:
            del _cache[next(iter(_cache))]

        _cache[bbox] = (
            time.monotonic(),
            resultado,
        )

        return resultado

    finally:
        _trava_consulta.release()