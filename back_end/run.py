from flask import Flask
from app.rotas.auth import auth_bp
from app.rotas.postos import postos_bp

app = Flask(__name__)

# Registro das rotas modulares
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(postos_bp, url_prefix='/postos')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)