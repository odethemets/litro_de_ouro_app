"""Catálogo OSM administrativo. Prévia por padrão; nunca atualiza postos existentes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sys
import tempfile

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from services import osm_service as osm
from services.grid_postos import classificar_lugar


def conectar():
    # Importacao tardia: testes somente da fonte nao precisam do MySQL.
    from services.database import get_db_connection

    return get_db_connection(
        time_zone="+00:00",
    )


def salvar_json(caminho, dados):
    """Escreve em arquivo temporário e substitui o destino ao concluir."""
    destino = Path(caminho)

    destino.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporario = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destino.parent,
            prefix=".osm-",
            suffix=".tmp",
            delete=False,
        ) as arquivo:
            temporario = Path(arquivo.name)

            json.dump(
                dados,
                arquivo,
                ensure_ascii=False,
                indent=2,
            )

            arquivo.write("\n")

        os.replace(
            temporario,
            destino,
        )

    finally:
        if (
            temporario is not None
            and temporario.exists()
        ):
            temporario.unlink()


def ler_json(caminho):
    with Path(caminho).open("rb") as arquivo:
        bruto = arquivo.read(
            16 * 1024 * 1024 + 1
        )

    if len(bruto) > 16 * 1024 * 1024:
        raise ValueError(
            "Arquivo excede 16 MiB."
        )

    return json.loads(bruto)


def normalizar_entrada(corpo, bbox=None):
    resultado, descartados = osm.converter_resposta(
        corpo,
        bbox,
    )

    # name deve existir na OSM.
    # Brand/operator isolados nao autorizam inclusao.
    nomes = {}

    for elemento in corpo["elements"]:
        if not isinstance(elemento, dict):
            continue

        tags = elemento.get("tags")

        if isinstance(tags, dict):
            nome = tags.get("name")

            ident = (
                f"osm:{elemento.get('type')}:"
                f"{elemento.get('id')}"
            )

            nomes[ident] = (
                isinstance(nome, str)
                and bool(nome.strip())
            )

    for lugar in resultado.lugares:
        nome = lugar["nome"].strip().casefold()

        lugar["_nome_osm_confirmado"] = (
            nomes.get(lugar["id_externo"], False)
            and nome not in (
                "posto",
                "posto sem nome",
                "eletroposto sem nome",
                "sem nome",
            )
        )

    return resultado.lugares, descartados


def processar_catalogo(
    cursor,
    lugares,
    aplicar=False,
):
    """Somente INSERT de novos com nome. Sem UPDATE, DELETE ou vínculos."""
    unicos = {}
    duplicados = 0

    for lugar in lugares:
        ident = lugar["id_externo"]

        if ident in unicos:
            if unicos[ident] != lugar:
                raise ValueError(
                    "Identificador OSM com dados conflitantes."
                )

            duplicados += 1

        unicos[ident] = lugar

    if len(unicos) > 3000:
        raise ValueError(
            "Catálogo excede o limite administrativo de 3000 elementos."
        )

    # Compara todos os candidatos nomeados ANTES de inserir.
    # Objetos OSM proximos ficam para revisao independentemente da ordem.
    virtuais = {
        "entrada:" + ident: dict(
            lugar,
            id="entrada:" + ident,
            mapbox_id=ident,
        )
        for ident, lugar in unicos.items()
        if lugar.get("_nome_osm_confirmado") is True
    }

    relatorio = {
        "modo": "aplicar" if aplicar else "dry-run",
        "novos": 0,
        "existentes": 0,
        "ambiguos": 0,
        "ignorados": 0,
        "inseridos": 0,
        "vinculados": 0,
        "duplicados_na_entrada": duplicados,
        "itens": [],
    }

    planos = []

    for ident, lugar in unicos.items():
        outros = {
            chave: valor
            for chave, valor in virtuais.items()
            if chave != "entrada:" + ident
        }

        item = classificar_lugar(
            cursor,
            lugar,
            outros,
        )

        item.pop(
            "_registro_vinculo",
            None,
        )

        if (
            item["categoria"] == "novos"
            and lugar.get("_nome_osm_confirmado") is not True
        ):
            item.update(
                categoria="ignorados",
                acao="ignorar_sem_nome",
                motivo="Sem name válido na OSM; não será importado.",
            )

        elif item["acao"] == "vincular":
            item.update(
                acao="manter_sem_vincular",
                motivo=(
                    "Cadastro manual compatível; "
                    "vínculo automático desativado."
                ),
            )

        relatorio[item["categoria"]] += 1
        relatorio["itens"].append(item)

        if item["categoria"] == "novos":
            planos.append(
                (lugar, item)
            )

    if aplicar:
        for lugar, item in planos:
            cursor.execute(
                """
                INSERT INTO postos (
                    mapbox_id,
                    nome,
                    endereco,
                    bairro,
                    cidade,
                    uf,
                    latitude,
                    longitude,
                    horario_funcionamento,
                    tipo_posto
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
                """,
                (
                    lugar["id_externo"],
                    lugar["nome"],
                    lugar["endereco"],
                    lugar["bairro"],
                    lugar["cidade"],
                    lugar["uf"],
                    lugar["latitude"],
                    lugar["longitude"],
                    lugar["horario_funcionamento"],
                    lugar["tipo_posto"],
                ),
            )

            item["posto_id"] = cursor.lastrowid
            relatorio["inseridos"] += 1

    return relatorio


def executar(
    lugares,
    get_conn=conectar,
    aplicar=False,
):
    conn = get_conn()

    try:
        with conn.cursor() as cursor:
            if aplicar:
                cursor.execute(
                    "SELECT GET_LOCK('litro_osm_batch', 0) AS adquirido"
                )

                linha = cursor.fetchone()

                adquirido = (
                    linha.get("adquirido")
                    if isinstance(linha, dict)
                    else linha[0]
                )

                if adquirido != 1:
                    raise RuntimeError(
                        "Outro importador está ativo."
                    )

            relatorio = processar_catalogo(
                cursor,
                lugares,
                aplicar=aplicar,
            )

        if aplicar:
            conn.commit()
        else:
            conn.rollback()

        return relatorio

    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass

        raise

    finally:
        conn.close()


def main(
    argv=None,
    get_conn=conectar,
):
    parser = argparse.ArgumentParser(
        description=__doc__,
    )

    origem = parser.add_mutually_exclusive_group(
        required=True,
    )

    origem.add_argument(
        "--teste-conexao",
        action="store_true",
        help="Consulta mínima, sem MySQL",
    )

    origem.add_argument(
        "--joao-pessoa",
        action="store_true",
        help="Buscar pela área administrativa OSM",
    )

    origem.add_argument(
        "--arquivo",
        help="JSON Overpass salvo anteriormente",
    )

    origem.add_argument(
        "--buscar",
        action="store_true",
        help="Prévia legada por bbox, sem aplicação",
    )

    parser.add_argument(
        "--bbox",
        help=(
            "sul,oeste,norte,leste; "
            "use --bbox=-7.12,-34.87,-7.10,-34.85"
        ),
    )

    modo = parser.add_mutually_exclusive_group()

    modo.add_argument(
        "--somente-fonte",
        action="store_true",
        help="Não conectar ao MySQL",
    )

    modo.add_argument(
        "--dry-run",
        action="store_true",
        help="Prévia no banco; é o padrão",
    )

    modo.add_argument(
        "--aplicar",
        action="store_true",
        help="Inserir apenas novos com nome",
    )

    parser.add_argument(
        "--tentativas",
        type=int,
        choices=range(1, 4),
        default=2,
    )

    parser.add_argument(
        "--max-espera",
        type=int,
        default=120,
    )

    parser.add_argument(
        "--salvar-json",
        help="Salvar resposta bruta para repetição offline",
    )

    parser.add_argument(
        "--relatorio",
        help="Salvar relatório JSON também em arquivo",
    )

    args = parser.parse_args(argv)

    if not 0 <= args.max_espera <= 300:
        parser.error(
            "--max-espera deve estar entre 0 e 300"
        )

    if args.buscar and not args.bbox:
        parser.error(
            "--buscar exige --bbox"
        )

    if args.bbox and not (
        args.buscar or args.arquivo
    ):
        parser.error(
            "--bbox é permitido somente com --buscar ou --arquivo"
        )

    if args.teste_conexao and (
        args.aplicar
        or args.salvar_json
        or args.bbox
    ):
        parser.error(
            "--teste-conexao não importa nem exporta o catálogo"
        )

    try:
        from dotenv import load_dotenv

        load_dotenv(
            BACKEND / ".env"
        )

    except ModuleNotFoundError:
        pass

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    relatorio = {
        "status": "iniciado",
        "fonte": "OpenStreetMap",
        "atribuicao": osm.ATRIBUICAO,
        "licenca_url": osm.LICENCA_URL,
        "iniciado_em_utc": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    codigo = 0

    try:
        if args.relatorio:
            salvar_json(
                args.relatorio,
                relatorio,
            )

        if args.teste_conexao:
            meta = osm.testar_conexao(
                args.tentativas,
                args.max_espera,
            )

            relatorio.update(
                status="ok",
                etapa="teste_conexao",
                mysql_consultado=False,
                **meta,
            )

        else:
            bbox = (
                osm._validar_bbox(
                    args.bbox.split(",")
                )
                if args.bbox
                else None
            )

            municipio = None

            if args.joao_pessoa:
                corpo, meta = osm.buscar_municipio(
                    args.tentativas,
                    args.max_espera,
                )

                municipio = osm.validar_municipio(
                    corpo
                )

                relatorio.update(meta)

            elif args.arquivo:
                corpo = ler_json(
                    args.arquivo
                )

                if (
                    isinstance(corpo, dict)
                    and isinstance(
                        corpo.get("elements"),
                        list,
                    )
                    and any(
                        isinstance(elemento, dict)
                        and elemento.get("type") == "area"
                        for elemento in corpo["elements"]
                    )
                ):
                    municipio = osm.validar_municipio(
                        corpo
                    )

                # JSON antigo sem area: somente previa dentro da caixa legada.
                if municipio is None and bbox is None:
                    bbox = osm.area_configurada()

            else:
                a, b, c, d = osm.area_configurada()

                if not (
                    a <= bbox[0] < bbox[2] <= c
                    and b <= bbox[1] < bbox[3] <= d
                ):
                    raise ValueError(
                        "Bbox fora da área de prévia configurada."
                    )

                corpo, meta = osm.consultar_com_contingencia(
                    osm.montar_consulta(bbox),
                    args.tentativas,
                    args.max_espera,
                )

                relatorio.update(meta)

            if args.aplicar and municipio is None:
                raise ValueError(
                    "Aplicação exige resposta com a área "
                    "administrativa de João Pessoa."
                )

            lugares, descartados = normalizar_entrada(
                corpo,
                bbox,
            )

            if municipio and not lugares:
                raise ValueError(
                    "A área foi encontrada, "
                    "mas nenhum posto válido foi recebido."
                )

            relatorio.update(
                municipio=municipio,
                total_lidos=len(lugares),
                descartados_na_leitura=descartados,
                escopo_validado=(
                    "area_osm"
                    if municipio
                    else "previa_bbox"
                ),
            )

            if args.salvar_json:
                salvar_json(
                    args.salvar_json,
                    corpo,
                )

            if args.somente_fonte:
                relatorio.update(
                    status="ok",
                    etapa="somente_fonte",
                    mysql_consultado=False,
                    nomeados=sum(
                        lugar["_nome_osm_confirmado"]
                        for lugar in lugares
                    ),
                )

            else:
                relatorio["gravacao_solicitada"] = args.aplicar

                resultado = executar(
                    lugares,
                    get_conn=get_conn,
                    aplicar=args.aplicar,
                )

                relatorio.update(
                    resultado,
                    status="ok",
                    mysql_consultado=True,
                )

    except osm.OSMIndisponivel as erro:
        codigo = 2

        relatorio.update(
            status="falha_fonte",
            erro=str(erro),
            status_http=erro.status_http,
        )

    except Exception as erro:
        codigo = 3

        relatorio.update(
            status="falha",
            tipo_erro=type(erro).__name__,
        )

        if isinstance(erro, ValueError):
            relatorio["orientacao"] = (
                "Confira argumentos, JSON, área "
                "e variáveis de configuração."
            )

        if args.aplicar:
            relatorio["gravacao"] = (
                "nao_confirmada_verifique_banco_antes_de_repetir"
            )

        logging.error(
            "Rotina interrompida: tipo=%s. "
            "Dados de conexão foram omitidos.",
            type(erro).__name__,
        )

    relatorio["finalizado_em_utc"] = datetime.now(
        timezone.utc
    ).isoformat()

    print(
        json.dumps(
            relatorio,
            ensure_ascii=False,
            indent=2,
        )
    )

    if args.relatorio:
        try:
            salvar_json(
                args.relatorio,
                relatorio,
            )

        except OSError:
            logging.error(
                "Não foi possível salvar o relatório; "
                "confira a saída do terminal."
            )

            codigo = 3

    return codigo


if __name__ == "__main__":
    raise SystemExit(main())