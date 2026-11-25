"""Referências ANP estimadas, separadas dos preços observados."""

import csv
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import io
from pathlib import Path
import re
import unicodedata


FONTE_SHA256 = (
    "f6ca4ecb4dd848888b95871a49901faf57"
    "dd71ef52d19d0f81a9780199de383b"
)

INICIO = date(2026, 11, 15)
FIM = date(2026, 11, 21)

MEDIAS = {
    "gasolina_comum": (
        "Gasolina Comum",
        "L",
        "6.20",
        19,
    ),
    "gasolina_aditivada": (
        "Gasolina Aditivada",
        "L",
        "6.51",
        12,
    ),
    "etanol": (
        "Etanol",
        "L",
        "4.31",
        15,
    ),
    "gnv": (
        "GNV",
        "m³",
        "4.99",
        4,
    ),
}

CAMPOS = {
    "posto_id",
    "nome",
    "tipo_posto",
    "cidade",
    "uf",
    "combustivel_codigo",
    "combustivel_nome",
    "unidade",
    "disponivel_manual",
    "disponivel_osm",
    "disponivel",
    "registo_id_atual",
    "preco_registrado",
    "data_registro",
}


class ErroMedias(ValueError):
    pass


def _flag(valor):
    if valor in (None, "", "NULL"):
        return None

    if valor in (0, "0", False):
        return False

    if valor in (1, "1", True):
        return True

    raise ErroMedias(
        "Flag de disponibilidade inválida."
    )


def _id(valor):
    if (
        isinstance(valor, bool)
        or not re.fullmatch(
            r"[1-9][0-9]{0,9}",
            str(valor),
        )
    ):
        raise ErroMedias(
            "Identificador de posto ou registro inválido."
        )

    numero = int(valor)

    if numero > 2147483647:
        raise ErroMedias(
            "Identificador fora do limite."
        )

    return numero


def _preco(valor):
    try:
        numero = Decimal(str(valor))

        if (
            not numero.is_finite()
            or not Decimal("0.01")
            <= numero
            <= Decimal("25.00")
            or numero != numero.quantize(
                Decimal("0.01")
            )
        ):
            raise ErroMedias("Preço inválido.")

        return numero

    except (InvalidOperation, ValueError):
        raise ErroMedias(
            "Preço inválido."
        ) from None


def carregar_snapshot(arquivo, sha256):
    if not re.fullmatch(
        r"[0-9a-f]{64}",
        sha256,
    ):
        raise ErroMedias(
            "SHA-256 do snapshot inválido."
        )

    bruto = Path(arquivo).read_bytes()

    if (
        len(bruto) > 4 * 1024 * 1024
        or hashlib.sha256(bruto).hexdigest()
        != sha256
    ):
        raise ErroMedias(
            "O arquivo diverge do hash esperado "
            "ou excede o limite."
        )

    texto = bruto.decode("utf-8-sig")

    dialect = csv.Sniffer().sniff(
        texto[:8000],
        delimiters=",;\t",
    )

    leitor = csv.DictReader(
        io.StringIO(texto),
        dialect=dialect,
    )

    cabecalho = leitor.fieldnames or []

    if (
        set(cabecalho) != CAMPOS
        or len(cabecalho) != len(CAMPOS)
    ):
        raise ErroMedias(
            "Colunas do snapshot divergentes."
        )

    linhas = list(leitor)

    if not 1 <= len(linhas) <= 8000:
        raise ErroMedias(
            "Quantidade de linhas inválida."
        )

    pares = set()
    postos = {}
    resultado = []

    for linha in linhas:
        if (
            None in linha
            or any(
                valor is None
                for valor in linha.values()
            )
        ):
            raise ErroMedias(
                "Linha CSV incompleta "
                "ou com campos extras."
            )

        posto_id = _id(linha["posto_id"])
        codigo = linha["combustivel_codigo"]

        if (
            codigo not in MEDIAS
            or (posto_id, codigo) in pares
        ):
            raise ErroMedias(
                "Produto desconhecido ou par "
                "posto/produto repetido."
            )

        nome, unidade, _, _ = MEDIAS[codigo]

        if (
            linha["combustivel_nome"] != nome
            or linha["unidade"] != unidade
        ):
            raise ErroMedias(
                "Nome ou unidade do combustível "
                "divergente."
            )

        identificacao = (
            linha["nome"],
            linha["tipo_posto"],
            linha["cidade"],
            linha["uf"],
        )

        if (
            not linha["nome"].strip()
            or (
                posto_id in postos
                and postos[posto_id]
                != identificacao
            )
        ):
            raise ErroMedias(
                "Metadados do posto ausentes "
                "ou inconsistentes."
            )

        postos[posto_id] = identificacao

        manual = _flag(
            linha["disponivel_manual"]
        )

        osm = _flag(
            linha["disponivel_osm"]
        )

        disponivel = _flag(
            linha["disponivel"]
        )

        disponibilidade_esperada = (
            manual
            if manual is not None
            else osm
        )

        if disponivel != disponibilidade_esperada:
            raise ErroMedias(
                "Disponibilidade incompatível "
                "com manual/OSM."
            )

        possui_registro = (
            linha["registo_id_atual"]
            not in ("", "NULL")
        )

        if possui_registro:
            _id(linha["registo_id_atual"])
            _preco(linha["preco_registrado"])
            datetime.fromisoformat(
                linha["data_registro"]
            )

        elif (
            linha["preco_registrado"]
            not in ("", "NULL")
            or linha["data_registro"]
            not in ("", "NULL")
        ):
            raise ErroMedias(
                "Preço/data sem identificador "
                "do registro."
            )

        resultado.append(
            dict(
                linha,
                posto_id=posto_id,
                disponivel=disponivel,
                possui_registro=possui_registro,
            )
        )

        pares.add((posto_id, codigo))

    for posto_id in postos:
        produtos_do_posto = {
            codigo
            for pid, codigo in pares
            if pid == posto_id
        }

        if produtos_do_posto != set(MEDIAS):
            raise ErroMedias(
                "Snapshot deve conter os quatro "
                "produtos por posto."
            )

    return resultado


