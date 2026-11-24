"""Leitura limitada de CSV/XLSX individuais; sem rede, Flask ou banco."""
import csv
import hashlib
import io
from pathlib import Path
import re
from zipfile import BadZipFile, ZipFile

from .contrato import ErroANP, normalizar, texto

MAX_BYTES = 32 * 1024 * 1024
MAX_LINHAS = 200_000
MAX_CELULA = 2000
MAX_DESCOMPACTADO = 128 * 1024 * 1024

COLUNAS = (
    "uf",
    "municipio",
    "cnpj",
    "revenda",
    "endereco",
    "numero",
    "bairro",
    "cep",
    "bandeira",
    "produto_original",
    "preco_venda_original",
    "unidade_original",
    "data_coleta",
)

APELIDOS = {
    "ESTADO": "uf",
    "MUNICIPIO": "municipio",
    "RAZAO": "revenda",
    "RAZAO SOCIAL": "revenda",
    "PRODUTO": "produto_original",
    "PRECO DE REVENDA": "preco_venda_original",
    "UNIDADE DE MEDIDA": "unidade_original",
    "DATA DA COLETA": "data_coleta",
    "NUMERO": "numero",
}


def chave_coluna(valor):
    chave = normalizar(valor).replace("_", " ")

    return APELIDOS.get(
        chave,
        chave.lower().replace(" ", "_"),
    )


def _cabecalho(linha):
    chaves = [chave_coluna(v) for v in linha]

    # Remove apenas colunas vazias formatadas após a tabela.
    while chaves and not chaves[-1]:
        chaves.pop()

    if set(COLUNAS).issubset(chaves):
        if len(chaves) != len(set(chaves)):
            raise ErroANP(
                "Cabeçalho contém colunas duplicadas ou ambíguas."
            )

        return chaves

    return None


def _linhas(iterador, aba, acumuladas):
    cabecalho = None

    for numero, valores in enumerate(iterador, 1):
        if numero > MAX_LINHAS + 25:
            raise ErroANP(
                "Planilha excede o limite de linhas físicas."
            )

        if numero <= 25 and cabecalho is None:
            cabecalho = _cabecalho(valores)
            continue

        if cabecalho is None:
            break

        if all(
            v is None or texto(v) == ""
            for v in valores
        ):
            continue

        if len(acumuladas) >= MAX_LINHAS:
            raise ErroANP(
                "Planilha excede o limite de linhas."
            )

        if any(
            len(texto(v)) > MAX_CELULA
            for v in valores
        ):
            raise ErroANP(
                "Célula acima do limite de caracteres."
            )

        # Não descarta conteúdo além do cabeçalho.
        if any(
            texto(v)
            for v in valores[len(cabecalho):]
        ):
            raise ErroANP(
                "Linha contém campos sem cabeçalho."
            )

        dado = {
            chave: valores[i] if i < len(valores) else None
            for i, chave in enumerate(cabecalho)
        }

        if texto(dado.get("")):
            raise ErroANP(
                "Linha contém campo sem cabeçalho."
            )

        acumuladas.append(
            {
                "dados": dado,
                "aba_lida": aba,
                "linha_lida": numero,
            }
        )

    return cabecalho is not None


def ler_arquivo(caminho, encoding="utf-8-sig"):
    caminho = Path(caminho)

    with caminho.open("rb") as arquivo:
        bruto = arquivo.read(MAX_BYTES + 1)

    if len(bruto) > MAX_BYTES or not bruto:
        raise ErroANP(
            "Arquivo vazio ou acima de 32 MiB."
        )

    registros = []
    abas = []
    formato = caminho.suffix.lower()

    if formato == ".csv":
        if encoding not in ("utf-8-sig", "cp1252"):
            raise ErroANP(
                "Codificação não suportada."
            )

        try:
            conteudo = bruto.decode(
                encoding,
                errors="strict",
            )
        except UnicodeDecodeError:
            raise ErroANP(
                "Codificação incompatível. Use --encoding cp1252 "
                "somente se essa for a origem."
            ) from None

        opcoes = []

        for separador in (";", ",", "\t"):
            try:
                amostra = csv.reader(
                    io.StringIO(
                        conteudo,
                        newline="",
                    ),
                    delimiter=separador,
                    strict=True,
                )

                for i, linha in enumerate(amostra):
                    if i >= 25:
                        break

                    if _cabecalho(linha):
                        opcoes.append(separador)
                        break

            except csv.Error:
                continue

        if len(opcoes) != 1:
            raise ErroANP(
                "Cabeçalho de revendas individuais não encontrado "
                "ou ambíguo. Resumos/médias não são aceitos."
            )

        try:
            _linhas(
                csv.reader(
                    io.StringIO(
                        conteudo,
                        newline="",
                    ),
                    delimiter=opcoes[0],
                    strict=True,
                ),
                "",
                registros,
            )

        except csv.Error:
            raise ErroANP(
                "CSV malformado."
            ) from None

    elif formato == ".xlsx":
        try:
            with ZipFile(io.BytesIO(bruto)) as pacote:
                tamanho = sum(
                    f.file_size
                    for f in pacote.infolist()
                )

                if tamanho > MAX_DESCOMPACTADO:
                    raise ErroANP(
                        "XLSX descompactado excede 128 MiB."
                    )

            from openpyxl import load_workbook

        except ImportError:
            raise ErroANP(
                "Instale requirements-anp.txt para ler XLSX."
            ) from None

        except BadZipFile:
            raise ErroANP(
                "XLSX inválido."
            ) from None

        try:
            livro = load_workbook(
                io.BytesIO(bruto),
                read_only=True,
                data_only=False,
                keep_links=False,
            )

            try:
                for folha in livro.worksheets:
                    if _linhas(
                        folha.iter_rows(values_only=True),
                        folha.title,
                        registros,
                    ):
                        abas.append(folha.title)

            finally:
                livro.close()

        except ErroANP:
            raise

        except Exception:
            raise ErroANP(
                "Não foi possível ler o XLSX de revendas."
            ) from None

        if not abas:
            raise ErroANP(
                "Nenhuma aba de revendas individuais encontrada. "
                "Resumos/médias não são aceitos."
            )

    else:
        raise ErroANP(
            "Use um arquivo .csv ou .xlsx."
        )

    if not registros:
        raise ErroANP(
            "O arquivo não contém revendas individuais."
        )

    return {
        "arquivo": caminho.name,
        "sha256": hashlib.sha256(bruto).hexdigest(),
        "bytes": len(bruto),
        "formato": formato[1:],
        "abas_lidas": abas,
        "registros": registros,
    }


def preservar_original(dado):
    # Não remove espaços das strings originais.
    return {
        str(k): v if isinstance(v, str) else texto(v)
        for k, v in dado.items()
    }


def identificador_cientifico(valor):
    return bool(
        re.fullmatch(
            r"[+-]?[0-9]+(?:[.,][0-9]+)?[eE][+-]?[0-9]+",
            texto(valor),
        )
    )