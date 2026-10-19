import os
import pymysql
import pymysql.cursors
from dotenv import load_dotenv

# Carrega o .env localmente, mas não bloqueia as variáveis do servidor
load_dotenv()

def get_db_connection():
    # Vai buscar a senha. Se não encontrar, tenta ler do ambiente global do Render.
    db_password = os.getenv('DB_PASSWORD') or os.environ.get('DB_PASSWORD')
    db_host = os.getenv('DB_HOST') or os.environ.get('DB_HOST')

    return pymysql.connect(
        host=db_host,
        port=26841,
        user='avnadmin',
        password=db_password, 
        database='defaultdb',
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
        ssl={'ssl': {}}
    )