# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt requirements-docker.txt ./

# A CA de proxy e opcional e fica somente no RUN, fora das camadas da imagem.
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    python -m pip install --no-cache-dir -r requirements-docker.txt

RUN groupadd --gid 1000 app && useradd --uid 1000 --gid app --create-home app
COPY --chown=app:app . .
USER app
EXPOSE 5000
CMD ["gunicorn", "--bind=0.0.0.0:5000", "--workers=1", "app:create_app()"]