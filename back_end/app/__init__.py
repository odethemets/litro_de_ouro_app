from flask import Flask
from flask_cors import CORS
from .rotas.auth import auth_bp
from .rotas.postos import postos_bp
from .rotas.precos import precos_bp

def create_app():
    app = Flask(__name__)
    
    CORS(app, resources={r"/*": {"origins": "*"}})

    @app.route('/favicon.ico')
    def favicon():
        return '', 204

    # Registro padronizado dos Blueprints
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(postos_bp, url_prefix='/postos')
    app.register_blueprint(precos_bp, url_prefix='/precos')

    return app