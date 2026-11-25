"""Consulta pública em lote de ofertas e preços."""

from __future__ import annotations

import math
import unicodedata
from datetime import date, datetime

from services.grid_postos import delta_graus


CATALOGO = {
    "gasolina_comum": ("Gasolina Comum", "L"),
    "gasolina_aditivada": ("Gasolina Aditivada", "L"),
    "etanol": ("Etanol", "L"),
    "diesel": ("Diesel", "L"),
    "gnv": ("GNV", "m³"),
    "recarga_eletrica": ("Recarga Elétrica", "kWh"),
}

NOMES = {
    nome: codigo
    for codigo, (nome, _) in CATALOGO.items()
}
NOMES["Recarga Elétrica (kWh)"] = "recarga_eletrica"


def normalizar_marca(valor):
    if not isinstance(valor, str) or not valor.strip():
        return None

    nome = valor.strip()

    chave = "".join(
        caractere
        for caractere in unicodedata.normalize(
            "NFKD", nome.casefold()
        )
        if not unicodedata.combining(caractere)
    )

    return {
        "br": "Petrobras",
        "petrobras": "Petrobras",
        "shell": "Shell",
        "ipiranga": "Ipiranga",
        "ypiranga": "Ipiranga",
        "ale": "Ale",
        "texaco": "Texaco",
        "esso": "Esso",
    }.get(chave, nome)


def validar_filtros(args):
    selecionados = []
    bruto = args.get("combustiveis", "")

    if len(bruto) > 200:
        raise ValueError(
            "Lista de combustíveis inválida."
        )

    if bruto:
        for codigo in bruto.split(","):
            codigo = codigo.strip()

            if codigo not in CATALOGO:
                raise ValueError(
                    "Combustível desconhecido. "
                    "Use os códigos do catálogo."
                )

            if codigo not in selecionados:
                selecionados.append(codigo)

    referencia = args.get("referencia") or (
        selecionados[0]
        if selecionados
        else "gasolina_comum"
    )

    if (
        referencia not in CATALOGO
        or (
            selecionados
            and referencia not in selecionados
        )
    ):
        raise ValueError(
            "A referência deve ser um "
            "dos combustíveis selecionados."
        )

    marca = args.get("marca", "").strip()

    if (
        len(marca) > 120
        or any(ord(c) < 32 for c in marca)
    ):
        raise ValueError("Marca inválida.")

    ordem = args.get("ordenar", "distancia")

    if ordem not in ("distancia", "preco"):
        raise ValueError("Ordenação inválida.")

    return (
        selecionados,
        referencia,
        normalizar_marca(marca),
        ordem,
    )


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None

    try:
        numero = float(valor)
    except (ValueError, TypeError, OverflowError):
        return None

    return numero if math.isfinite(numero) else None


def _estado(valor):
    if valor in (0, "0", False):
        return False
    if valor in (1, "1", True):
        return True
    return None


def _data(valor):
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    return None


