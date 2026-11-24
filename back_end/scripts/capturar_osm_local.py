"""Captura municipal OSM por HTTP/1.1; não importa app, .env ou banco."""
import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import math
from pathlib import Path
import subprocess
from typing import Any, TypeGuard

URL = "https://overpass.private.coffee/api/interpreter"
MAX_BYTES = 16 * 1024 * 1024

CONSULTA = (
    '[out:json][timeout:60];'
    'area["boundary"="administrative"]["admin_level"="8"]'
    '["IBGE:GEOCODIGO"="2507507"]->.municipio;'
    '.municipio out tags;('
    'nwr["amenity"="fuel"](area.municipio);'
    'nwr["amenity"="charging_station"](area.municipio);'
    ');out center tags;'
)


class ErroCaptura(ValueError):
    """Códigos controlados, sem dados privados do processo."""


def rejeitar_constante(valor):
    raise ErroCaptura("json_nao_finito")


def numero(valor: Any) -> TypeGuard[int | float]:
    return (
        isinstance(valor, (int, float))
        and not isinstance(valor, bool)
        and math.isfinite(valor)
    )


def validar_fonte(
    bruto: bytes,
    agora=None,
) -> dict[str, Any]:
    if not bruto or len(bruto) > MAX_BYTES:
        raise ErroCaptura("fonte_vazia_ou_acima_do_limite")

    try:
        corpo = json.loads(
            bruto,
            parse_constant=rejeitar_constante,
        )
    except (ValueError, UnicodeError):
        raise ErroCaptura(
            "json_invalido_ou_nao_finito"
        ) from None

    if not isinstance(corpo, dict) or corpo.get("remark"):
        raise ErroCaptura("resposta_incompleta")

    elementos = corpo.get("elements")

    if (
        not isinstance(elementos, list)
        or not 2 <= len(elementos) <= 5000
        or not all(
            isinstance(item, dict)
            for item in elementos
        )
    ):
        raise ErroCaptura("elementos_invalidos")

    areas = [
        item
        for item in elementos
        if item.get("type") == "area"
    ]

    if len(areas) != 1:
        raise ErroCaptura("area_ausente_ou_ambigua")

    tags = areas[0].get("tags")

    if (
        not isinstance(tags, dict)
        or tags.get("boundary") != "administrative"
        or tags.get("admin_level") != "8"
        or tags.get("IBGE:GEOCODIGO") != "2507507"
    ):
        raise ErroCaptura("municipio_divergente")

    vistos = set()

    locais = [
        item
        for item in elementos
        if item.get("type") != "area"
    ]

    for item in locais:
        tipo = item.get("type")
        identificador = item.get("id")
        centro = (
            item
            if tipo == "node"
            else item.get("center")
        )
        tags = item.get("tags")

        if (
            tipo not in ("node", "way", "relation")
            or type(identificador) is not int
            or identificador <= 0
            or not isinstance(tags, dict)
            or tags.get("amenity")
            not in ("fuel", "charging_station")
            or not isinstance(centro, dict)
        ):
            raise ErroCaptura("local_invalido")

        lat = centro.get("lat")
        lon = centro.get("lon")

        if (
            not numero(lat)
            or not numero(lon)
            or not -7.25 <= lat <= -6.95
            or not -35.0 <= lon <= -34.7
        ):
            raise ErroCaptura(
                "coordenadas_fora_do_recorte"
            )

        chave = (tipo, identificador)

        if chave in vistos:
            raise ErroCaptura("elemento_duplicado")

        vistos.add(chave)

    meta = corpo.get("osm3s")
    valor = (
        meta.get("timestamp_osm_base")
        if isinstance(meta, dict)
        else None
    )

    if not isinstance(valor, str):
        raise ErroCaptura("data_ausente")

    try:
        data = datetime.fromisoformat(
            valor.replace("Z", "+00:00")
        )
    except ValueError:
        raise ErroCaptura("data_invalida") from None

    if data.tzinfo is None:
        raise ErroCaptura("data_sem_fuso")

    agora = (
        datetime.now(timezone.utc)
        if agora is None
        else agora
    )

    idade = (agora - data).total_seconds()

    if not -300 <= idade <= 30 * 86400:
        raise ErroCaptura("fonte_futura_ou_antiga")

    return {
        "consulta_municipal_validada": True,
        "municipio_ibge": "2507507",
        "elementos_locais": len(locais),
        "data_base_fonte_utc": data.astimezone(
            timezone.utc
        ).isoformat(),
        "sha256_fonte": hashlib.sha256(
            bruto
        ).hexdigest(),
    }