def validar_referencia(registro):
    codigo = registro.get(
        "combustivel_codigo"
    )

    if codigo not in MEDIAS:
        raise ErroMedias(
            "Produto da referência não suportado."
        )

    _, _, valor, amostra = MEDIAS[codigo]

    if (
        _preco(registro.get("preco"))
        != Decimal(valor)
        or registro.get("municipio_referencia")
        != "JOAO PESSOA"
        or registro.get("uf_referencia")
        != "PB"
        or registro.get("periodo_inicio")
        != INICIO
        or registro.get("periodo_fim")
        != FIM
        or registro.get("amostra")
        != amostra
        or isinstance(
            registro.get("amostra"),
            bool,
        )
        or registro.get("fonte_sha256")
        != FONTE_SHA256
        or not re.fullmatch(
            r"[0-9a-f]{64}",
            str(
                registro.get(
                    "snapshot_sha256",
                    "",
                )
            ),
        )
    ):
        raise ErroMedias(
            "Referência armazenada diverge "
            "da fonte revisada."
        )

    _id(registro.get("posto_id"))

    return {
        "fonte": "ANP",
        "tipo": "media_municipal",
        "municipio": "JOAO PESSOA",
        "uf": "PB",
        "periodo_inicio": INICIO.isoformat(),
        "periodo_fim": FIM.isoformat(),
        "amostra": amostra,
    }


def consultar_referencias(cursor, ids):
    marcadores = ",".join(
        ["%s"] * len(ids)
    )

    cursor.execute(
        "SELECT "
        "posto_id,"
        "combustivel_codigo,"
        "preco,"
        "municipio_referencia,"
        "uf_referencia,"
        "periodo_inicio,"
        "periodo_fim,"
        "amostra,"
        "fonte_sha256,"
        "snapshot_sha256 "
        "FROM referencias_medias_iniciais "
        "WHERE posto_id IN ("
        + marcadores
        + ")",
        ids,
    )

    resultado = {}

    for registro in cursor.fetchall():
        chave = (
            registro["posto_id"],
            registro["combustivel_codigo"],
        )

        if chave in resultado:
            raise ErroMedias(
                "Referência repetida no banco."
            )

        resultado[chave] = dict(
            registro,
            estimativa=validar_referencia(
                registro
            ),
        )

    return resultado


