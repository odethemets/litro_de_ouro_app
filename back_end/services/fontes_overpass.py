"""Configuração pública e restrita da captura OSM; não lê banco ou .env."""
import os

PRINCIPAL = "https://overpass-api.de/api/interpreter"
ALTERNATIVO = "https://overpass.private.coffee/api/interpreter"
TERCEIRO = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"

PERMITIDOS = (
    PRINCIPAL,
    ALTERNATIVO,
    TERCEIRO,
)


class ConfiguracaoOverpassInvalida(ValueError):
    """Mensagens são códigos fixos, sem valores recebidos."""


def servidores_configurados(bruto=None, *, diagnostico=False):
    bruto = (
        os.environ.get("OSM_OVERPASS_URLS", "")
        if bruto is None
        else bruto
    )

    if not isinstance(bruto, str) or len(bruto) > 600:
        raise ConfiguracaoOverpassInvalida(
            "configuracao_servidores_overpass_invalida"
        )

    if not bruto.strip():
        return (
            PERMITIDOS
            if diagnostico
            else (PRINCIPAL, ALTERNATIVO)
        )

    partes = [p.strip() for p in bruto.split(",")]

    if (
        not 1 <= len(partes) <= 3
        or any(p not in PERMITIDOS for p in partes)
    ):
        # Não inclui URLs recebidas na mensagem de erro.
        raise ConfiguracaoOverpassInvalida(
            "servidor_overpass_nao_permitido"
        )

    return tuple(dict.fromkeys(partes))


def plano_captura(env=None):
    env = os.environ if env is None else env

    urls = servidores_configurados(
        env.get("OSM_OVERPASS_URLS", "")
    )

    ipv4 = env.get("OSM_OVERPASS_IPV4", "")

    if ipv4 not in ("", "false", "true"):
        raise ConfiguracaoOverpassInvalida(
            "configuracao_ipv4_overpass_invalida"
        )

    # Mantém três tentativas.
    return (
        tuple(urls[i % len(urls)] for i in range(3)),
        ipv4 == "true",
    )