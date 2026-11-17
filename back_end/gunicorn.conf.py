"""Inicialização compartilhada pelo Docker local e pelo serviço no Render."""
import os

try:
    _porta = int(os.getenv("PORT", "5000"))
except ValueError:
    raise RuntimeError("PORT deve ser um inteiro entre 1 e 65535.") from None
if not 1 <= _porta <= 65535:
    raise RuntimeError("PORT deve ser um inteiro entre 1 e 65535.")

bind = f"0.0.0.0:{_porta}"
workers = 1
worker_class = "gthread"
threads = 2
timeout = 75
graceful_timeout = 30
keepalive = 5

# O Render recolhe stderr; as rotas continuam responsáveis pelos logs da aplicação.
# O access log fica desativado para não registrar coordenadas presentes na URL.
errorlog = "-"
accesslog = None
capture_output = True
