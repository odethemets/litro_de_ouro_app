from flask import Flask
from flask_cors import CORS

def create_app():
    app = Flask(__name__)

    # 1. Configuração única do CORS para permitir o acesso Web e Mobile
    CORS(app, resources={r"/*": {"origins": "*"}})

    # Importa os Blueprints dos ficheiros modulares
    from .rotas.auth import auth_bp
    from .rotas.postos import bp as postos_bp
    from .rotas.precos import bp as precos_bp

    # 2. Regista as rotas na aplicação principal com os prefixos de URL
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(postos_bp, url_prefix='/postos')
    app.register_blueprint(precos_bp, url_prefix='/precos')

    return app