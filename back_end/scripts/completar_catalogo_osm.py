"""Completa metadados ausentes do catalogo local. Previa por padrao, sem rede."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import ssl
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services import osm_service as osm
from services.catalogo_postos import normalizar_marca
from services.database import get_db_connection, load_config

BANCO = "litro_de_ouro_dev"
LOCK = "ldo_completar_catalogo_osm_v1"
FIXTURES = {
    1: ("[TESTE] Posto Docker A", -7.1100, -34.8600, "Convencional", ("gasolina_comum", "diesel")),
    2: ("[TESTE] Posto Docker B", -7.1140, -34.8640, "Convencional", ("gasolina_comum",)),
    3: ("[TESTE] Eletroposto Docker", -7.1080, -34.8560, "Eletroposto", ("recarga_eletrica",)),
    4: ("[TESTE] Posto sem preco", -7.1120, -34.8580, "Convencional", ("gasolina_comum",)),
}
ALIASES = {
    "gasolina_comum": ("fuel:gasolina_comum",),
    "gasolina_aditivada": ("fuel:gasolina_aditivada",),
    "etanol": ("fuel:ethanol", "fuel:etanol_comum"),
    "gnv": ("fuel:cng",),
    "recarga_eletrica": ("fuel:electricity",),
}
DIESEL_SUBTIPOS = ("fuel:diesel_s10", "fuel:diesel_s500", "fuel:diesel:s10", "fuel:diesel:s500")


class ErroCatalogo(ValueError):
    """Mensagem controlada, sem detalhes de conexao ou mensagens do driver."""


def ofertas_explicitas(tags):
    """Omissao/valor ambiguo nao significa ausencia. Gasoline nao distingue aditivo."""
    ofertas, avisos = {}, []
    conhecidos = {k for grupo in ALIASES.values() for k in grupo} | {"fuel:diesel", *DIESEL_SUBTIPOS}

    def valores(chaves):
        encontrados = []
        for chave in chaves:
            if chave not in tags:
                continue
            valor = tags[chave]
            valor = valor.strip().lower() if isinstance(valor, str) else None
            if valor not in ("yes", "no"):
                avisos.append("Valor nao interpretado: " + chave)
                return None
            encontrados.append(valor == "yes")
        return encontrados

    for codigo, chaves in ALIASES.items():
        estados = valores(chaves)
        if codigo == "recarga_eletrica" and tags.get("amenity") == "charging_station":
            estados = None if estados is None else [*estados, True]
        if estados is None or not estados:
            continue
        if len(set(estados)) > 1:
            avisos.append("Tags conflitantes para " + codigo)
        else:
            ofertas[codigo] = int(estados[0])

    principal, subtipos = valores(("fuel:diesel",)), valores(DIESEL_SUBTIPOS)
    if principal is not None and subtipos is not None:
        if principal == [False] and any(subtipos):
            avisos.append("Tags conflitantes para diesel")
        elif principal:
            ofertas["diesel"] = int(principal[0])
        elif any(subtipos):
            ofertas["diesel"] = 1
        # Subtipos negativos isolados nao negam toda a categoria diesel.
    avisos.extend("Tag sem correspondencia segura: " + k for k in sorted(tags)
                  if k.startswith("fuel:") and k not in conhecidos)
    return ofertas, avisos


def carregar_fonte(caminho, sha256=None):
    with Path(caminho).open("rb") as stream:
        bruto = stream.read(16 * 1024 * 1024 + 1)
    if len(bruto) > 16 * 1024 * 1024:
        raise ErroCatalogo("Arquivo excede 16 MiB.")
    digest = hashlib.sha256(bruto).hexdigest()
    if sha256 is not None and digest != sha256.lower():
        raise ErroCatalogo("SHA256 diferente do arquivo previsto; nenhuma escrita autorizada.")
    corpo = json.loads(bruto)
    municipio = osm.validar_municipio(corpo)
    try:
        data = datetime.fromisoformat(corpo["osm3s"]["timestamp_osm_base"].replace("Z", "+00:00"))
        if data.tzinfo is None:
            raise ValueError
        data = data.astimezone(timezone.utc).replace(tzinfo=None)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ErroCatalogo("Data UTC da base OSM ausente ou invalida.") from None
    resultado, _ = osm.converter_resposta(corpo)
    validos = {lugar["id_externo"] for lugar in resultado.lugares}
    elementos, duplicados = {}, {}
    for e in corpo["elements"]:
        if not isinstance(e, dict):
            continue
        ident = f"osm:{e.get('type')}:{e.get('id')}"
        if ident not in validos:
            continue
        if ident in duplicados and duplicados[ident] != e:
            raise ErroCatalogo("Identificador OSM repetido com dados conflitantes.")
        duplicados[ident] = e
        tags = e["tags"]
        marca = normalizar_marca(tags.get("brand"))
        if marca and (len(marca) > 120 or any(ord(c) < 32 for c in marca)):
            raise ErroCatalogo("Brand OSM invalida.")
        ofertas, avisos = ofertas_explicitas(tags)
        elementos[ident] = {"id_externo": ident, "marca": marca, "ofertas": ofertas, "avisos": avisos}
    return {"sha256": digest, "municipio": municipio, "data_base_utc": data, "elementos": elementos}


def planejar(fonte, postos, ofertas, incluir_testes=False):
    indice = {}
    for p in postos:
        if p.get("mapbox_id"):
            ident = p["mapbox_id"]
            if ident in indice:
                raise ErroCatalogo("ID externo duplicado no banco; revisar antes de completar.")
            indice[ident] = p
    atuais = {(r["posto_id"], r["combustivel_codigo"]): r for r in ofertas}
    plano, encontrados = [], 0
    for ident, elemento in fonte["elementos"].items():
        p = indice.get(ident)
        if p is None:
            continue  # Nao cria, vincula ou aproxima postos.
        encontrados += 1
        if elemento["marca"] and not (p.get("marca") or "").strip() and p.get("marca_origem") in (None, "osm"):
            plano.append({"tipo": "marca", "posto_id": p["id"], "id_externo": ident, "valor": elemento["marca"]})
        for codigo, estado in elemento["ofertas"].items():
            atual = atuais.get((p["id"], codigo))
            if atual and (atual["disponivel_manual"] is not None or atual["disponivel_osm"] is not None):
                continue
            plano.append({"tipo": "oferta_osm", "posto_id": p["id"], "codigo": codigo,
                          "valor": estado, "existe": atual is not None})
    if incluir_testes:
        por_id = {p["id"]: p for p in postos}
        for ident, (nome, lat, lon, tipo, produtos) in FIXTURES.items():
            p = por_id.get(ident)
            if not p or p.get("mapbox_id") is not None or p["nome"] != nome or p["tipo_posto"] != tipo:
                raise ErroCatalogo("Postos ficticios diferentes do inicializador; dados de teste bloqueados.")
            if abs(float(p["latitude"]) - lat) > 0.00000001 or abs(float(p["longitude"]) - lon) > 0.00000001:
                raise ErroCatalogo("Coordenadas dos postos ficticios alteradas; dados de teste bloqueados.")
            for codigo in produtos:
                atual = atuais.get((ident, codigo))
                if atual and (atual["disponivel_manual"] is not None or atual["disponivel_osm"] is not None):
                    continue
                plano.append({"tipo": "oferta_teste", "posto_id": ident, "codigo": codigo,
                              "valor": 1, "existe": atual is not None})
    return plano, encontrados


def salvar_backup(caminho, dados):
    """Backup dos metadados antes de qualquer DML. Nunca sobrescreve arquivo."""
    destino = Path(caminho)
    if not destino.is_absolute():
        raise ErroCatalogo("Use caminho absoluto para o backup de metadados.")
    descriptor = os.open(destino, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(dados, stream, ensure_ascii=False, indent=2, default=str)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def ler_estado(cursor, fonte, incluir_testes, travar=False):
    ids = list(fonte["elementos"])
    if not ids:
        raise ErroCatalogo("Fonte municipal sem postos validos.")
    placeholders = ",".join(["%s"] * len(ids))
    where = "mapbox_id IN (" + placeholders + ")"
    if incluir_testes:
        where += " OR id IN (1,2,3,4)"
    sufixo = " FOR UPDATE" if travar else ""
    cursor.execute("SELECT id,mapbox_id,nome,latitude,longitude,tipo_posto,marca,marca_origem "
                   "FROM postos WHERE " + where + " ORDER BY id" + sufixo, ids)
    postos = cursor.fetchall()
    ofertas = []
    if postos:
        pids = [p["id"] for p in postos]
        cursor.execute("SELECT posto_id,combustivel_codigo,disponivel_osm,osm_verificado_em,"
                       "disponivel_manual,manual_atualizado_em,manual_atualizado_por "
                       "FROM postos_combustiveis WHERE posto_id IN (" + ",".join(["%s"] * len(pids)) + ")"
                       " ORDER BY posto_id,combustivel_codigo" + sufixo, pids)
        ofertas = cursor.fetchall()
    return postos, ofertas


def executar(conn, fonte, aplicar=False, incluir_testes=False, backup=None, escrever_backup=salvar_backup):
    relatorio = {"status": "ok", "modo": "aplicar" if aplicar else "dry-run", "banco": BANCO,
                 "fonte_sha256": fonte["sha256"], "data_base_utc": str(fonte["data_base_utc"]),
                 "atribuicao": "© OpenStreetMap contributors — ODbL", "aplicadas": 0}
    bloqueado = False
    etapa = "leitura"
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS banco, VERSION() AS versao")
            servidor = cursor.fetchone()
            if servidor["banco"] != BANCO or "tidb" in servidor["versao"].lower():
                raise ErroCatalogo("Destino diferente do MySQL local esperado.")
            cursor.execute("SELECT versao,sha256,estado FROM ldo_docker_local WHERE id=1")
            esperado = {"versao": "1", "sha256": hashlib.sha256((ROOT / "docker/schema_base.sql").read_bytes()).hexdigest(), "estado": "pronto"}
            if cursor.fetchone() != esperado:
                raise ErroCatalogo("Marcador do laboratorio ausente ou divergente.")
            cursor.execute("SELECT TABLE_NAME AS nome,ENGINE AS motor FROM information_schema.TABLES "
                           "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('postos','postos_combustiveis')")
            if {r["nome"]: r["motor"] for r in cursor.fetchall()} != {"postos": "InnoDB", "postos_combustiveis": "InnoDB"}:
                raise ErroCatalogo("Tabelas de metadados precisam existir e usar InnoDB; conferir migracoes.")
            if aplicar:
                if not backup:
                    raise ErroCatalogo("Backup dos metadados e obrigatorio para aplicar.")
                cursor.execute("SELECT GET_LOCK(%s,0) AS obtido", (LOCK,))
                bloqueado = cursor.fetchone()["obtido"] == 1
                if not bloqueado:
                    raise ErroCatalogo("Outra revisao do catalogo esta em andamento.")
            postos, ofertas = ler_estado(cursor, fonte, incluir_testes, aplicar)
            plano, encontrados = planejar(fonte, postos, ofertas, incluir_testes)
            relatorio.update(postos_osm_encontrados=encontrados, marcas_a_preencher=sum(p["tipo"] == "marca" for p in plano),
                             ofertas_osm_a_preencher=sum(p["tipo"] == "oferta_osm" for p in plano),
                             ofertas_teste_a_preencher=sum(p["tipo"] == "oferta_teste" for p in plano), plano=plano)
            if aplicar and plano:
                etapa = "backup"
                escrever_backup(backup, {"formato": "ldo_metadados_v1", "criado_em_utc": datetime.now(timezone.utc).isoformat(),
                                        "fonte_sha256": fonte["sha256"], "banco": BANCO,
                                        "antes": {"postos": postos, "ofertas": ofertas}, "plano": plano})
                relatorio["backup_metadados"] = str(backup)
                etapa = "escrita"
                for item in plano:
                    if item["tipo"] == "marca":
                        cursor.execute("UPDATE postos SET marca=%s,marca_origem='osm' WHERE id=%s AND mapbox_id=%s "
                                       "AND (marca IS NULL OR TRIM(marca)='') AND (marca_origem IS NULL OR marca_origem='osm')",
                                       (item["valor"], item["posto_id"], item["id_externo"]))
                    else:
                        teste = item["tipo"] == "oferta_teste"
                        coluna = "disponivel_manual" if teste else "disponivel_osm"
                        data_coluna = "manual_atualizado_em" if teste else "osm_verificado_em"
                        data = datetime.now(timezone.utc).replace(tzinfo=None) if teste else fonte["data_base_utc"]
                        if item["existe"]:
                            cursor.execute(f"UPDATE postos_combustiveis SET {coluna}=%s,{data_coluna}=%s "
                                           "WHERE posto_id=%s AND combustivel_codigo=%s AND disponivel_manual IS NULL AND disponivel_osm IS NULL",
                                           (item["valor"], data, item["posto_id"], item["codigo"]))
                        else:
                            cursor.execute(f"INSERT INTO postos_combustiveis (posto_id,combustivel_codigo,{coluna},{data_coluna}) "
                                           "VALUES (%s,%s,%s,%s)", (item["posto_id"], item["codigo"], item["valor"], data))
                    if cursor.rowcount != 1:
                        raise ErroCatalogo("Metadado mudou durante a revisao; execucao interrompida.")
                etapa = "conferencia"
                depois_postos, depois_ofertas = ler_estado(cursor, fonte, incluir_testes, True)
                dp = {p["id"]: p for p in depois_postos}
                do = {(r["posto_id"], r["combustivel_codigo"]): r for r in depois_ofertas}
                for item in plano:
                    atual = dp[item["posto_id"]] if item["tipo"] == "marca" else do[(item["posto_id"], item["codigo"])]
                    campo = "marca" if item["tipo"] == "marca" else "disponivel_manual" if item["tipo"] == "oferta_teste" else "disponivel_osm"
                    if atual[campo] != item["valor"]:
                        raise ErroCatalogo("Conferencia dos metadados divergiu antes do commit.")
                etapa = "commit"
                conn.commit()
                relatorio["aplicadas"] = len(plano)
                etapa = "concluido"
            else:
                conn.rollback()
        return relatorio
    except Exception as exc:
        relatorio.update(status="resultado_commit_desconhecido" if etapa == "commit" else "falha", etapa=etapa,
                         erro=str(exc) if isinstance(exc, ErroCatalogo) else "Operacao interrompida; detalhes do driver omitidos.",
                         erro_tipo=type(exc).__name__)
        if etapa != "commit":
            try:
                conn.rollback()
                relatorio["rollback_confirmado"] = True
            except Exception:
                relatorio["rollback_confirmado"] = False
        return relatorio
    finally:
        if bloqueado:
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT RELEASE_LOCK(%s)", (LOCK,))
            except Exception:
                pass  # O fechamento da sessao tambem libera o lock.


def conectar_local(aplicar=False):
    config = load_config()
    if (os.getenv("LDO_DOCKER_LOCAL") != "1" or config.host != "db" or config.port != 3306
            or config.database != BANCO or config.user != "litro_local" or os.getenv("DATABASE_URL", "").strip()):
        raise ErroCatalogo("Execute somente no backend do Compose local db/litro_de_ouro_dev.")
    conn = get_db_connection(config=config, read_only=not aplicar, time_zone="+00:00")
    sock = getattr(conn, "_sock", None)
    if (not isinstance(sock, ssl.SSLSocket) or not sock.cipher()
            or sock.context.verify_mode != ssl.CERT_REQUIRED or not sock.context.check_hostname):
        conn.close()
        raise ErroCatalogo("TLS negociado com verificacao de identidade e obrigatorio.")
    return conn


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arquivo", required=True)
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--dry-run", action="store_true", help="Somente leitura; e o padrao.")
    modo.add_argument("--somente-fonte", action="store_true", help="Analise offline, sem conectar ao MySQL.")
    modo.add_argument("--aplicar", action="store_true")
    parser.add_argument("--incluir-dados-teste", action="store_true", help="Confirma as cinco ofertas da massa ficticia original, apos conferir seus quatro cadastros.")
    parser.add_argument("--banco")
    parser.add_argument("--sha256")
    parser.add_argument("--backup", help="Caminho absoluto novo. Monte uma pasta do Windows para persistir o JSON.")
    args = parser.parse_args(argv)
    conn = None
    try:
        if args.aplicar and (args.banco != BANCO or not args.sha256 or not args.backup):
            raise ErroCatalogo("Aplicar exige --banco litro_de_ouro_dev, --sha256 e --backup.")
        fonte = carregar_fonte(args.arquivo, args.sha256)
        if args.somente_fonte:
            elementos = list(fonte["elementos"].values())
            relatorio = {"status": "ok", "modo": "somente-fonte", "mysql_consultado": False,
                         "sha256": fonte["sha256"], "municipio": fonte["municipio"],
                         "postos_na_fonte": len(elementos), "com_brand": sum(bool(e["marca"]) for e in elementos),
                         "ofertas_explicitas": sum(len(e["ofertas"]) for e in elementos),
                         "avisos": [{"id_externo": e["id_externo"], "avisos": e["avisos"]} for e in elementos if e["avisos"]]}
        else:
            conn = conectar_local(args.aplicar)
            relatorio = executar(conn, fonte, args.aplicar, args.incluir_dados_teste, args.backup)
    except Exception as exc:
        relatorio = {"status": "falha", "erro_tipo": type(exc).__name__,
                     "erro": str(exc) if isinstance(exc, ErroCatalogo) else "Falha ao ler fonte ou conectar. Nenhuma mensagem do driver foi divulgada."}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
    print(json.dumps(relatorio, ensure_ascii=False, indent=2))
    return 0 if relatorio["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())