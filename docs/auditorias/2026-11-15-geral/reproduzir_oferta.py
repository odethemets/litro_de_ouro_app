"""Reprodução isolada: função real do cadastro, Flask real e banco/Karma simulados."""
import json
from unittest.mock import MagicMock, patch
from flask import Flask
from app.rotas import precos
conn=MagicMock()
cursor=conn.cursor.return_value.__enter__.return_value
cursor.lastrowid=123
queries=[]
def execute(sql,args=None):
 queries.append(' '.join(sql.split()))
 cursor.sql=sql

def fetchone():
 sql=cursor.sql
 if 'FROM usuarios' in sql: return {'id':1}
 if 'FROM postos_combustiveis' in sql: return {'disponivel_manual':0,'disponivel_osm':0}
 if 'FROM postos' in sql: return {'latitude':-7.11,'longitude':-34.86,'nome':'Sintetico','tipo_posto':'Convencional'}
 return None
cursor.execute.side_effect=execute
cursor.fetchone.side_effect=fetchone
app=Flask(__name__)
with app.test_request_context('/precos',method='POST'), patch.object(precos,'get_db_connection',return_value=conn), patch.object(precos,'registrar_karma') as karma:
 resposta,status=precos.registrar_preco_validado(1,{'posto_id':1,'tipo_combustivel':'Etanol','preco':'4.39','latitude':-7.11,'longitude':-34.86,'precisao_m':10,'simulada':False})
 print(json.dumps({'http':status,'consultou_disponibilidade':any('postos_combustiveis' in q for q in queries),'commits_simulados':conn.commit.call_count,'karma_simulado':karma.call_count,'banco_real':False}))