def consultar_catalogo(
    conn,
    centro,
    raio_km,
    limite,
    filtros,
    distancia_m,
    *,
    incluir_estimativas=False,
):
    selecionados, referencia, marca, ordem = filtros
    parametros = []
    where = ""

    if centro:
        dlat, dlon = delta_graus(
            centro[0], raio_km
        )

        where = (
            "WHERE p.latitude BETWEEN %s AND %s "
            "AND p.longitude BETWEEN %s AND %s"
        )

        parametros.extend((
            centro[0] - dlat,
            centro[0] + dlat,
            centro[1] - dlon,
            centro[1] + dlon,
        ))

    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                p.id, p.nome, p.bairro, p.endereco,
                p.latitude, p.longitude,
                p.horario_funcionamento,
                p.tipo_posto, p.marca, p.marca_origem
            FROM postos p
            """
            + where
            + " ORDER BY p.id LIMIT %s",
            [*parametros, limite],
        )

        postos = cursor.fetchall()
        validos = []

        for posto in postos:
            lat = _numero(posto.get("latitude"))
            lon = _numero(posto.get("longitude"))

            if (
                lat is None
                or lon is None
                or not (
                    -90 <= lat <= 90
                    and -180 <= lon <= 180
                )
            ):
                continue

            posto = dict(
                posto,
                latitude=lat,
                longitude=lon,
            )

            if centro:
                distancia = distancia_m(
                    *centro, lat, lon
                )

                if distancia > raio_km * 1000:
                    continue

                posto["distancia_m"] = round(
                    distancia
                )

            validos.append(posto)

        if not validos:
            return []

        ids = [
            posto["id"]
            for posto in validos
        ]

        placeholders = ",".join(
            ["%s"] * len(ids)
        )

        cursor.execute(
            """
            SELECT
                posto_id,
                combustivel_codigo,
                disponivel_manual,
                disponivel_osm
            FROM postos_combustiveis
            WHERE posto_id IN (
            """
            + placeholders
            + ")",
            ids,
        )

        ofertas = {
            (
                row["posto_id"],
                row["combustivel_codigo"],
            ): row
            for row in cursor.fetchall()
        }

        cursor.execute(
            """
            SELECT
                r.id, r.posto_id, r.tipo_combustivel,
                r.preco, r.data_registro,
                u.nome AS autor_nome
            FROM registos_preco r
            LEFT JOIN usuarios u
              ON u.id = r.usuario_id
            WHERE r.posto_id IN (
            """
            + placeholders
            + """
            )
              AND r.id = (
                SELECT r2.id
                FROM registos_preco r2
                WHERE r2.posto_id = r.posto_id
                  AND r2.tipo_combustivel = r.tipo_combustivel
                ORDER BY
                    r2.data_registro DESC,
                    r2.id DESC
                LIMIT 1
              )
            ORDER BY r.data_registro DESC, r.id DESC
            """,
            ids,
        )

        precos = {}

        for registro in cursor.fetchall():
            codigo = NOMES.get(
                registro["tipo_combustivel"]
            )

            chave = (
                registro["posto_id"],
                codigo,
            )

            valor = _numero(
                registro.get("preco")
            )

            if (
                codigo
                and chave not in precos
                and valor is not None
                and valor > 0
            ):
                precos[chave] = dict(
                    registro,
                    preco=valor,
                )

        referencias = {}

        if incluir_estimativas:
            from services.referencias_medias import consultar_referencias

            referencias = consultar_referencias(
                cursor, ids
            )

    resultado = []

    for posto in validos:
        posto["marca"] = normalizar_marca(
            posto.get("marca")
        )

        if marca == "nao_informada":
            if posto["marca"] is not None:
                continue

        elif marca:
            if (
                posto["marca"] or ""
            ).casefold() != marca.casefold():
                continue

        produtos = []

        for codigo, (nome, unidade) in CATALOGO.items():
            oferta = ofertas.get(
                (posto["id"], codigo),
                {},
            )

            manual = _estado(
                oferta.get("disponivel_manual")
            )
            osm = _estado(
                oferta.get("disponivel_osm")
            )

            disponivel = (
                manual
                if manual is not None
                else osm
            )

            registro = precos.get(
                (posto["id"], codigo),
                {},
            )

            estimativa = None

            if (
                not registro
                and posto.get("tipo_posto")
                == "Convencional"
                and disponivel is not False
            ):
                media = referencias.get(
                    (posto["id"], codigo)
                )

                if media:
                    registro = {
                        "preco": float(media["preco"])
                    }
                    estimativa = media["estimativa"]

            produtos.append({
                "codigo": codigo,
                "nome": nome,
                "unidade": unidade,
                "disponivel": disponivel,
                "origem": (
                    "manual"
                    if manual is not None
                    else "osm"
                    if osm is not None
                    else None
                ),
                "preco": registro.get("preco"),
                "atualizado_em": _data(
                    registro.get("data_registro")
                ),
                "autor_nome": registro.get("autor_nome"),
                "registo_id": registro.get("id"),
                **(
                    {"estimativa": estimativa}
                    if estimativa is not None
                    else {}
                ),
            })

        if selecionados and not any(
            produto["codigo"] in selecionados
            and produto["disponivel"] is True
            for produto in produtos
        ):
            continue

        ref = next(
            produto
            for produto in produtos
            if produto["codigo"] == referencia
        )

        gasolina = next(
            produto
            for produto in produtos
            if produto["codigo"] == "gasolina_comum"
        )

        pode_exibir_referencia = (
            ref["disponivel"] is not False
            and (
                not selecionados
                or ref["disponivel"] is True
            )
        )

        posto.update({
            "combustiveis": produtos,
            "combustivel_referencia": referencia,
            "preco_referencia": (
                ref["preco"]
                if pode_exibir_referencia
                else None
            ),
            "unidade_referencia": ref["unidade"],
            "data_atualizacao": ref["atualizado_em"],
            "autor_referencia": ref["autor_nome"],
            "preco_gasolina": gasolina["preco"],
            "horario_funcionamento": (
                posto.get("horario_funcionamento")
                or "Horário não informado"
            ),
        })

        resultado.append(posto)

    if ordem == "preco":
        resultado.sort(
            key=lambda posto: (
                posto["preco_referencia"] is None,
                bool(
                    next(
                        oferta
                        for oferta in posto["combustiveis"]
                        if oferta["codigo"] == referencia
                    ).get("estimativa")
                ),
                posto["preco_referencia"] or 0,
                posto.get("distancia_m", math.inf),
                posto["id"],
            )
        )

    elif centro:
        resultado.sort(
            key=lambda posto: (
                posto["distancia_m"],
                posto["id"],
            )
        )

    return resultado