import hashlib, inspect, json, os, platform
from pathlib import Path
from importlib.metadata import version
from app import create_app
from services.database import get_db_connection, load_config
from services.atividade_alertas import processar_pendentes
config=load_config()
result={'python':platform.python_version(),'factory':inspect.getfile(create_app),'assinatura_processador':str(inspect.signature(processar_pendentes)), 'pacotes':{p:version(p) for p in ['Flask','PyMySQL','google-genai','Pillow','gunicorn','Flask-Cors']},'config_presenca':{k:bool(os.getenv(k,'').strip()) for k in ['GEMINI_API_KEY','GEMINI_MODEL','DROPBOX_TOKEN','MAPBOX_TOKEN','RESEND_API_KEY','SECRET_KEY','APP_ENV','CORS_ORIGINS','DATABASE_URL','DB_HOST','DB_NAME','DB_SSL_CA','OSM_SYNC_ENABLED','OSM_SYNC_APPLY']},'destino_local_esperado':config.host=='db' and config.database=='litro_de_ouro_dev','hashes':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in ['app/__init__.py','services/infra_web.py','services/atividade_alertas.py','services/executor_alertas.py','scripts/executar_alertas.py','app/rotas/ia.py','requirements.txt']}}
app=create_app()
result['rotas']=[{'rota':r.rule,'metodos':sorted(r.methods),'endpoint':r.endpoint} for r in app.url_map.iter_rules()]
if result['destino_local_esperado']:
 conn=get_db_connection(read_only=True,time_zone='+00:00')
 try:
  with conn.cursor() as c:
   result['banco']={}
   for nome,sql in {'destino':'SELECT DATABASE() AS banco, VERSION() AS versao','catalogo':"SELECT COUNT(*) AS total,SUM(mapbox_id LIKE 'osm:%') AS osm,SUM(nome LIKE '[TESTE]%') AS teste FROM postos",'fila':'SELECT COUNT(*) AS pendentes, MIN(criado_em) AS mais_antigo FROM eventos_preco WHERE processado_em IS NULL','migracoes':'SELECT versao,sha256,estado FROM schema_migrations ORDER BY versao','tabelas':'SHOW TABLES'}.items():
    c.execute(sql);result['banco'][nome]=c.fetchall()
 finally:conn.rollback();conn.close()
print(json.dumps(result,default=str,ensure_ascii=False,indent=2))
