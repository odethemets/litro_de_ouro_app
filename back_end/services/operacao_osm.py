"""Política da operação OSM; não acessa o banco nem altera dados."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from urllib.request import Request, urlopen

from services.admin_reports import json_default
from services.osm_online import ErroOSM


class ErroOperacao(ErroOSM):
    """Código controlado, sem credenciais ou mensagens do driver."""


def canonico(valor):
    return json.dumps(
        valor,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        default=json_default,
    ).encode("utf-8")


def limitar(valor, maximo, codigo):
    if type(valor) is not int or not 0 <= valor <= maximo:
        raise ErroOperacao(codigo)


def validar_limites(relatorio, max_novos=20, max_metadados=1000):
    if relatorio.get("status") != "ok":
        raise ErroOperacao("previa_nao_concluida")

    limitar(max_novos, 3000, "limite_novos_invalido")
    limitar(max_metadados, 30000, "limite_metadados_invalido")

    limitar(
        relatorio["catalogo"]["novos"],
        max_novos,
        "novos_acima_do_limite",
    )
    limitar(
        relatorio["metadados_planejados"],
        max_metadados,
        "metadados_acima_do_limite",
    )


def minimizar_estado(dados):
    # O autor manual não é necessário para recuperar metadados OSM.
    campos_postos = (
        "id",
        "mapbox_id",
        "nome",
        "latitude",
        "longitude",
        "tipo_posto",
        "marca",
        "marca_origem",
    )
    campos_ofertas = (
        "posto_id",
        "combustivel_codigo",
        "disponivel_osm",
        "osm_verificado_em",
        "disponivel_manual",
        "manual_atualizado_em",
    )

    return {
        "banco": dados["banco"],
        "fonte_sha256": dados["fonte_sha256"],
        "postos": [
            {campo: posto.get(campo) for campo in campos_postos}
            for posto in dados["postos"]
        ],
        "ofertas": [
            {campo: oferta.get(campo) for campo in campos_ofertas}
            for oferta in dados["ofertas"]
        ],
    }


def assinatura_plano(catalogo, plano, postos):
    indice = {
        posto["id"]: posto["mapbox_id"]
        for posto in postos
    }

    def externo(item):
        ident = item["posto_id"]

        if isinstance(ident, str) and ident.startswith("novo:"):
            return ident[5:]

        if ident not in indice:
            raise ErroOperacao("posto_do_plano_sem_identificador")

        return indice[ident]

    itens = [
        {
            "id_externo": item["id_externo"],
            "categoria": item["categoria"],
        }
        for item in catalogo["itens"]
    ]

    metadados = [
        {
            "tipo": item["tipo"],
            "id_externo": externo(item),
            "codigo": item.get("codigo"),
            "valor": item["valor"],
        }
        for item in plano
    ]

    return canonico({
        "itens": sorted(itens, key=canonico),
        "metadados": sorted(metadados, key=canonico),
    })


def validar_backup(bruto, esperado, banco, fonte_sha256, agora=None):
    if not re.fullmatch(r"[0-9a-fA-F]{64}", esperado or ""):
        raise ErroOperacao("hash_backup_invalido")

    if hashlib.sha256(bruto).hexdigest() != esperado.lower():
        raise ErroOperacao("hash_backup_divergente")

    dados = json.loads(bruto)

    if (
        dados.get("versao") != 1
        or dados.get("estado", {}).get("banco") != banco
    ):
        raise ErroOperacao("backup_de_outro_destino")

    if dados["estado"].get("fonte_sha256") != fonte_sha256:
        raise ErroOperacao("backup_de_outra_fonte")

    capturado = datetime.fromisoformat(dados["capturado_em_utc"])
    agora = agora or datetime.now(timezone.utc)

    if (
        capturado.tzinfo is None
        or not (
            -timedelta(minutes=5)
            <= agora - capturado
            <= timedelta(hours=2)
        )
    ):
        raise ErroOperacao("backup_fora_da_janela_de_duas_horas")

    return dados


def api_github(env, caminho):
    repo = env.get("GITHUB_REPOSITORY", "")
    token = env.get("GITHUB_API_TOKEN", "")

    if (
        not re.fullmatch(
            r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",
            repo,
        )
        or not token
    ):
        raise ErroOperacao("contexto_github_ausente")

    requisicao = Request(
        "https://api.github.com/repos/" + repo + caminho,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "LitroDeOuro-OSM/1.2",
        },
    )

    with urlopen(requisicao, timeout=20) as resposta:
        bruto = resposta.read(2 * 1024 * 1024 + 1)

    if len(bruto) > 2 * 1024 * 1024:
        raise ErroOperacao("resposta_github_acima_do_limite")

    return json.loads(bruto)


def verificar_historico(env, consultar=api_github):
    if (
        env.get("GITHUB_REF") != "refs/heads/main"
        or env.get("GITHUB_RUN_ATTEMPT") != "1"
    ):
        raise ErroOperacao("escrita_exige_main_e_nova_execucao")

    atual = env.get("GITHUB_RUN_ID", "")

    if not atual.isdecimal():
        raise ErroOperacao("run_atual_invalido")

    dados = consultar(
        env,
        "/actions/workflows/osm_operacao.yml/"
        "runs?per_page=100&branch=main",
    )

    if not isinstance(dados.get("workflow_runs"), list):
        raise ErroOperacao("historico_github_invalido")

    anteriores = [
        run
        for run in dados["workflow_runs"]
        if run["id"] < int(atual)
    ]

    falhas = [
        run
        for run in anteriores
        if run.get("conclusion") not in ("success", "skipped")
    ]

    if falhas:
        ultima = max(falhas, key=lambda run: run["id"])

        if (
            env.get("OSM_FALHA_REVISADA_RUN_ID")
            != str(ultima["id"])
        ):
            raise ErroOperacao(
                "execucao_anterior_exige_conferencia_manual"
            )


def verificar_artefato(env, ident, consultar=api_github):
    if (
        not isinstance(ident, str)
        or not ident.isdecimal()
        or int(ident) <= 0
    ):
        raise ErroOperacao("artefato_backup_obrigatorio")

    dados = consultar(env, "/actions/artifacts/" + ident)

    nome = (
        "osm-backup-"
        + env.get("GITHUB_RUN_ID", "")
        + "-"
        + env.get("GITHUB_RUN_ATTEMPT", "")
    )

    if (
        dados.get("id") != int(ident)
        or dados.get("name") != nome
        or dados.get("expired") is not False
        or str(dados.get("workflow_run", {}).get("id"))
        != env.get("GITHUB_RUN_ID")
    ):
        raise ErroOperacao("backup_nao_confirmado_no_github")