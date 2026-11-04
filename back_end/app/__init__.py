# back_end/app/__init__.py

import os

from flask import Flask, jsonify
from flask_cors import CORS

from .rotas.auth import auth_bp
from .rotas.postos import postos_bp
from .rotas.precos import precos_bp
from .rotas.ia import ia_bp
from .rotas.atividade import atividade_bp


def create_app():
    app = Flask(__name__)

    # O login e o decorator utilizarão esta mesma chave.
    # A chave vem do ambiente, nunca de um valor padrão no código.
    segredo = os.getenv("SECRET_KEY", "")

    if (
        len(segredo.strip().encode("utf-8")) < 32
        or segredo.strip() == "segredo-padrao-temporario"
    ):
        raise RuntimeError(
            "Configure SECRET_KEY com um segredo aleatório "
            "de pelo menos 32 bytes."
        )

    # Preserva exatamente o valor configurado.
    # Não registrar essa variável em logs.
    app.config["SECRET_KEY"] = segredo

    # Mantém o comportamento atual para não bloquear os clientes existentes.
    # A restrição às origens reais da Vercel será uma configuração separada.
    CORS(
        app,
        resources={
            r"/*": {
                "origins": "*"
            }
        },
    )

    @app.route("/")
    def index():
        # Confirma apenas que o processo Flask está respondendo.
        # Não comprova conexão com banco nem funcionamento do e-mail.
        return jsonify({
            "status": "online",
            "api": "Litro de Ouro API",
            "versao": "1.0",
        }), 200

    @app.route("/favicon.ico")
    def favicon():
        return "", 204

    # Preserva todos os caminhos públicos existentes.
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(postos_bp, url_prefix="/postos")
    app.register_blueprint(precos_bp, url_prefix="/precos")
    app.register_blueprint(ia_bp, url_prefix="/ia")
    app.register_blueprint(atividade_bp, url_prefix="/atividade")

    return app