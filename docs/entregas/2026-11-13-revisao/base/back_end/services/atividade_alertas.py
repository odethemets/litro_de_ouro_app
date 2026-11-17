"""Histórico e fila transacionais; transporte push é uma integração separada."""
from services.catalogo_postos import NOMES


def registrar_karma(cursor, usuario_id, pontos, origem, motivo, registo_id):
    # O chamador deve deter o lock da conta. A origem protege reprocessamentos.
    cursor.execute("SELECT id FROM historico_karma WHERE usuario_id=%s AND origem=%s", (usuario_id, origem))
    if cursor.fetchone():
        return
    cursor.execute("UPDATE usuarios SET karma=COALESCE(karma,0)+%s WHERE id=%s", (pontos, usuario_id))
    cursor.execute("SELECT karma FROM usuarios WHERE id=%s", (usuario_id,))
    saldo = cursor.fetchone()["karma"]
    cursor.execute("""
        INSERT INTO historico_karma (usuario_id,origem,motivo,pontos,saldo_apos,registo_id,criado_em)
        VALUES (%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP())
    """, (usuario_id, origem, motivo, pontos, saldo, registo_id))


def processar_pendentes(conn, limite=100):
    """Uma transação por evento; locks serializam executores e preferências."""
    processados = 0
    for _ in range(limite):
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT e.registo_id,e.preco_anterior,r.posto_id,r.tipo_combustivel,r.preco
                    FROM eventos_preco e JOIN registos_preco r ON r.id=e.registo_id
                    WHERE e.processado_em IS NULL ORDER BY e.registo_id LIMIT 1 FOR UPDATE
                """)
                evento = cursor.fetchone()
                if not evento:
                    conn.rollback()
                    break
                codigo = NOMES.get(evento["tipo_combustivel"])
                if codigo is None:
                    raise ValueError("Combustível desconhecido na fila")
                cursor.execute("""
                    SELECT pa.usuario_id,pa.somente_quedas,pa.intervalo_minutos
                    FROM preferencias_alertas pa
                    JOIN favoritos_postos fp ON fp.usuario_id=pa.usuario_id AND fp.posto_id=%s
                    JOIN favoritos_combustiveis fc ON fc.usuario_id=pa.usuario_id AND fc.combustivel_codigo=%s
                    WHERE pa.ativo=1 ORDER BY pa.usuario_id FOR UPDATE
                """, (evento["posto_id"], codigo))
                for pref in cursor.fetchall():
                    anterior = evento["preco_anterior"]
                    if pref["somente_quedas"] and (anterior is None or evento["preco"] >= anterior):
                        continue
                    cursor.execute("""
                        SELECT id FROM notificacoes WHERE usuario_id=%s AND posto_id=%s
                        AND combustivel_codigo=%s AND criado_em > UTC_TIMESTAMP() - INTERVAL %s MINUTE
                        LIMIT 1
                    """, (pref["usuario_id"], evento["posto_id"], codigo, pref["intervalo_minutos"]))
                    if cursor.fetchone():
                        continue
                    cursor.execute("""
                        INSERT INTO notificacoes (usuario_id,registo_id,posto_id,combustivel_codigo,
                            preco_anterior,preco_novo,criado_em)
                        VALUES (%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP())
                        ON DUPLICATE KEY UPDATE id=id
                    """, (pref["usuario_id"], evento["registo_id"], evento["posto_id"], codigo, anterior, evento["preco"]))
                cursor.execute("UPDATE eventos_preco SET processado_em=UTC_TIMESTAMP() WHERE registo_id=%s", (evento["registo_id"],))
            conn.commit()
            processados += 1
        except Exception:
            conn.rollback()
            raise
    return processados
