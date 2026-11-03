"""
Cliente Mapbox do Litro de Ouro.

Mantém o endpoint que o projeto já usava (Geocoding v5, busca por texto "posto de combustivel"),
mas agora recebe uma BBOX (a célula do grid) em vez de um ponto solto, com retry limitado,
timeout e parsing defensivo. Só é chamado pela sincronização em segundo plano
(services/grid_postos.py), nunca diretamente pela requisição do utilizador.

Variáveis de ambiente:
  MAPBOX_TOKEN        token (já existente)
  MAPBOX_PERMANENT    "1" para enviar permanent=true. Necessário porque os resultados são GRAVADOS
                      na tabela `postos` (os resultados "temporários" do Mapbox não podem ser
                      guardados). Exige cartão no Mapbox e é cobrado a um preço diferente.

NÃO foi possível chamar a API real ao escrever este ficheiro: o parsing segue a estrutura do v5
(id, text, place_name, geometry.coordinates, properties.address, context[]). Valide com uma
chamada real antes de ir para produção.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from services.grid_postos import ResultadoBusca

log = logging.getLogger(__name__)

URL = "https://api.mapbox.com/geocoding/v5/mapbox.places/posto%20de%20combustivel.json"
TIMEOUT = (3.05, 5.0)  # (conexão, leitura) em segundos
LIMITE_POR_CHAMADA = 10  # teto do Geocoding v5

CIDADE_PADRAO = os.getenv("GRID_CIDADE_PADRAO", "João Pessoa")
UF_PADRAO = os.getenv("GRID_UF_PADRAO", "PB")

_PALAVRAS_CATEGORIA = ("gas", "fuel", "combust", "posto", "petrol")

_sessao: Optional[requests.Session] = None


def _sessao_http() -> requests.Session:
    global _sessao
    if _sessao is None:
        s = requests.Session()
        retry = Retry(
            total=1,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            respect_retry_after_header=True,
        )
        s.mount("https://", HTTPAdapter(max_retries=retry))
        _sessao = s
    return _sessao


def _cortar(valor: Any, limite: int) -> str:
    return str(valor or "").strip()[:limite]


def _contexto(feature: dict, *prefixos: str) -> str:
    for item in feature.get("context") or []:
        if not isinstance(item, dict):
            continue
        ident = str(item.get("id", ""))
        if any(ident.startswith(p + ".") for p in prefixos) and item.get("text"):
            return str(item["text"])
    return ""


def _categoria_ok(feature: dict) -> bool:
    """A busca é por TEXTO: pode trazer "Posto de Saúde". Se houver categoria, exige combustível."""
    categoria = str((feature.get("properties") or {}).get("category") or "").lower()
    return True if not categoria else any(p in categoria for p in _PALAVRAS_CATEGORIA)


def mapear_feature(feature: dict) -> Optional[dict]:
    """Feature do Mapbox -> dict interno (colunas de `postos`). None se inutilizável."""
    if not isinstance(feature, dict) or not _categoria_ok(feature):
        return None
    coords = (feature.get("geometry") or {}).get("coordinates") or []
    try:
        lon, lat = float(coords[0]), float(coords[1])
    except (TypeError, ValueError, IndexError):
        return None
    mapbox_id = feature.get("id")
    if not mapbox_id or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return None

    props = feature.get("properties") or {}
    region = next(
        (str(c.get("short_code")) for c in feature.get("context") or []
         if isinstance(c, dict) and str(c.get("id", "")).startswith("region.") and c.get("short_code")),
        "",
    )
    uf = region.split("-")[-1].upper()[:2] if region else ""

    return {
        "mapbox_id": _cortar(mapbox_id, 255),
        "nome": _cortar(feature.get("text") or "Posto", 100),
        "endereco": _cortar(props.get("address") or feature.get("place_name"), 255),
        "bairro": _cortar(_contexto(feature, "neighborhood", "locality", "district"), 100),
        "cidade": _cortar(_contexto(feature, "place") or CIDADE_PADRAO, 100),
        "uf": uf or UF_PADRAO,
        "latitude": lat,
        "longitude": lon,
    }


def buscar_postos_por_bbox(bbox: tuple[float, float, float, float]) -> ResultadoBusca:
    """bbox = (min_lat, min_lon, max_lat, max_lon). Levanta exceção em falha: o chamador faz backoff."""
    token = os.getenv("MAPBOX_TOKEN")
    if not token:
        raise RuntimeError("MAPBOX_TOKEN não definido.")

    min_lat, min_lon, max_lat, max_lon = bbox
    params = {
        "access_token": token,
        "bbox": f"{min_lon},{min_lat},{max_lon},{max_lat}",  # Mapbox usa lon,lat
        "proximity": f"{(min_lon + max_lon) / 2},{(min_lat + max_lat) / 2}",
        "limit": LIMITE_POR_CHAMADA,
        "language": "pt",
        "country": "br",
        "types": "poi",
    }
    if os.getenv("MAPBOX_PERMANENT", "").strip().lower() in ("1", "true", "yes"):
        params["permanent"] = "true"

    resposta = _sessao_http().get(URL, params=params, timeout=TIMEOUT)
    resposta.raise_for_status()

    features = resposta.json().get("features") or []
    lugares = [m for m in (mapear_feature(f) for f in features) if m]
    if len(lugares) != len(features):
        log.info("Mapbox: %d de %d resultados descartados (sem coordenadas ou não são postos)", len(features) - len(lugares), len(features))
    # `truncado` usa a contagem BRUTA: se o Mapbox devolveu o teto, pode haver mais postos na célula.
    return ResultadoBusca(lugares=lugares, truncado=len(features) >= LIMITE_POR_CHAMADA)