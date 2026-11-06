"""
Grid geográfico e sincronização de postos em segundo plano.

A listagem continua lendo a tabela postos. A fonte externa é consultada
somente quando uma célula precisa de sincronização.

Compatibilidade com o banco existente:
- A coluna mapbox_id mantém seu nome.
- Identificadores OSM usam osm:node:123, osm:way:123 etc.
- IDs internos, preços e históricos existentes são preservados.

Limites:
- Cache e travas ficam na memória de cada processo.
- Reiniciar o backend perde esse estado.
- Inicialmente, use um único worker no backend.
"""

from __future__ import annotations

import logging
import math
import os
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)

Celula = tuple[int, int]

# Ordem interna: latitude mínima, longitude mínima,
# latitude máxima, longitude máxima.
BBox = tuple[float, float, float, float]

Lugar = dict[str, Any]


@dataclass(frozen=True)
class ResultadoBusca:
    lugares: list[Lugar]
    truncado: bool = False


BuscarFn = Callable[[BBox], ResultadoBusca]


def _env_num(nome: str, padrao: float) -> float:
    try:
        valor = float(os.getenv(nome, ""))
    except ValueError:
        return padrao

    if not math.isfinite(valor) or valor <= 0:
        return padrao

    return valor


PASSO_GRAUS = _env_num("GRID_PASSO_GRAUS", 0.05)
TTL_SEGUNDOS = _env_num("GRID_TTL_DIAS", 7) * 86400

LOCK_SEGUNDOS = 120
BACKOFF_FALHA_SEGUNDOS = 300
PROFUNDIDADE_MAX_SUBDIVISAO = 1

# Uma célula por agendamento evita rajadas de consultas à Overpass.
MAX_CELULAS_POR_REQUISICAO = 1
INTERVALO_AGENDAMENTO_SEGUNDOS = 30

TOLERANCIA_ADOCAO_M = 80.0

_MICRO = 1_000_000
_PASSO_MICRO = max(1, int(round(PASSO_GRAUS * _MICRO)))


# -------------------------------------------------------------------
# Divisão geográfica
# -------------------------------------------------------------------

def celula_de(lat: float, lon: float) -> Celula:
    return (
        int(round(lat * _MICRO)) // _PASSO_MICRO,
        int(round(lon * _MICRO)) // _PASSO_MICRO,
    )


def bbox_da_celula(cel: Celula) -> BBox:
    i, j = cel

    return (
        i * _PASSO_MICRO / _MICRO,
        j * _PASSO_MICRO / _MICRO,
        (i + 1) * _PASSO_MICRO / _MICRO,
        (j + 1) * _PASSO_MICRO / _MICRO,
    )


def _centro(cel: Celula) -> tuple[float, float]:
    sul, oeste, norte, leste = bbox_da_celula(cel)
    return (sul + norte) / 2, (oeste + leste) / 2


def haversine_m(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)

    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1)
        * math.cos(p2)
        * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )

    return 2 * 6_371_008.8 * math.asin(min(1.0, math.sqrt(a)))


def delta_graus(
    lat: float,
    raio_km: float,
) -> tuple[float, float]:
    dlat = raio_km / 111.32

    dlon = raio_km / (
        111.32 * max(0.01, math.cos(math.radians(lat)))
    )

    return dlat, dlon


def celulas_cobrindo(
    lat: float,
    lon: float,
    raio_km: float,
) -> list[Celula]:
    """Retorna células da caixa de busca, ordenadas pela distância."""

    dlat, dlon = delta_graus(lat, raio_km)

    i0, j0 = celula_de(lat - dlat, lon - dlon)
    i1, j1 = celula_de(lat + dlat, lon + dlon)

    celulas = [
        (i, j)
        for i in range(i0, i1 + 1)
        for j in range(j0, j1 + 1)
    ]

    celulas.sort(
        key=lambda cel: haversine_m(lat, lon, *_centro(cel))
    )

    return celulas


# -------------------------------------------------------------------
# Estado em memória
# -------------------------------------------------------------------

@dataclass
class _Estado:
    sincronizado_em: Optional[float] = None
    bloqueado_ate: float = 0.0


_estados: dict[Celula, _Estado] = {}

_trava = threading.Lock()

# Impede múltiplos workers de sincronização dentro do mesmo processo.
_trava_worker = threading.Lock()

_proximo_agendamento = 0.0

_agora: Callable[[], float] = time.monotonic


