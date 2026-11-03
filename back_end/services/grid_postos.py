"""
Grid geográfico + sincronização de postos com o Mapbox, fora do caminho da requisição.

A rota GET /postos lê SEMPRE da tabela `postos`. O Mapbox só é consultado, em segundo plano,
quando a célula do grid (~5,5 km) ainda não foi sincronizada ou venceu o TTL. Logo, as chamadas
ao Mapbox dependem de (células x TTL) e não do número de utilizadores nem de aberturas do app.

Sem alterações no banco: o estado da sincronização (quando cada célula foi sincronizada) fica
em MEMÓRIA do processo. Consequências assumidas:
  - ao reiniciar o servidor (ou acordar o Render), cada célula é sincronizada de novo uma vez;
  - com N workers, cada um sincroniza as suas células (no máximo N chamadas por célula por TTL);
  - dentro do mesmo processo há trava: duas requisições nunca sincronizam a mesma célula juntas.
Se isto virar problema, o estado pode migrar para uma tabela (exigiria alterar o banco).

Postos cadastrados à mão (mapbox_id NULL) a <= 80 m de um resultado do Mapbox são "adotados":
só recebem o mapbox_id, preservando id, nome e todo o histórico de preços.

Aceita cursor de tupla ou DictCursor (o projeto usa DictCursor).
"""
from __future__ import annotations

import logging
import math
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)

Celula = tuple[int, int]
BBox = tuple[float, float, float, float]  # (min_lat, min_lon, max_lat, max_lon)
Lugar = dict[str, Any]


@dataclass(frozen=True)
class ResultadoBusca:
    lugares: list[Lugar]
    #: True se o Mapbox devolveu o teto de resultados (pode haver mais postos na área).
    truncado: bool = False


BuscarFn = Callable[[BBox], ResultadoBusca]


def _env_num(nome: str, padrao: float) -> float:
    try:
        v = float(os.getenv(nome, ""))
    except ValueError:
        return padrao
    return v if math.isfinite(v) and v > 0 else padrao


PASSO_GRAUS = _env_num("GRID_PASSO_GRAUS", 0.05)          # ~5,5 km de latitude
TTL_SEGUNDOS = _env_num("GRID_TTL_DIAS", 7) * 86400
LOCK_SEGUNDOS = 120                                        # tempo máximo de uma sincronização
BACKOFF_FALHA_SEGUNDOS = 300                               # após falha, não insiste durante 5 min
PROFUNDIDADE_MAX_SUBDIVISAO = 1                            # 1 chamada + até 4 quadrantes
MAX_CELULAS_POR_REQUISICAO = 2
TOLERANCIA_ADOCAO_M = 80.0

_MICRO = 1_000_000
_PASSO_MICRO = max(1, int(round(PASSO_GRAUS * _MICRO)))


