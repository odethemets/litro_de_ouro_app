# back_end/run.py

import os

from dotenv import load_dotenv

# Carrega o .env local antes de importar e criar a aplicação.
# Variáveis já definidas no Render não são sobrescritas.
load_dotenv()

from app import create_app


# Objeto utilizado pelo Gunicorn: run:app
app = create_app()


if __name__ == "__main__":
    # Execução local.
    # No Render, utilize Gunicorn em vez deste servidor de desenvolvimento.
    porta = int(os.getenv("PORT", "5000"))

    # Debug desativado por padrão.
    # Para desenvolvimento local, defina FLASK_DEBUG=1.
    debug_ativo = os.getenv("FLASK_DEBUG", "0") == "1"

    app.run(
        host="0.0.0.0",
        port=porta,
        debug=debug_ativo,
    )