def _precisa_sincronizar(cel: Celula) -> bool:
    agora = _agora()

    with _trava:
        estado = _estados.get(cel)

        if estado is None:
            return True

        fresca = (
            estado.sincronizado_em is not None
            and agora - estado.sincronizado_em < TTL_SEGUNDOS
        )

        return not fresca and estado.bloqueado_ate <= agora


def _reservar(cel: Celula) -> str:
    agora = _agora()

    with _trava:
        estado = _estados.setdefault(cel, _Estado())

        if (
            estado.sincronizado_em is not None
            and agora - estado.sincronizado_em < TTL_SEGUNDOS
        ):
            return "fresca"

        if estado.bloqueado_ate > agora:
            return "ocupada"

        estado.bloqueado_ate = agora + LOCK_SEGUNDOS

        return "reservada"


def _concluir(cel: Celula, ok: bool) -> None:
    with _trava:
        estado = _estados[cel]

        if ok:
            estado.sincronizado_em = _agora()
            estado.bloqueado_ate = 0.0
        else:
            estado.bloqueado_ate = (
                _agora() + BACKOFF_FALHA_SEGUNDOS
            )


# -------------------------------------------------------------------
# Identificação e associação de postos
# -------------------------------------------------------------------

def _eh_duplicado(exc: Exception) -> bool:
    return (
        bool(getattr(exc, "args", None))
        and exc.args[0] == 1062
    )


def _id_externo(lugar: Lugar) -> str:
    # Mantém compatibilidade com o cliente antigo.
    ident = lugar.get("id_externo") or lugar.get("mapbox_id")

    if (
        not isinstance(ident, str)
        or not ident
        or len(ident) > 100
    ):
        raise ValueError(
            "Identificador externo ausente "
            "ou maior que 100 caracteres."
        )

    return ident


def _normalizar(texto: Any) -> str:
    texto = unicodedata.normalize(
        "NFKD",
        str(texto or "").casefold(),
    )

    sem_acentos = "".join(
        c for c in texto
        if not unicodedata.combining(c)
    )

    return re.sub(
        r"[^a-z0-9]+",
        " ",
        sem_acentos,
    ).strip()


def _mesmo_estabelecimento(
    lugar: Lugar,
    candidato: dict,
    distancia: float,
) -> bool:
    if distancia > TOLERANCIA_ADOCAO_M:
        return False

    tipo_novo = lugar.get("tipo_posto", "Convencional")
    tipo_existente = (
        candidato.get("tipo_posto") or "Convencional"
    )

    if tipo_novo != tipo_existente:
        return False

    nome = _normalizar(lugar.get("nome"))

    if nome in (
        "",
        "posto",
        "posto sem nome",
        "eletroposto sem nome",
    ):
        return False

    if nome != _normalizar(candidato.get("nome")):
        return False

    endereco = _normalizar(lugar.get("endereco"))
    endereco_existente = _normalizar(
        candidato.get("endereco")
    )

    if endereco and endereco_existente:
        return endereco == endereco_existente

    # Sem endereço para comparar, exige maior proximidade.
    return distancia <= 15


