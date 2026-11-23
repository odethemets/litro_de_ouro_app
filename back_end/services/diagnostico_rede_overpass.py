"""Sondas pequenas e limitadas; não consultam município ou banco."""
import ipaddress
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time

from services.fontes_overpass import (
    PERMITIDOS,
    servidores_configurados,
)

CONSULTA = "[out:json][timeout:5];node(1);out ids;"

PERFIS = (
    ("POST", "automatico"),
    ("GET", "automatico"),
    ("GET", "ipv4"),
)

MAX_CORPO = 262144


def comando_sonda(servidor, metodo, perfil, corpo, headers):
    if (
        servidor not in PERMITIDOS
        or (metodo, perfil) not in PERFIS
    ):
        raise ValueError("alvo_ou_perfil_nao_permitido")

    comando = [
        "curl",
        "--silent",
        "--show-error",
        "--proto",
        "=https",
        "--connect-timeout",
        "8",
        "--max-time",
        "12",
        "--max-filesize",
        str(MAX_CORPO),
        "--retry",
        "0",
        "--header",
        "Accept: application/json",
        "--user-agent",
        (
            "LitroDeOuro/diagnostico "
            "(+https://github.com/odethemets/litro_de_ouro_app)"
        ),
        "--dump-header",
        str(headers),
        "--output",
        str(corpo),
        "--write-out",
        "%{json}",
    ]

    if perfil == "ipv4":
        comando.append("--ipv4")

    if metodo == "GET":
        comando.append("--get")
    else:
        comando.extend(["--request", "POST"])

    comando.extend([
        "--data-urlencode",
        "data=" + CONSULTA,
        servidor,
    ])

    return comando


def _numero(valor):
    if isinstance(valor, bool):
        return None

    try:
        numero = float(valor)

        return (
            numero
            if math.isfinite(numero) and numero >= 0
            else None
        )
    except (TypeError, ValueError, OverflowError):
        return None


def _constante_invalida(valor):
    raise ValueError("json_nao_finito")


