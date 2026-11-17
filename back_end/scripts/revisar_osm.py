"""Prévia municipal OSM com JSON/hash/relatório; nenhum modo grava no banco."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MAX_BYTES = 16 * 1024 * 1024
ATRIBUICAO = "© OpenStreetMap contributors — ODbL"
LICENCA = "https://www.openstreetmap.org/copyright"


# Reutiliza o importador sem executar seu main ou seu modo aplicar.
def dependencias():
    osm = importlib.import_module("services.osm_service")
    importador = importlib.import_module("scripts.importar_postos_osm")
    banco = importlib.import_module("services.database")

    inspect.signature(osm.validar_municipio).bind({})
    inspect.signature(importador.normalizar_entrada).bind({})
    inspect.signature(importador.processar_catalogo).bind(
        object(), [], aplicar=False
    )

    return osm, importador, banco.get_db_connection


def instante():
    return datetime.now(timezone.utc).isoformat()


# Cada execução usa uma pasta nova, sem sobrescrever relatórios.
def gravar(pasta, nome, valor):
    bruto = (
        json.dumps(
            valor,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ) + "\n"
    ).encode("utf-8")

    with (pasta / nome).open("xb") as arquivo:
        arquivo.write(bruto)

    return hashlib.sha256(bruto).hexdigest()


def rejeitar_constante(_valor):
    raise ValueError("Número JSON não suportado.")


# Registra a idade da fonte sem presumir que um arquivo salvo é recente.
def data_base(corpo):
    meta = corpo.get("osm3s")
    valor = meta.get("timestamp_osm_base") if isinstance(meta, dict) else None

    if not isinstance(valor, str):
        return None

    try:
        data = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        if data.tzinfo is None:
            return None
        return data.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


# O hash representa exatamente os bytes arquivados.
def ler_arquivo(caminho):
    with Path(caminho).open("rb") as arquivo:
        bruto = arquivo.read(MAX_BYTES + 1)

    if not bruto or len(bruto) > MAX_BYTES:
        raise ValueError("Fonte vazia ou acima de 16 MiB.")

    return bruto


# Defesa adicional para as consultas conhecidas do classificador.
class CursorPrevia:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, parametros=()):
        consulta = sql.strip()
        proibido = (
            r"\b(?:FOR\s+(?:UPDATE|SHARE)|LOCK\s+IN\s+SHARE\s+MODE|"
            r"GET_LOCK|RELEASE_LOCK|INTO|SLEEP|BENCHMARK)\b"
        )

        if (
            not re.match(r"^SELECT\b", consulta, re.I)
            or ";" in consulta
            or re.search(proibido, consulta, re.I)
        ):
            raise ValueError(
                "A prévia aceita apenas SELECT sem gravação "
                "ou trava explícita."
            )

        return self._cursor.execute(sql, parametros)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


# Confere o destino antes de executar o classificador existente.
def prever(lugares, esperado, conectar, importador):
    conn, erro, resultado = None, None, None

    try:
        conn = conectar(read_only=True, time_zone="+00:00")

        with conn.cursor() as original:
            cursor = CursorPrevia(original)
            cursor.execute("SELECT DATABASE() AS banco")
            registro = cursor.fetchone()

            if (
                not isinstance(registro, dict)
                or registro.get("banco") != esperado
            ):
                raise ValueError("Banco diferente do esperado.")

            resultado = importador.processar_catalogo(
                cursor,
                lugares,
                aplicar=False,
            )

        if not isinstance(resultado, dict) or any(
            type(resultado.get(k)) is not int or resultado[k] != 0
            for k in ("inseridos", "vinculados")
        ):
            raise ValueError(
                "O importador não devolveu uma prévia compatível."
            )

    except Exception as falha:
        erro = falha

    finally:
        if conn is not None:
            for acao in (conn.rollback, conn.close):
                try:
                    acao()
                except Exception as falha:
                    if erro is None:
                        erro = falha

    if erro is not None:
        raise erro from None

    return resultado


# Só consulta o banco depois de validar e arquivar a fonte.
def executar(args, osm, importador, conectar):
    pasta = Path(args.saida)
    pasta.mkdir(parents=True, exist_ok=False)

    relatorio = {
        "status": "iniciado",
        "iniciado_em_utc": instante(),
        "modo": "somente_fonte" if args.somente_fonte else "previa",
        "origem": "arquivo" if args.arquivo else "overpass_municipal",
        "atribuicao": ATRIBUICAO,
        "licenca_url": LICENCA,
        "gravacao_habilitada": False,
        "consulta_banco_solicitada": False,
    }
    hashes, etapa = {}, "ler_fonte"

    try:
        if args.arquivo:
            bruto = ler_arquivo(args.arquivo)
        else:
            corpo, _meta = osm.buscar_municipio(
                tentativas=args.tentativas,
                max_espera=args.max_espera,
            )
            bruto = (
                json.dumps(
                    corpo,
                    ensure_ascii=False,
                    allow_nan=False,
                ) + "\n"
            ).encode("utf-8")

            if len(bruto) > MAX_BYTES:
                raise ValueError("Fonte acima de 16 MiB.")

        etapa = "validar_fonte"
        corpo = json.loads(bruto, parse_constant=rejeitar_constante)
        municipio = osm.validar_municipio(corpo)

        if (
            municipio.get("codigo_ibge") != "2507507"
            or len(corpo["elements"]) > 5000
        ):
            raise ValueError(
                "Município ou tamanho da resposta incompatível."
            )

        lugares, descartados = importador.normalizar_entrada(corpo)

        if not isinstance(lugares, list) or not 1 <= len(lugares) <= 3000:
            raise ValueError(
                "Quantidade de postos normalizados incompatível."
            )

        etapa = "arquivar_fonte"
        with (pasta / "fonte.json").open("xb") as arquivo:
            arquivo.write(bruto)

        hashes["fonte.json"] = hashlib.sha256(bruto).hexdigest()

        relatorio.update(
            municipio=municipio,
            sha256_fonte=hashes["fonte.json"],
            data_base_fonte_utc=data_base(corpo),
            postos_normalizados=len(lugares),
            descartados_na_leitura=descartados,
        )

        if not args.somente_fonte:
            etapa = "comparar_catalogo"
            relatorio["consulta_banco_solicitada"] = True
            relatorio["previa"] = prever(
                lugares,
                args.banco,
                conectar,
                importador,
            )
            relatorio["destino_conferido"] = True

        relatorio.update(status="ok", etapa="concluido")

    except Exception as erro:
        codigo = getattr(erro, "status_http", None)
        relatorio.update(
            status="falha",
            etapa=etapa,
            erro_tipo=type(erro).__name__,
            status_http=codigo if type(codigo) is int else None,
        )

    relatorio["finalizado_em_utc"] = instante()
    hashes["relatorio.json"] = gravar(
        pasta,
        "relatorio.json",
        relatorio,
    )

    # Gravado por último para identificar uma execução com artefatos completos.
    gravar(pasta, "manifesto.json", {
        "status": relatorio["status"],
        "sha256": hashes,
        "gravacao_habilitada": False,
        "atribuicao": ATRIBUICAO,
        "licenca_url": LICENCA,
    })

    resumo = {
        k: relatorio[k] for k in (
            "status", "modo", "etapa", "postos_normalizados",
            "sha256_fonte", "erro_tipo", "status_http",
        ) if k in relatorio
    }

    if "previa" in relatorio:
        resumo["classificacao"] = {
            k: relatorio["previa"].get(k) for k in (
                "novos", "existentes", "ambiguos",
                "ignorados", "inseridos", "vinculados",
            )
        }

    return {
        **resumo,
        "pasta": str(pasta),
        "gravacao_habilitada": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    origem = parser.add_mutually_exclusive_group(required=True)
    origem.add_argument("--arquivo")
    origem.add_argument("--joao-pessoa", action="store_true")

    parser.add_argument("--somente-fonte", action="store_true")
    parser.add_argument("--banco")
    parser.add_argument(
        "--saida",
        required=True,
        help="Pasta nova para JSON, relatório e hashes.",
    )
    parser.add_argument(
        "--tentativas",
        type=int,
        choices=(1, 2, 3),
        default=1,
    )
    parser.add_argument("--max-espera", type=int, default=0)
    args = parser.parse_args(argv)

    if not 0 <= args.max_espera <= 300:
        parser.error("--max-espera deve estar entre 0 e 300.")

    if args.somente_fonte and args.banco:
        parser.error("--somente-fonte não utiliza --banco.")

    if not args.somente_fonte and (
        not args.banco
        or not 1 <= len(args.banco) <= 64
        or args.banco != args.banco.strip()
        or any(ord(c) < 32 or ord(c) == 127 for c in args.banco)
    ):
        parser.error(
            "A prévia exige --banco com o nome exato do destino."
        )

    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False)
        osm, importador, conectar = dependencias()
        resultado = executar(args, osm, importador, conectar)

    except Exception as erro:
        resultado = {
            "status": "falha_preparacao_ou_artefatos",
            "erro_tipo": type(erro).__name__,
            "gravacao_habilitada": False,
        }

    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0 if resultado["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())