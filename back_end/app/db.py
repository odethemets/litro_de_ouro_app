import pymysql

def get_db_connection():
    return pymysql.connect(
        # 1. O Host longo da Aiven
        host='litro-de-ouro-api-2026-litro-de-ouro-app.d.aivencloud.com', 
        
        # 2. A porta da Aiven (NÃO é a 3306)
        port=26841, 
        
        # 3. O Utilizador
        user='avnadmin', 
        
        # 4. A Senha da Aiven
        password='', 
        
        # 5. O Banco de Dados
        database='defaultdb', 
        
        cursorclass=pymysql.cursors.DictCursor,
        
        # 6. A Aiven exige conexão segura (SSL). Adicione esta linha:
        ssl={'ssl': {}} 
    )