from flask import Flask
from flask_cors import CORS  # 1. Adicione a importação do CORS
from app.rotas.auth import auth_bp
from app.rotas.postos import postos_bp

app = Flask(__name__)

# 2. Ative o CORS (Permite que o React Native Web aceda ao Flask)
CORS(app)

# Registro das rotas modulares
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(postos_bp, url_prefix='/postos')

if __name__ == '__main__':
    # O host '0.0.0.0' permite que o telemóvel encontre o computador na rede local
    app.run(debug=True, host='0.0.0.0', port=5000)