def classificar_lugar(
    cursor,
    lugar: Lugar,
    virtuais=None,
) -> dict:
    """Classifica o posto usando apenas consultas SELECT."""
    ident = _id_externo(lugar)
    lat = float(lugar["latitude"])
    lon = float(lugar["longitude"])

    if not (
        math.isfinite(lat)
        and math.isfinite(lon)
        and -90 <= lat <= 90
        and -180 <= lon <= 180
    ):
        raise ValueError("Coordenadas inválidas.")

    cursor.execute(
        "SELECT id FROM postos WHERE mapbox_id = %s",
        (ident,),
    )
    existente = cursor.fetchone()

    item = {
        "id_externo": ident,
        "nome": lugar["nome"],
        "categoria": "existentes",
        "acao": "manter",
        "motivo": "Identificador externo já cadastrado.",
        "posto_id": None,
        "candidatos": [],
    }

    if existente:
        item["posto_id"] = (
            existente["id"]
            if isinstance(existente, dict)
            else existente[0]
        )
        return item

    margem = 0.0012

    cursor.execute(
        """
        SELECT
            id,
            latitude,
            longitude,
            nome,
            endereco,
            tipo_posto,
            mapbox_id
        FROM postos
        WHERE latitude BETWEEN %s AND %s
          AND longitude BETWEEN %s AND %s
        """,
        (
            lat - margem,
            lat + margem,
            lon - margem,
            lon + margem,
        ),
    )

    campos = (
        "id",
        "latitude",
        "longitude",
        "nome",
        "endereco",
        "tipo_posto",
        "mapbox_id",
    )

    linhas = [
        linha
        if isinstance(linha, dict)
        else dict(zip(campos, linha))
        for linha in cursor.fetchall()
    ]

    por_id = {linha["id"]: linha for linha in linhas}

    # Considera também os registros planejados no mesmo lote.
    por_id.update(virtuais or {})

    proximos = []

    for registro in por_id.values():
        distancia = haversine_m(
            lat,
            lon,
            float(registro["latitude"]),
            float(registro["longitude"]),
        )

        mesmo_tipo = (
            registro.get("tipo_posto") or "Convencional"
        ) == lugar.get("tipo_posto", "Convencional")

        if distancia <= TOLERANCIA_ADOCAO_M and mesmo_tipo:
            proximos.append((registro, distancia))

    if not proximos:
        item.update(
            categoria="novos",
            acao="inserir",
            motivo="Nenhum candidato local próximo.",
        )

    elif (
        len(proximos) == 1
        and not proximos[0][0].get("mapbox_id")
        and _mesmo_estabelecimento(lugar, *proximos[0])
    ):
        item["_registro_vinculo"] = proximos[0][0]

        item.update(
            acao="vincular",
            posto_id=proximos[0][0]["id"],
            motivo=(
                "Único posto manual compatível em nome, "
                "tipo e localização/endereço."
            ),
        )

    else:
        # Casos duvidosos ficam para revisão manual.
        item.update(
            categoria="ambiguos",
            acao="ignorar",
            motivo=(
                "Candidatos próximos, conflitantes ou já "
                "vinculados a outro identificador."
            ),
        )

        item["candidatos"] = [
            {
                "id": registro["id"],
                "distancia_m": round(distancia, 1),
            }
            for registro, distancia in proximos
        ]

    return item


