import os
import pymysql
import pymysql.cursors
from dotenv import load_dotenv

# O que faz: 
#   Lê as credenciais secretas e estabelece a ponte de comunicação direta com o banco de dados MySQL local.
# Como faz: 
#   Chama a função "load_dotenv()" para carregar as variáveis escondidas no ficheiro ".env". Depois, utiliza o driver "PyMySQL" para conectar ao banco, configurando o "DictCursor" para que os resultados das tabelas voltem em formato de dicionários ({'id': 1, 'nome': 'Posto'}), facilitando o uso no Flask.

load_dotenv()

def get_db_connection():
    return pymysql.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 3306)),
        user=os.getenv('DB_USER', 'root'),
        # CORREÇÃO: Nunca deixe a senha real como fallback no código-fonte. Deixe vazio.
        # A sua senha '843599' deve ficar APENAS dentro do arquivo .env
        password=os.getenv('DB_PASSWORD', ''), 
        database=os.getenv('DB_NAME', 'litro_de_ouro'),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False # Exige que usemos conn.commit() após INSERTS/UPDATES para maior segurança
    )