def main(argv=None, executar=None):
    parser = argparse.ArgumentParser(
        description=__doc__
    )
    parser.add_argument(
        "--saida",
        required=True,
        help="Pasta nova, ainda inexistente.",
    )
    parser.add_argument(
        "--ipv6",
        action="store_true",
    )

    args = parser.parse_args(argv)
    executar = (
        subprocess.run
        if executar is None
        else executar
    )
    pasta = Path(args.saida)

    try:
        pasta.mkdir(
            parents=True,
            exist_ok=False,
        )
    except OSError:
        print(json.dumps({
            "status": "falha",
            "erro": "pasta_indisponivel_ou_existente",
        }))
        return 2

    temporario = pasta / "resposta.tmp"

    relatorio: dict[str, Any] = {
        "status": "falha",
        "etapa": "consultar_overpass",
        "servidor": URL,
        "protocolo_solicitado": "HTTP/1.1",
        "ipv6_solicitado": args.ipv6,
        "consulta_municipal_validada": False,
        "mysql_consultado": False,
        "gravacao_banco_habilitada": False,
        "atribuicao": (
            "© OpenStreetMap contributors — ODbL"
        ),
        "licenca_url": (
            "https://www.openstreetmap.org/copyright"
        ),
    }

    codigo = 1

    try:
        comando = [
            "curl",
            "--silent",
            "--show-error",
            "--http1.1",
            "--proto",
            "=https",
            "--connect-timeout",
            "15",
            "--max-time",
            "120",
            "--max-filesize",
            str(MAX_BYTES),
            "--retry",
            "0",
            "--header",
            "Accept: application/json",
            "--user-agent",
            (
                "LitroDeOuro/diagnostico "
                "(+https://github.com/odethemets/litro_de_ouro_app)"
            ),
            "--request",
            "POST",
            "--data-urlencode",
            "data=" + CONSULTA,
            "--output",
            str(temporario),
            "--write-out",
            "%{json}",
            URL,
        ]

        if args.ipv6:
            comando.insert(1, "--ipv6")

        resposta = executar(
            comando,
            capture_output=True,
            text=True,
            timeout=150,
            check=False,
        )

        info = json.loads(
            resposta.stdout or "{}",
            parse_constant=rejeitar_constante,
        )

        if not isinstance(info, dict):
            raise ErroCaptura("metricas_invalidas")

        http = info.get(
            "response_code",
            info.get("http_code"),
        )
        versao = info.get("http_version")

        relatorio["codigo_curl"] = resposta.returncode
        relatorio["status_http"] = (
            http if type(http) is int else None
        )

        verificacao = info.get("ssl_verify_result")
        relatorio["verificacao_tls"] = (
            verificacao
            if type(verificacao) is int
            else None
        )

        duracao = info.get("time_total")
        relatorio["duracao_s"] = (
            duracao if numero(duracao) else None
        )

        relatorio["http_version_negociada"] = (
            versao
            if versao in (
                "0", "1", "1.0", "1.1", "2", "3"
            )
            else None
        )

        ip = info.get("remote_ip")

        if isinstance(ip, str) and ip:
            try:
                relatorio["familia_ip_remota"] = (
                    "IPv"
                    + str(ipaddress.ip_address(ip).version)
                )
            except ValueError:
                pass

        if (
            resposta.returncode != 0
            or type(http) is not int
            or http != 200
        ):
            raise ErroCaptura(
                "consulta_http_nao_concluida"
            )

        if versao not in ("1", "1.0", "1.1"):
            raise ErroCaptura("http1_nao_confirmado")

        if (
            args.ipv6
            and relatorio.get("familia_ip_remota")
            != "IPv6"
        ):
            raise ErroCaptura("ipv6_nao_confirmado")

        relatorio["etapa"] = "validar_fonte"

        with temporario.open("rb") as arquivo:
            bruto = arquivo.read(MAX_BYTES + 1)

        dados = validar_fonte(bruto)

        relatorio["etapa"] = "arquivar_fonte"

        with (pasta / "fonte.json").open("xb") as arquivo:
            arquivo.write(bruto)

        manifesto = {
            "arquivos": {
                "fonte.json": dados["sha256_fonte"],
            },
        }

        with (pasta / "manifesto.json").open(
            "x",
            encoding="utf-8",
        ) as arquivo:
            json.dump(
                manifesto,
                arquivo,
                ensure_ascii=False,
                indent=2,
            )

        relatorio.update(dados)
        relatorio.update(
            status="ok",
            etapa="concluido",
        )
        codigo = 0

    except ErroCaptura as erro:
        relatorio["erro"] = str(erro)

    except Exception as erro:
        relatorio["erro_tipo"] = type(erro).__name__

    finally:
        temporario.unlink(missing_ok=True)

        with (pasta / "relatorio.json").open(
            "x",
            encoding="utf-8",
        ) as arquivo:
            json.dump(
                relatorio,
                arquivo,
                ensure_ascii=False,
                indent=2,
            )

        print(
            json.dumps(
                relatorio,
                ensure_ascii=False,
                indent=2,
            )
        )

    return codigo


if __name__ == "__main__":
    raise SystemExit(main())