def processar_lugares(
    cursor,
    lugares: list[Lugar],
    aplicar=False,
) -> dict:
    """Prévia por padrão; o chamador controla commit e rollback."""
    relatorio = {
        "modo": "aplicar" if aplicar else "dry-run",
        "novos": 0,
        "existentes": 0,
        "ambiguos": 0,
        "inseridos": 0,
        "vinculados": 0,
        "duplicados_na_entrada": 0,
        "itens": [],
    }

    vistos = {}
    virtuais = {}

    for lugar in lugares:
        ident = _id_externo(lugar)

        if ident in vistos:
            if vistos[ident] != lugar:
                raise ValueError(
                    "Identificador externo repetido "
                    "com dados conflitantes."
                )

            relatorio["duplicados_na_entrada"] += 1
            continue

        vistos[ident] = lugar

        item = classificar_lugar(
            cursor,
            lugar,
            virtuais,
        )

        registro_vinculo = item.pop(
            "_registro_vinculo",
            None,
        )

        relatorio[item["categoria"]] += 1
        relatorio["itens"].append(item)

        if item["acao"] == "inserir":
            posto_id = "planejado:" + ident

            if aplicar:
                cursor.execute(
                    """
                    INSERT INTO postos (
                        mapbox_id,
                        nome,
                        endereco,
                        bairro,
                        cidade,
                        uf,
                        latitude,
                        longitude,
                        horario_funcionamento,
                        tipo_posto
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        ident,
                        lugar["nome"],
                        lugar["endereco"],
                        lugar["bairro"],
                        lugar["cidade"],
                        lugar["uf"],
                        lugar["latitude"],
                        lugar["longitude"],
                        lugar.get("horario_funcionamento")
                        or "Horário não informado",
                        lugar.get(
                            "tipo_posto",
                            "Convencional",
                        ),
                    ),
                )

                posto_id = cursor.lastrowid
                item["posto_id"] = posto_id
                relatorio["inseridos"] += 1

            virtuais[posto_id] = dict(
                lugar,
                id=posto_id,
                mapbox_id=ident,
            )

        elif item["acao"] == "vincular":
            if aplicar:
                # Atualiza apenas o identificador externo.
                cursor.execute(
                    """
                    UPDATE postos
                    SET mapbox_id = %s
                    WHERE id = %s
                      AND mapbox_id IS NULL
                    """,
                    (ident, item["posto_id"]),
                )

                if cursor.rowcount != 1:
                    raise RuntimeError(
                        "Vínculo mudou durante a importação; "
                        "execute nova prévia."
                    )

                relatorio["vinculados"] += 1

            virtuais[item["posto_id"]] = dict(
                registro_vinculo,
                mapbox_id=ident,
            )

        elif item["categoria"] == "ambiguos":
            log.warning(
                "Posto externo ambíguo: não será associado "
                "ou inserido automaticamente."
            )

    return relatorio


def _gravar_lugares(cursor, lugares: list[Lugar]) -> int:
    """Mantém compatibilidade com o sincronizador legado."""
    return processar_lugares(
        cursor,
        lugares,
        aplicar=True,
    )["inseridos"]


# -------------------------------------------------------------------
# Busca externa
# -------------------------------------------------------------------

def _dividir_bbox(bbox: BBox) -> list[BBox]:
    sul, oeste, norte, leste = bbox

    meio_lat = (sul + norte) / 2
    meio_lon = (oeste + leste) / 2

    return [
        (sul, oeste, meio_lat, meio_lon),
        (sul, meio_lon, meio_lat, leste),
        (meio_lat, oeste, norte, meio_lon),
        (meio_lat, meio_lon, norte, leste),
    ]


def _buscar_com_subdivisao(
    buscar: BuscarFn,
    bbox: BBox,
    profundidade: int = 0,
) -> list[Lugar]:
    resultado = buscar(bbox)

    if (
        resultado.truncado
        and profundidade < PROFUNDIDADE_MAX_SUBDIVISAO
    ):
        unicos: dict[str, Lugar] = {}

        for quadrante in _dividir_bbox(bbox):
            lugares = _buscar_com_subdivisao(
                buscar,
                quadrante,
                profundidade + 1,
            )

            for lugar in lugares:
                unicos[_id_externo(lugar)] = lugar

        return list(unicos.values())

    return resultado.lugares


# -------------------------------------------------------------------
# Sincronização
# -------------------------------------------------------------------

def sincronizar_celula(
    get_conn: Callable[[], Any],
    cel: Celula,
    buscar: BuscarFn,
) -> str:
    """
    Retorna: fresca, ocupada, sincronizada ou falhou.

    A consulta externa acontece antes de abrir conexão com o banco.
    """

    status = _reservar(cel)

    if status != "reservada":
        return status

    try:
        lugares = _buscar_com_subdivisao(
            buscar,
            bbox_da_celula(cel),
        )

        conn = get_conn()

        try:
            with conn.cursor() as cursor:
                novos = _gravar_lugares(cursor, lugares)

            conn.commit()

        except Exception:
            conn.rollback()
            raise

        finally:
            conn.close()

        _concluir(cel, True)

        log.info(
            "Célula %s sincronizada: %d encontrados, %d novos",
            cel,
            len(lugares),
            novos,
        )

        return "sincronizada"

    except Exception:
        log.exception(
            "Falha ao sincronizar a célula %s "
            "(nova tentativa em %ds)",
            cel,
            BACKOFF_FALHA_SEGUNDOS,
        )

        _concluir(cel, False)

        return "falhou"


def garantir_cobertura(
    get_conn: Callable[[], Any],
    lat: float,
    lon: float,
    raio_km: float,
    buscar: BuscarFn,
) -> dict[Celula, str]:
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


def garantir_cobertura_async(
    get_conn: Callable[[], Any],
    lat: float,
    lon: float,
    raio_km: float,
    buscar: BuscarFn,
) -> bool:
    """
    Agenda uma sincronização sem bloquear a requisição.

    Considera todas as células pendentes, mesmo quando as primeiras
    já estão sincronizadas.
    """

    global _proximo_agendamento

    if not _trava_worker.acquire(blocking=False):
        return False

    entregue = False

    try:
        if _agora() < _proximo_agendamento:
            return False

        precisa_buscar = any(
            _precisa_sincronizar(cel)
            for cel in celulas_cobrindo(lat, lon, raio_km)
        )

        if not precisa_buscar:
            return False

        def executar():
            global _proximo_agendamento

            try:
                garantir_cobertura(
                    get_conn,
                    lat,
                    lon,
                    raio_km,
                    buscar,
                )

            finally:
                _proximo_agendamento = (
                    _agora() + INTERVALO_AGENDAMENTO_SEGUNDOS
                )

                _trava_worker.release()

        threading.Thread(
            target=executar,
            daemon=True,
            name="sync-postos-osm",
        ).start()

        entregue = True

    finally:
        if not entregue:
            _trava_worker.release()

    return True