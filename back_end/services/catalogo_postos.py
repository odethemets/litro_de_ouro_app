"""Consulta pública em lote: oferta, preço e origem são informações distintas."""
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
NOMES = {nome: codigo for codigo, (nome, _) in CATALOGO.items()}
NOMES["Recarga Elétrica (kWh)"] = "recarga_eletrica"


# Unifica apelidos de bandeiras; ajustar aqui quando aparecer uma nova grafia.
def normalizar_marca(valor):
    if not isinstance(valor, str) or not valor.strip():
        return None
    nome = valor.strip()
    chave = "".join(c for c in unicodedata.normalize("NFKD", nome.casefold()) if not unicodedata.combining(c))
    return {
        "br": "Petrobras", "petrobras": "Petrobras", "shell": "Shell",
        "ipiranga": "Ipiranga", "ypiranga": "Ipiranga", "ale": "Ale",
        "texaco": "Texaco", "esso": "Esso",
    }.get(chave, nome)


# Converte os parâmetros da consulta em seleção, referência, bandeira e ordenação.
def validar_filtros(args):
    selecionados = []
    bruto = args.get("combustiveis", "")
    if len(bruto) > 200:
        raise ValueError("Lista de combustíveis inválida.")
    if bruto:
        for codigo in bruto.split(","):
            codigo = codigo.strip()
            if codigo not in CATALOGO:
                raise ValueError("Combustível desconhecido. Use os códigos do catálogo.")
            if codigo not in selecionados:
                selecionados.append(codigo)
    referencia = args.get("referencia") or (selecionados[0] if selecionados else "gasolina_comum")
    if referencia not in CATALOGO or (selecionados and referencia not in selecionados):
        raise ValueError("A referência deve ser um dos combustíveis selecionados.")
    marca = args.get("marca", "").strip()
    if len(marca) > 120 or any(ord(c) < 32 for c in marca):
        raise ValueError("Marca inválida.")
    ordem = args.get("ordenar", "distancia")
    if ordem not in ("distancia", "preco"):
        raise ValueError("Ordenação inválida.")
    return selecionados, referencia, normalizar_marca(marca), ordem


# Converte valores do banco em números finitos, preservando ausência como None.
def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (ValueError, TypeError, OverflowError):
        return None
    return numero if math.isfinite(numero) else None


# Traduz flags SQL sem confundir oferta desconhecida com indisponibilidade.
def _estado(valor):
    if valor in (0, "0", False):
        return False
    if valor in (1, "1", True):
        return True
    return None


# Serializa datas do banco em ISO; não atribui um fuso que não veio no valor.
def _data(valor):
    return valor.isoformat() if isinstance(valor, (datetime, date)) else None


# Monta postos/ofertas/preços em lote; revisar aqui filtros e preço de referência.
def consultar_catalogo(conn, centro, raio_km, limite, filtros, distancia_m):
    selecionados, referencia, marca, ordem = filtros
    parametros = []
    where = ""
    if centro:
        dlat, dlon = delta_graus(centro[0], raio_km)
        where = "WHERE p.latitude BETWEEN %s AND %s AND p.longitude BETWEEN %s AND %s"
        parametros.extend((centro[0]-dlat, centro[0]+dlat, centro[1]-dlon, centro[1]+dlon))
    # Somente where fixo e placeholders gerados internamente são interpolados.
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT p.id, p.nome, p.bairro, p.endereco, p.latitude, p.longitude,
                   p.horario_funcionamento, p.tipo_posto, p.marca, p.marca_origem
            FROM postos p """ + where + " ORDER BY p.id LIMIT %s", [*parametros, limite])
        postos = cursor.fetchall()
        validos = []
        for posto in postos:
            lat, lon = _numero(posto.get("latitude")), _numero(posto.get("longitude"))
            if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            posto = dict(posto, latitude=lat, longitude=lon)
            if centro:
                distancia = distancia_m(*centro, lat, lon)
                if distancia > raio_km * 1000:
                    continue
                posto["distancia_m"] = round(distancia)
            validos.append(posto)
        if not validos:
            return []
        ids = [p["id"] for p in validos]
        placeholders = ",".join(["%s"] * len(ids))
        cursor.execute("""
            SELECT posto_id, combustivel_codigo, disponivel_manual, disponivel_osm
            FROM postos_combustiveis WHERE posto_id IN (""" + placeholders + ")", ids)
        ofertas = {(r["posto_id"], r["combustivel_codigo"]): r for r in cursor.fetchall()}
        cursor.execute("""
            SELECT r.id, r.posto_id, r.tipo_combustivel, r.preco, r.data_registro,
                   u.nome AS autor_nome
            FROM registos_preco r LEFT JOIN usuarios u ON u.id = r.usuario_id
            WHERE r.posto_id IN (""" + placeholders + """)
              AND r.id = (
                  SELECT r2.id FROM registos_preco r2
                  WHERE r2.posto_id = r.posto_id AND r2.tipo_combustivel = r.tipo_combustivel
                  ORDER BY r2.data_registro DESC, r2.id DESC LIMIT 1
              )
            ORDER BY r.data_registro DESC, r.id DESC
        """, ids)
        precos = {}
        for registro in cursor.fetchall():
            codigo = NOMES.get(registro["tipo_combustivel"])
            chave = (registro["posto_id"], codigo)
            valor = _numero(registro.get("preco"))
            if codigo and chave not in precos and valor is not None and valor > 0:
                precos[chave] = dict(registro, preco=valor)

    resultado = []
    for posto in validos:
        posto["marca"] = normalizar_marca(posto.get("marca"))
        if marca == "nao_informada":
            if posto["marca"] is not None:
                continue
        elif marca and (posto["marca"] or "").casefold() != marca.casefold():
            continue
        produtos = []
        for codigo, (nome, unidade) in CATALOGO.items():
            oferta = ofertas.get((posto["id"], codigo), {})
            manual, osm = _estado(oferta.get("disponivel_manual")), _estado(oferta.get("disponivel_osm"))
            disponivel = manual if manual is not None else osm
            registro = precos.get((posto["id"], codigo), {})
            produtos.append({
                "codigo": codigo, "nome": nome, "unidade": unidade,
                "disponivel": disponivel,
                "origem": "manual" if manual is not None else "osm" if osm is not None else None,
                "preco": registro.get("preco"), "atualizado_em": _data(registro.get("data_registro")),
                "autor_nome": registro.get("autor_nome"),
                "registo_id": registro.get("id"),
            })
        if selecionados and not any(p["codigo"] in selecionados and p["disponivel"] is True for p in produtos):
            continue
        ref = next(p for p in produtos if p["codigo"] == referencia)
        gasolina = next(p for p in produtos if p["codigo"] == "gasolina_comum")
        posto.update({
            "combustiveis": produtos, "combustivel_referencia": referencia,
            "preco_referencia": ref["preco"] if ref["disponivel"] is not False and (not selecionados or ref["disponivel"] is True) else None,
            "unidade_referencia": ref["unidade"], "data_atualizacao": ref["atualizado_em"],
            "autor_referencia": ref["autor_nome"],
            "preco_gasolina": gasolina["preco"],
            "horario_funcionamento": posto.get("horario_funcionamento") or "Horário não informado",
        })
        resultado.append(posto)
    if ordem == "preco":
        resultado.sort(key=lambda p: (p["preco_referencia"] is None, p["preco_referencia"] or 0, p.get("distancia_m", math.inf), p["id"]))
    elif centro:
        resultado.sort(key=lambda p: (p["distancia_m"], p["id"]))
    return resultado