def carregar_medias(
    conn,
    migracoes,
    snapshot,
    sha256,
    *,
    banco,
    aplicar=False,
):
    from services.migrations import run

    try:
        if (
            not snapshot
            or not re.fullmatch(
                r"[0-9a-f]{64}",
                sha256,
            )
        ):
            raise ErroMedias(
                "Snapshot vazio ou hash inválido."
            )

        estado = run(
            conn,
            migracoes,
            expected_database=banco,
        )

        if any(
            migracao["estado"] != "aplicada"
            for migracao in estado["migracoes"]
        ):
            raise ErroMedias(
                "Aplique e confira a migração 006 "
                "antes da carga."
            )

        ids = sorted({
            linha["posto_id"]
            for linha in snapshot
        })

        marcadores = ",".join(
            ["%s"] * len(ids)
        )

        if aplicar:
            conn.rollback()

            with conn.cursor() as cursor:
                if (
                    "tidb"
                    in estado[
                        "versao_servidor"
                    ].lower()
                ):
                    cursor.execute(
                        "BEGIN PESSIMISTIC"
                    )
                else:
                    cursor.execute(
                        "START TRANSACTION"
                    )

        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT "
                "id,nome,tipo_posto,cidade,uf "
                "FROM postos "
                "WHERE id IN ("
                + marcadores
                + ") ORDER BY id"
                + (
                    " FOR UPDATE"
                    if aplicar
                    else ""
                ),
                ids,
            )

            postos = {
                registro["id"]: registro
                for registro in cursor.fetchall()
            }

            if set(postos) != set(ids):
                raise ErroMedias(
                    "Um posto do snapshot deixou "
                    "de existir; refaça a prévia."
                )

            cursor.execute(
                "SELECT "
                "posto_id,"
                "combustivel_codigo,"
                "disponivel_manual,"
                "disponivel_osm "
                "FROM postos_combustiveis "
                "WHERE posto_id IN ("
                + marcadores
                + ")"
                + (
                    " FOR UPDATE"
                    if aplicar
                    else ""
                ),
                ids,
            )

            ofertas = {
                (
                    registro["posto_id"],
                    registro[
                        "combustivel_codigo"
                    ],
                ): registro
                for registro in cursor.fetchall()
            }

            cursor.execute(
                "SELECT "
                "posto_id,tipo_combustivel "
                "FROM registos_preco "
                "WHERE posto_id IN ("
                + marcadores
                + ")",
                ids,
            )

            observados = {
                (
                    registro["posto_id"],
                    registro[
                        "tipo_combustivel"
                    ],
                )
                for registro in cursor.fetchall()
            }

            referencias = consultar_referencias(
                cursor,
                ids,
            )

            acoes = []

            for linha in snapshot:
                posto_id = linha["posto_id"]
                codigo = linha[
                    "combustivel_codigo"
                ]

                posto = postos[posto_id]

                if (
                    posto["nome"]
                    != linha["nome"]
                    or posto["tipo_posto"]
                    != linha["tipo_posto"]
                ):
                    raise ErroMedias(
                        "Identidade/tipo de posto "
                        "alterado; refaça o snapshot."
                    )

                cidade_bruta = (
                    posto.get("cidade") or ""
                )

                cidade = "".join(
                    caractere
                    for caractere
                    in unicodedata.normalize(
                        "NFKD",
                        cidade_bruta,
                    )
                    if not unicodedata.combining(
                        caractere
                    )
                ).strip().upper()

                uf = (
                    posto.get("uf") or ""
                ).strip().upper()

                if (
                    cidade
                    not in ("", "JOAO PESSOA")
                    or uf not in ("", "PB")
                ):
                    raise ErroMedias(
                        "Posto declara outra região; "
                        "revisar o escopo da carga."
                    )

                nome, _, preco, amostra = (
                    MEDIAS[codigo]
                )

                oferta = ofertas.get(
                    (posto_id, codigo),
                    {},
                )

                manual = _flag(
                    oferta.get(
                        "disponivel_manual"
                    )
                )

                osm = _flag(
                    oferta.get(
                        "disponivel_osm"
                    )
                )

                disponivel = (
                    manual
                    if manual is not None
                    else osm
                )

                if (
                    posto["tipo_posto"]
                    != "Convencional"
                ):
                    acao = "ignorar_tipo_posto"

                elif (
                    disponivel is False
                    or linha["disponivel"]
                    is False
                ):
                    acao = "ignorar_indisponivel"

                elif (
                    linha["possui_registro"]
                    or (posto_id, nome)
                    in observados
                ):
                    acao = (
                        "preservar_preco_registrado"
                    )

                elif (
                    posto_id,
                    codigo,
                ) in referencias:
                    acao = "referencia_ja_existe"

                else:
                    acao = (
                        "inserir_referencia_estimada"
                    )

                    if aplicar:
                        cursor.execute(
                            """
                            INSERT INTO
                                referencias_medias_iniciais
                            (
                                posto_id,
                                combustivel_codigo,
                                preco,
                                municipio_referencia,
                                uf_referencia,
                                periodo_inicio,
                                periodo_fim,
                                amostra,
                                fonte_sha256,
                                snapshot_sha256,
                                criado_em
                            )
                            VALUES (
                                %s,
                                %s,
                                %s,
                                'JOAO PESSOA',
                                'PB',
                                %s,
                                %s,
                                %s,
                                %s,
                                %s,
                                UTC_TIMESTAMP()
                            )
                            """,
                            (
                                posto_id,
                                codigo,
                                Decimal(preco),
                                INICIO,
                                FIM,
                                amostra,
                                FONTE_SHA256,
                                sha256,
                            ),
                        )

                acoes.append({
                    "posto_id": posto_id,
                    "codigo": codigo,
                    "acao": acao,
                    "media": preco,
                })

        if aplicar:
            try:
                conn.commit()

            except Exception:
                raise ErroMedias(
                    "Commit sem confirmação. "
                    "Confira com --dry-run "
                    "antes de repetir; "
                    "a carga pode ter sido salva."
                ) from None

        else:
            conn.rollback()

        return {
            "status": "ok",
            "modo": (
                "aplicar"
                if aplicar
                else "dry-run"
            ),
            "banco": banco,
            "postos": len(ids),
            "snapshot_sha256": sha256,
            "fonte_sha256": FONTE_SHA256,
            "resumo": dict(
                Counter(
                    registro["acao"]
                    for registro in acoes
                )
            ),
            "acoes": acoes,
            "altera_registos_preco": False,
            "gera_karma": False,
            "altera_disponibilidade": False,
        }

    except Exception:
        conn.rollback()
        raise