def sondar(
    servidor,
    metodo,
    perfil,
    *,
    executar=subprocess.run,
    env=None,
):
    env = os.environ if env is None else env

    registro = {
        "servidor": servidor,
        "metodo": metodo,
        "perfil": perfil,
        "consulta_minima": True,
        "consulta_municipal": False,
        "codigo_curl": None,
        "status_http": None,
        "resposta_overpass_reconhecida": False,
        "retry_after_presente": False,
        "proxy_configurado": any(
            env.get(chave)
            for chave in (
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "http_proxy",
                "https_proxy",
                "ALL_PROXY",
                "all_proxy",
            )
        ),
    }

    with tempfile.TemporaryDirectory() as pasta:
        corpo = Path(pasta) / "corpo"
        headers = Path(pasta) / "headers"

        comando = comando_sonda(
            servidor,
            metodo,
            perfil,
            corpo,
            headers,
        )

        try:
            resposta = executar(
                comando,
                capture_output=True,
                text=True,
                timeout=18,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return dict(
                registro,
                categoria="timeout_processo",
            )
        except OSError:
            return dict(
                registro,
                categoria="falha_executor",
            )

        registro["codigo_curl"] = resposta.returncode

        try:
            medidas = json.loads(
                resposta.stdout or "{}",
                parse_constant=_constante_invalida,
            )

            if not isinstance(medidas, dict):
                raise ValueError
        except (TypeError, ValueError):
            return dict(
                registro,
                categoria="metricas_invalidas",
            )

        bruto_http = medidas.get(
            "response_code",
            medidas.get("http_code"),
        )

        if (
            type(bruto_http) is int
            or (
                isinstance(bruto_http, str)
                and bruto_http.isdecimal()
            )
        ):
            http = int(bruto_http)
        else:
            http = None

        if http is not None and not 0 <= http <= 599:
            http = None

        verificacao_tls = medidas.get(
            "ssl_verify_result"
        )

        registro.update(
            status_http=http,
            verificacao_tls=(
                verificacao_tls
                if type(verificacao_tls) is int
                else None
            ),
            tempos_s={
                chave: _numero(medidas.get(chave))
                for chave in (
                    "time_namelookup",
                    "time_connect",
                    "time_appconnect",
                    "time_starttransfer",
                    "time_total",
                )
            },
        )

        ip_remoto = medidas.get("remote_ip")
        registro["familia_ip_remota"] = "indisponivel"

        if isinstance(ip_remoto, str) and ip_remoto:
            try:
                endereco = ipaddress.ip_address(ip_remoto)
            except ValueError:
                pass
            else:
                registro["familia_ip_remota"] = (
                    "IPv" + str(endereco.version)
                )

        if headers.is_file():
            with headers.open("rb") as stream:
                linhas = (
                    stream.read(16384)
                    .decode("utf-8", errors="replace")
                    .splitlines()
                )

            for linha in linhas:
                if linha.startswith("HTTP/"):
                    registro["retry_after_presente"] = (
                        False
                    )
                elif linha.lower().startswith(
                    "retry-after:"
                ):
                    registro["retry_after_presente"] = (
                        bool(
                            linha.split(":", 1)[1].strip()
                        )
                    )

        if resposta.returncode != 0:
            categorias = {
                5: "dns_proxy",
                6: "dns_servidor",
                7: "falha_conexao",
                28: "timeout",
                35: "falha_tls",
                60: "certificado_rejeitado",
                63: "corpo_acima_limite",
            }

            registro["categoria"] = categorias.get(
                resposta.returncode,
                "falha_curl",
            )
        elif http != 200:
            registro["categoria"] = "falha_http"
        else:
            try:
                with corpo.open("rb") as stream:
                    bruto = stream.read(
                        MAX_CORPO + 1
                    )

                if (
                    not bruto
                    or len(bruto) > MAX_CORPO
                ):
                    raise ValueError

                dados = json.loads(
                    bruto,
                    parse_constant=_constante_invalida,
                )

                if (
                    not isinstance(dados, dict)
                    or not isinstance(
                        dados.get("elements"),
                        list,
                    )
                    or dados.get("remark")
                ):
                    raise ValueError

                registro.update(
                    categoria="resposta_minima_valida",
                    resposta_overpass_reconhecida=True,
                )
            except (OSError, ValueError, TypeError):
                registro["categoria"] = (
                    "http200_sem_resposta_overpass_valida"
                )

    # Não publica corpo, stderr ou endereços de proxy.
    return registro


def diagnosticar_rede(
    env=None,
    *,
    executar=subprocess.run,
    pausar=time.sleep,
    emitir=None,
):
    env = os.environ if env is None else env

    urls = servidores_configurados(
        env.get("OSM_OVERPASS_URLS", ""),
        diagnostico=True,
    )

    registros = []
    paradas = []

    for servidor in urls:
        for metodo, perfil in PERFIS:
            if registros:
                pausar(2)

            registro = sondar(
                servidor,
                metodo,
                perfil,
                executar=executar,
                env=env,
            )

            registros.append(registro)

            if emitir:
                emitir(registro)

            motivo = None

            if registro.get("status_http") in (
                401,
                403,
                429,
            ):
                motivo = "acesso_recusado_ou_limite"
            elif registro.get(
                "retry_after_presente"
            ):
                motivo = "retry_after_recebido"
            elif registro.get("codigo_curl") in (
                35,
                60,
            ):
                motivo = "falha_tls_sem_contorno"

            if motivo:
                paradas.append({
                    "servidor": servidor,
                    "motivo": motivo,
                })

                break

    validas = [
        registro
        for registro in registros
        if registro[
            "resposta_overpass_reconhecida"
        ]
    ]

    return {
        "versao": 1,
        "status": (
            "ha_resposta_minima_valida"
            if validas
            else "sem_resposta_minima_valida"
        ),
        "testes_planejados": (
            len(urls) * len(PERFIS)
        ),
        "testes_realizados": len(registros),
        "paradas_por_host": paradas,
        "banco_consultado": False,
        "gravacao_banco_habilitada": False,
        "consulta_municipal_validada": False,
        "resultados": registros,
        "configuracao_alterada": False,
    }


def resumo_markdown(relatorio):
    linhas = [
        "## Conectividade Overpass",
        "",
        f"Resultado: **{relatorio['status']}**.",
        "",
        (
            "| Servidor | Método | Perfil | "
            "HTTP | Curl | Resultado |"
        ),
        "| --- | --- | --- | --- | --- | --- |",
    ]

    linhas += [
        (
            f"| {registro['servidor']} "
            f"| {registro['metodo']} "
            f"| {registro['perfil']} "
            f"| {registro['status_http']} "
            f"| {registro['codigo_curl']} "
            f"| {registro['categoria']} |"
        )
        for registro in relatorio["resultados"]
    ]

    linhas += [
        "",
        (
            "Uma resposta mínima válida não comprova "
            "a consulta municipal completa nem corrige "
            "o agendamento."
        ),
        (
            "Nenhuma configuração ou dado do banco "
            "foi alterado. SSL verify=0 isolado, "
            "sem resposta HTTP, não comprova "
            "conclusão de TLS."
        ),
        "",
    ]

    return "\n".join(linhas)