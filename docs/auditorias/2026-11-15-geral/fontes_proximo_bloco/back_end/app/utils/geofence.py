"""
Geofencing do Litro de Ouro.

Responsabilidades:
  1. Validar coordenadas recebidas do cliente (ausentes, não numéricas, fora de faixa,
     NaN/Infinity, "Null Island" 0,0 que é o valor típico de GPS falhado).
  2. Calcular a distância cliente <-> posto (haversine).
  3. Decidir se o registo é aceite, devolvendo erros com `codigo` estável para o
     frontend poder reagir (pedir GPS de novo, avisar que está longe, etc.).

Configuração por variável de ambiente (valores inválidos caem no padrão):
  GEOFENCE_RAIO_M            raio base em metros                      (padrão 500)
  GEOFENCE_PRECISAO_MAX_M    acima disto o fix de GPS é rejeitado     (padrão 150)
  GEOFENCE_FOLGA_MAX_M       máximo de folga concedida por precisão   (padrão 100)

Limite conhecido: coordenadas vêm do cliente e podem ser forjadas (apps de
localização falsa). Este módulo impede erros e abusos casuais, não fraude
determinada. Ver notas na resposta de integração.
"""
from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from typing import Any, Optional

RAIO_TERRA_M = 6_371_008.8


def _env_float(nome: str, padrao: float) -> float:
    try:
        valor = float(os.getenv(nome, ""))
    except ValueError:
        return padrao
    return valor if math.isfinite(valor) and valor > 0 else padrao


log = logging.getLogger(__name__)

RAIO_PADRAO_M = _env_float("GEOFENCE_RAIO_M", 500.0)
PRECISAO_MAX_ACEITA_M = _env_float("GEOFENCE_PRECISAO_MAX_M", 150.0)
FOLGA_MAX_POR_PRECISAO_M = _env_float("GEOFENCE_FOLGA_MAX_M", 100.0)

if RAIO_PADRAO_M > 2000:
    # Útil para testar em casa (ex.: GEOFENCE_RAIO_M=50000), mas anula a proteção anti-fraude.
    log.warning("GEOFENCE_RAIO_M=%s m: raio de DESENVOLVIMENTO ativo. Não use em produção.", RAIO_PADRAO_M)


class GeofenceError(Exception):
    """Erro de validação de localização, serializável para resposta HTTP."""

    def __init__(self, codigo: str, mensagem: str, status: int = 400, **extra: Any):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.status = status
        self.extra = extra

    def para_resposta(self) -> tuple[dict, int]:
        corpo = {"error": self.mensagem, "codigo": self.codigo}
        corpo.update(self.extra)
        return corpo, self.status


@dataclass(frozen=True)
class ResultadoGeofence:
    distancia_m: float
    raio_efetivo_m: float


def _como_float(valor: Any) -> Optional[float]:
    """Converte para float finito ou devolve None. Rejeita bool (True == 1 em Python)."""
    if isinstance(valor, bool) or valor is None:
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def validar_coordenadas(lat: Any, lon: Any) -> tuple[float, float]:
    if lat is None or lon is None:
        raise GeofenceError(
            "GPS_AUSENTE",
            "Localização não enviada. Ative o GPS e tente novamente.",
            400,
        )
    lat_f, lon_f = _como_float(lat), _como_float(lon)
    if lat_f is None or lon_f is None or not (-90.0 <= lat_f <= 90.0) or not (-180.0 <= lon_f <= 180.0):
        raise GeofenceError("GPS_INVALIDO", "Coordenadas de localização inválidas.", 400)
    if lat_f == 0.0 and lon_f == 0.0:
        # (0, 0) é o valor que muitos clientes devolvem quando o GPS falha.
        raise GeofenceError("GPS_INVALIDO", "Localização inválida. Aguarde o sinal do GPS e tente novamente.", 400)
    return lat_f, lon_f


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * RAIO_TERRA_M * math.asin(min(1.0, math.sqrt(a)))


def validar_proximidade(
    lat: Any,
    lon: Any,
    precisao_m: Any,
    posto_lat: Any,
    posto_lon: Any,
    raio_m: Optional[float] = None,
) -> ResultadoGeofence:
    """
    Levanta GeofenceError se a localização for inválida, imprecisa ou estiver fora do raio.

    A precisão reportada pelo aparelho concede uma folga ao raio (limitada), porque um
    fix com ±40 m pode legitimamente colocar quem está na bomba a 40 m "para fora".
    Sem precisão informada, a folga é zero (regra estrita).
    """
    lat_u, lon_u = validar_coordenadas(lat, lon)

    try:
        lat_p, lon_p = validar_coordenadas(posto_lat, posto_lon)
    except GeofenceError:
        raise GeofenceError(
            "POSTO_SEM_COORDENADAS",
            "Este posto não tem coordenadas válidas cadastradas.",
            500,
        )

    raio_base = raio_m if (raio_m is not None and raio_m > 0) else RAIO_PADRAO_M

    folga = 0.0
    precisao = _como_float(precisao_m)
    if precisao is not None and precisao >= 0:
        if precisao > PRECISAO_MAX_ACEITA_M:
            raise GeofenceError(
                "GPS_IMPRECISO",
                "O sinal de GPS está fraco. Vá para um local aberto e tente novamente.",
                422,
                precisao_m=round(precisao),
                precisao_maxima_m=round(PRECISAO_MAX_ACEITA_M),
            )
        folga = min(precisao, FOLGA_MAX_POR_PRECISAO_M)

    raio_efetivo = raio_base + folga
    distancia = haversine_m(lat_u, lon_u, lat_p, lon_p)

    if distancia > raio_efetivo:
        raise GeofenceError(
            "FORA_DO_RAIO",
            "Você precisa estar no posto para registrar o preço.",
            403,
            distancia_m=round(distancia),
            raio_m=round(raio_base),
        )

    return ResultadoGeofence(distancia_m=distancia, raio_efetivo_m=raio_efetivo)