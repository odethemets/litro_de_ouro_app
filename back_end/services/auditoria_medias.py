"""Auditoria somente de leitura do bloco inicial de médias municipais ANP."""

from collections import Counter

from services.referencias_medias import (
    ErroMedias,
    FIM,
    FONTE_SHA256,
    INICIO,
    MEDIAS,
    _flag,
    validar_referencia,
)


def auditar_medias(conn, migracoes, *, banco):
    """Valida schema/proveniência e relata contagens; nunca aplica ou corrige."""
    from services.migrations import run

    try:
        if not isinstance(banco, str) or not banco.strip():
            raise ErroMedias("Informe o nome exato do banco esperado.")
        estado = run(conn, migracoes, expected_database=banco)
        if any(m["estado"] != "aplicada" for m in estado["migracoes"]):
            raise ErroMedias("A auditoria exige todas as migrações aplicadas, inclusive 006.")

        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT posto_id,combustivel_codigo,preco,municipio_referencia,"
                "uf_referencia,periodo_inicio,periodo_fim,amostra,fonte_sha256,"
                "snapshot_sha256 FROM referencias_medias_iniciais "
                "ORDER BY posto_id,combustivel_codigo LIMIT 8001"
            )
            referencias = cursor.fetchall()
            if len(referencias) > 8000:
                raise ErroMedias("O volume excede o escopo desta auditoria inicial.")

            pares = set()
            por_produto = Counter()
            por_snapshot = Counter()
            for referencia in referencias:
                validar_referencia(referencia)
                par = (referencia["posto_id"], referencia["combustivel_codigo"])
                if par in pares:
                    raise ErroMedias("Par posto/produto repetido na auditoria.")
                pares.add(par)
                por_produto[par[1]] += 1
                por_snapshot[referencia["snapshot_sha256"]] += 1

            ids = sorted({p for p, _ in pares})
            postos, ofertas, observados = {}, {}, set()
            if ids:
                marcas = ",".join(["%s"] * len(ids))
                cursor.execute(
                    "SELECT id,tipo_posto FROM postos WHERE id IN (" + marcas + ")", ids
                )
                postos = {r["id"]: r for r in cursor.fetchall()}
                if set(postos) != set(ids):
                    raise ErroMedias("Referência sem posto correspondente.")
                cursor.execute(
                    "SELECT posto_id,combustivel_codigo,disponivel_manual,disponivel_osm "
                    "FROM postos_combustiveis WHERE posto_id IN (" + marcas + ")", ids
                )
                ofertas = {
                    (r["posto_id"], r["combustivel_codigo"]): r
                    for r in cursor.fetchall()
                }
                cursor.execute(
                    "SELECT DISTINCT posto_id,tipo_combustivel FROM registos_preco "
                    "WHERE posto_id IN (" + marcas + ")", ids
                )
                observados = {
                    (r["posto_id"], r["tipo_combustivel"])
                    for r in cursor.fetchall()
                }

        indisponiveis = 0
        for par in pares:
            oferta = ofertas.get(par, {})
            manual = _flag(oferta.get("disponivel_manual"))
            osm = _flag(oferta.get("disponivel_osm"))
            if (manual if manual is not None else osm) is False:
                indisponiveis += 1

        return {
            "status": "ok",
            "modo": "somente-leitura",
            "banco": banco,
            "versao_servidor": estado["versao_servidor"],
            "total_referencias": len(referencias),
            "postos_com_referencias": len(ids),
            "por_combustivel": dict(sorted(por_produto.items())),
            "por_snapshot_sha256": dict(sorted(por_snapshot.items())),
            "fonte_sha256": FONTE_SHA256,
            "periodo_inicio": INICIO.isoformat(),
            "periodo_fim": FIM.isoformat(),
            "referencias_com_historico_observado": sum(
                (pid, MEDIAS[codigo][0]) in observados for pid, codigo in pares
            ),
            "referencias_com_oferta_indisponivel": indisponiveis,
            "referencias_em_tipo_incompativel": sum(
                postos[pid]["tipo_posto"] != "Convencional" for pid, _ in pares
            ),
            "gravacao_executada": False,
            "limite": (
                "Contagens de armazenamento e histórico; não comprovam exibição "
                "no app, filtros aplicados ou preço mais recente por produto."
            ),
        }
    finally:
        conn.rollback()