# --------------------------------------------------------------------------- grid
def celula_de(lat: float, lon: float) -> Celula:
    """Índice inteiro da célula. Aritmética inteira evita erros de fronteira de float."""
    return (int(round(lat * _MICRO)) // _PASSO_MICRO, int(round(lon * _MICRO)) // _PASSO_MICRO)


def bbox_da_celula(cel: Celula) -> BBox:
    i, j = cel
    return (
        i * _PASSO_MICRO / _MICRO,
        j * _PASSO_MICRO / _MICRO,
        (i + 1) * _PASSO_MICRO / _MICRO,
        (j + 1) * _PASSO_MICRO / _MICRO,
    )


def _centro(cel: Celula) -> tuple[float, float]:
    a, b, c, d = bbox_da_celula(cel)
    return (a + c) / 2, (b + d) / 2


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6_371_008.8 * math.asin(min(1.0, math.sqrt(a)))


def delta_graus(lat: float, raio_km: float) -> tuple[float, float]:
    """Metade da caixa (em graus de lat/lon) que contém um círculo de raio_km."""
    dlat = raio_km / 111.32
    dlon = raio_km / (111.32 * max(0.01, math.cos(math.radians(lat))))
    return dlat, dlon


def celulas_cobrindo(lat: float, lon: float, raio_km: float) -> list[Celula]:
    """Células tocadas pelo círculo de busca, da mais próxima do utilizador para a mais distante."""
    dlat, dlon = delta_graus(lat, raio_km)
    i0, j0 = celula_de(lat - dlat, lon - dlon)
    i1, j1 = celula_de(lat + dlat, lon + dlon)
    celulas = [(i, j) for i in range(i0, i1 + 1) for j in range(j0, j1 + 1)]
    celulas.sort(key=lambda c: haversine_m(lat, lon, *_centro(c)))
    return celulas


# --------------------------------------------------------------------------- estado em memória
@dataclass
class _Estado:
    sincronizado_em: Optional[float] = None
    bloqueado_ate: float = 0.0


_estados: dict[Celula, _Estado] = {}
_trava = threading.Lock()
_agora: Callable[[], float] = time.monotonic  # substituível em testes


def _precisa_sincronizar(cel: Celula) -> bool:
    agora = _agora()
    with _trava:
        e = _estados.get(cel)
        if e is None:
            return True
        fresca = e.sincronizado_em is not None and agora - e.sincronizado_em < TTL_SEGUNDOS
        return not fresca and e.bloqueado_ate <= agora


def _reservar(cel: Celula) -> str:
    agora = _agora()
    with _trava:
        e = _estados.setdefault(cel, _Estado())
        if e.sincronizado_em is not None and agora - e.sincronizado_em < TTL_SEGUNDOS:
            return "fresca"
        if e.bloqueado_ate > agora:
            return "ocupada"
        e.bloqueado_ate = agora + LOCK_SEGUNDOS
        return "reservada"


def _concluir(cel: Celula, ok: bool) -> None:
    with _trava:
        e = _estados[cel]
        if ok:
            e.sincronizado_em, e.bloqueado_ate = _agora(), 0.0
        else:
            e.bloqueado_ate = _agora() + BACKOFF_FALHA_SEGUNDOS


# --------------------------------------------------------------------------- banco
def _col(linha: Any, indice: int, nome: str) -> Any:
    return linha[nome] if isinstance(linha, dict) else linha[indice]


def _eh_duplicado(exc: Exception) -> bool:
    return bool(getattr(exc, "args", None)) and exc.args[0] == 1062  # MySQL: duplicate entry


def _gravar_lugares(cursor, lugares: list[Lugar]) -> int:
    """Insere postos novos sem sobrescrever nada. Devolve quantos foram inseridos."""
    inseridos = 0
    margem = 0.0012  # ~130 m de pré-filtro em graus; o corte fino é por haversine
    for lugar in lugares:
        mid, lat, lon = lugar["mapbox_id"], lugar["latitude"], lugar["longitude"]

        cursor.execute("SELECT id FROM postos WHERE mapbox_id = %s", (mid,))
        if cursor.fetchone():
            continue

        cursor.execute(
            "SELECT id, latitude, longitude FROM postos "
            "WHERE mapbox_id IS NULL AND latitude BETWEEN %s AND %s AND longitude BETWEEN %s AND %s",
            (lat - margem, lat + margem, lon - margem, lon + margem),
        )
        candidatos = []
        for r in cursor.fetchall():
            d = haversine_m(lat, lon, float(_col(r, 1, "latitude")), float(_col(r, 2, "longitude")))
            if d <= TOLERANCIA_ADOCAO_M:
                candidatos.append((d, _col(r, 0, "id")))
        if candidatos:
            candidatos.sort()
            cursor.execute("UPDATE postos SET mapbox_id = %s WHERE id = %s", (mid, candidatos[0][1]))
            continue

        try:
            cursor.execute(
                "INSERT INTO postos (mapbox_id, nome, endereco, bairro, cidade, uf, latitude, longitude, horario_funcionamento) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '24 Horas')",
                (mid, lugar["nome"], lugar["endereco"], lugar["bairro"], lugar["cidade"], lugar["uf"], lat, lon),
            )
            inseridos += 1
        except Exception as exc:
            if not _eh_duplicado(exc):  # outro worker inseriu o mesmo posto agora: ignora
                raise
    return inseridos


def _dividir_bbox(b: BBox) -> list[BBox]:
    a, bb, c, d = b
    ma, mb = (a + c) / 2, (bb + d) / 2
    return [(a, bb, ma, mb), (a, mb, ma, d), (ma, bb, c, mb), (ma, mb, c, d)]


def _buscar_com_subdivisao(buscar: BuscarFn, bbox: BBox, profundidade: int = 0) -> list[Lugar]:
    """Se o Mapbox devolver o teto de resultados, há postos cortados: divide em quadrantes."""
    resultado = buscar(bbox)
    if resultado.truncado and profundidade < PROFUNDIDADE_MAX_SUBDIVISAO:
        unicos: dict[str, Lugar] = {}
        for quadrante in _dividir_bbox(bbox):
            for lugar in _buscar_com_subdivisao(buscar, quadrante, profundidade + 1):
                unicos[lugar["mapbox_id"]] = lugar
        return list(unicos.values())
    return resultado.lugares


# --------------------------------------------------------------------------- sincronização
def sincronizar_celula(get_conn: Callable[[], Any], cel: Celula, buscar: BuscarFn) -> str:
    """
    "fresca" | "sincronizada" | "ocupada" | "falhou". Nunca levanta exceção.
    A chamada HTTP acontece SEM conexão de banco aberta: só se abre uma para gravar.
    """
    status = _reservar(cel)
    if status != "reservada":
        return status
    try:
        lugares = _buscar_com_subdivisao(buscar, bbox_da_celula(cel))
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                novos = _gravar_lugares(cur, lugares)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        _concluir(cel, True)
        log.info("Célula %s sincronizada: %d encontrados, %d novos", cel, len(lugares), novos)
        return "sincronizada"
    except Exception:
        log.exception("Falha ao sincronizar a célula %s (nova tentativa em %ds)", cel, BACKOFF_FALHA_SEGUNDOS)
        _concluir(cel, False)
        return "falhou"


def garantir_cobertura(get_conn: Callable[[], Any], lat: float, lon: float, raio_km: float, buscar: BuscarFn) -> dict[Celula, str]:
    """Sincroniza (no máximo MAX_CELULAS_POR_REQUISICAO, as mais próximas primeiro) as células do raio."""
    resultado: dict[Celula, str] = {}
    chamadas = 0
    for cel in celulas_cobrindo(lat, lon, raio_km):
        if chamadas >= MAX_CELULAS_POR_REQUISICAO:
            break
        status = sincronizar_celula(get_conn, cel, buscar)
        resultado[cel] = status
        if status in ("sincronizada", "falhou"):
            chamadas += 1
    return resultado


def garantir_cobertura_async(get_conn: Callable[[], Any], lat: float, lon: float, raio_km: float, buscar: BuscarFn) -> bool:
    """
    Dispara a sincronização numa thread e volta na hora (a requisição não espera o Mapbox).
    Só cria a thread se alguma célula realmente precisar. Devolve True se disparou.
    """
    if not any(_precisa_sincronizar(c) for c in celulas_cobrindo(lat, lon, raio_km)[:MAX_CELULAS_POR_REQUISICAO]):
        return False
    threading.Thread(
        target=garantir_cobertura, args=(get_conn, lat, lon, raio_km, buscar), daemon=True, name="sync-postos"
    ).start()
    return True