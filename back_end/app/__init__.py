from flask import Flask, jsonify
from flask_cors import CORS
from .rotas.auth import auth_bp
from .rotas.postos import postos_bp
from .rotas.precos import precos_bp
from .rotas.ia import ia_bp
from .rotas.atividade import atividade_bp

def create_app():
    app = Flask(__name__)
    
    CORS(app, resources={r"/*": {"origins": "*"}})

    # Rota raiz para o Render verificar se a API está viva
    @app.route('/')
    def index():
        return jsonify({
            "status": "online", 
            "api": "Litro de Ouro API",
            "versao": "1.0"
        }), 200

    @app.route('/favicon.ico')
    def favicon():
        return '', 204

    # Registro padronizado dos Blueprints
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(postos_bp, url_prefix='/postos')
    app.register_blueprint(precos_bp, url_prefix='/precos')
    app.register_blueprint(ia_bp, url_prefix='/ia')
    app.register_blueprint(atividade_bp, url_prefix='/atividade')

    return app