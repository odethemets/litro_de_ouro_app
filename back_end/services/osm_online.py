"""Carga OSM transacional: novos postos, marcas ausentes e ofertas datadas."""
from datetime import datetime, timedelta, timezone

from scripts.completar_catalogo_osm import ler_estado
from scripts.importar_postos_osm import processar_catalogo
from services.migrations import run

VERSAO_LOCK = "004_atividade_alertas"


class ErroOSM(ValueError):
    """Código controlado, sem mensagens privadas do driver."""


class FalhaOSM(RuntimeError):
    def __init__(self, etapa, erro):
        super().__init__("Sincronização interrompida.")
        self.etapa = etapa
        self.tipo = type(erro).__name__
        self.codigo = str(erro) if isinstance(erro, ErroOSM) else None
        self.commit_incerto = etapa == "commit"


def validar_data(data, agora=None):
    agora = agora or datetime.now(timezone.utc).replace(tzinfo=None)
    if not isinstance(data, datetime) or data.tzinfo is not None:
        raise ErroOSM("data_base_invalida")
    if data > agora + timedelta(minutes=5) or agora - data > timedelta(days=30):
        raise ErroOSM("fonte_futura_ou_mais_antiga_que_30_dias")


# Marcas só preenchem lacunas. Ofertas OSM podem mudar com fonte mais recente.
def planejar_metadados(fonte, postos, ofertas):
    indice = {p["mapbox_id"]: p for p in postos}
    if len(indice) != len(postos):
        raise ErroOSM("identificador_externo_duplicado")
    atuais = {(o["posto_id"], o["combustivel_codigo"]): o for o in ofertas}
    plano = []
    for ident, elemento in fonte["elementos"].items():
        posto = indice.get(ident)
        if posto is None:
            continue
        if (
            elemento["marca"]
            and not (posto.get("marca") or "").strip()
            and posto.get("marca_origem") in (None, "osm")
        ):
            plano.append({
                "tipo": "marca", "posto_id": posto["id"],
                "id_externo": ident, "valor": elemento["marca"],
            })
        for codigo, valor in elemento["ofertas"].items():
            atual = atuais.get((posto["id"], codigo))
            if atual is not None:
                if atual["disponivel_manual"] is not None:
                    continue
                anterior = atual["osm_verificado_em"]
                if anterior is not None:
                    if not isinstance(anterior, datetime) or anterior.tzinfo is not None:
                        raise ErroOSM("data_osm_existente_invalida")
                    if anterior > fonte["data_base_utc"]:
                        continue
                    if anterior == fonte["data_base_utc"]:
                        if atual["disponivel_osm"] != valor:
                            raise ErroOSM("fontes_conflitantes_na_mesma_data")
                        continue
            plano.append({
                "tipo": "oferta", "posto_id": posto["id"], "codigo": codigo,
                "valor": valor, "existe": atual is not None,
            })
    return plano


def validar_migracoes(conn, migracoes, banco):
    relatorio = run(conn, migracoes, apply=False, expected_database=banco)
    if any(m["estado"] != "aplicada" for m in relatorio["migracoes"]):
        raise ErroOSM("aplique_as_migracoes_antes_da_carga_osm")


# Uma linha já existente coordena somente os executores deste novo fluxo.
def iniciar_escrita(conn, versao, migracoes):
    conn.rollback()
    with conn.cursor() as cursor:
        if "tidb" in versao.lower():
            cursor.execute("SET SESSION tidb_txn_mode = 'pessimistic'")
        cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
    conn.begin()
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT versao,sha256,estado FROM schema_migrations "
            "WHERE versao=%s FOR UPDATE", (VERSAO_LOCK,),
        )
        linha = cursor.fetchone()
    sha = next((m["sha256"] for m in migracoes if m["versao"] == VERSAO_LOCK), None)
    if not linha or linha["estado"] != "aplicada" or linha["sha256"] != sha or sha is None:
        raise ErroOSM("registro_de_coordenacao_ausente_ou_divergente")


def aplicar_metadados(cursor, plano, data):
    for item in plano:
        if item["tipo"] == "marca":
            cursor.execute(
                "UPDATE postos SET marca=%s,marca_origem='osm' "
                "WHERE id=%s AND mapbox_id=%s "
                "AND (marca IS NULL OR TRIM(marca)='') "
                "AND (marca_origem IS NULL OR marca_origem='osm')",
                (item["valor"], item["posto_id"], item["id_externo"]),
            )
        elif item["existe"]:
            cursor.execute(
                "UPDATE postos_combustiveis SET disponivel_osm=%s,osm_verificado_em=%s "
                "WHERE posto_id=%s AND combustivel_codigo=%s AND disponivel_manual IS NULL "
                "AND (osm_verificado_em IS NULL OR osm_verificado_em<=%s)",
                (item["valor"], data, item["posto_id"], item["codigo"], data),
            )
        else:
            cursor.execute(
                "INSERT INTO postos_combustiveis "
                "(posto_id,combustivel_codigo,disponivel_osm,osm_verificado_em) "
                "VALUES (%s,%s,%s,%s)",
                (item["posto_id"], item["codigo"], item["valor"], data),
            )
        if cursor.rowcount != 1:
            raise ErroOSM("metadado_mudou_durante_a_carga")


def conferir_metadados(plano, postos, ofertas, data):
    por_id = {p["id"]: p for p in postos}
    por_produto = {(o["posto_id"], o["combustivel_codigo"]): o for o in ofertas}
    for item in plano:
        if item["tipo"] == "marca":
            atual = por_id[item["posto_id"]]
            correto = atual["marca"] == item["valor"] and atual["marca_origem"] == "osm"
        else:
            atual = por_produto[(item["posto_id"], item["codigo"])]
            correto = (
                atual["disponivel_osm"] == item["valor"]
                and atual["osm_verificado_em"] == data
                and atual["disponivel_manual"] is None
            )
        if not correto:
            raise ErroOSM("conferencia_antes_do_commit_divergiu")


def sincronizar(conn, fonte, lugares, migracoes, banco, aplicar=False,
                backup=None, verificar=validar_migracoes):
    etapa = "validar_destino"
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS banco, VERSION() AS versao")
            servidor = cursor.fetchone()
        if servidor["banco"] != banco:
            raise ErroOSM("banco_divergente")
        etapa = "validar_migracoes"
        verificar(conn, migracoes, banco)
        if aplicar:
            if backup is None:
                raise ErroOSM("backup_de_metadados_obrigatorio")
            etapa = "coordenar_escrita"
            iniciar_escrita(conn, servidor["versao"], migracoes)
        etapa = "consultar_estado"
        with conn.cursor() as cursor:
            antes_postos, antes_ofertas = ler_estado(cursor, fonte, False, aplicar)
            if aplicar:
                etapa = "salvar_backup"
                backup({
                    "banco": banco, "fonte_sha256": fonte["sha256"],
                    "postos": antes_postos, "ofertas": antes_ofertas,
                })
            etapa = "classificar_e_importar"
            catalogo = processar_catalogo(cursor, lugares, aplicar=aplicar)
            postos, ofertas = (
                ler_estado(cursor, fonte, False, True)
                if aplicar else (antes_postos, antes_ofertas)
            )
            if not aplicar:
                postos = [*postos, *[
                    {"id": "novo:" + item["id_externo"], "mapbox_id": item["id_externo"],
                     "marca": None, "marca_origem": None}
                    for item in catalogo["itens"] if item["categoria"] == "novos"
                ]]
            plano = planejar_metadados(fonte, postos, ofertas)
            if aplicar:
                etapa = "atualizar_metadados"
                aplicar_metadados(cursor, plano, fonte["data_base_utc"])
                etapa = "conferir_metadados"
                conferir_metadados(
                    plano, *ler_estado(cursor, fonte, False, True), fonte["data_base_utc"],
                )
        if aplicar:
            etapa = "commit"
            conn.commit()
        else:
            conn.rollback()
        return {
            "status": "ok", "modo": "aplicar" if aplicar else "dry-run",
            "banco": banco, "catalogo": catalogo, "plano_metadados": plano,
            "metadados_planejados": len(plano),
            "metadados_aplicados": len(plano) if aplicar else 0,
            "precos_modificados": 0, "usuarios_criados": 0,
        }
    except Exception as erro:
        if etapa != "commit":
            try:
                conn.rollback()
            except Exception:
                pass
        raise FalhaOSM(etapa, erro) from None
