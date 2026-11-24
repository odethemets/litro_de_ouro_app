"""Conversões estritas: identificadores não são números e preços não são float."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
import unicodedata
from urllib.parse import urlsplit


class ErroANP(ValueError):
    """Entrada incompatível com a preparação de preços individuais."""


PRODUTOS = {
    "GASOLINA COMUM": ("gasolina_comum", "L"),
    "GASOLINA ADITIVADA": ("gasolina_aditivada", "L"),
    "ETANOL": ("etanol", "L"),
    "GNV": ("gnv", "m³"),
}


def normalizar(valor):
    return " ".join(
        "".join(
            c
            for c in unicodedata.normalize(
                "NFKD",
                str(valor or "").upper(),
            )
            if not unicodedata.combining(c)
        ).split()
    )


def texto(valor):
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()

    return "" if valor is None else str(valor).strip()


def cnpj_valido(valor):
    bruto = texto(valor)

    # Não arredonda notação científica nem inventa dígitos.
    if not re.fullmatch(
        r"(?:[0-9]{14}|[0-9]{2}\.[0-9]{3}\.[0-9]{3}/[0-9]{4}-[0-9]{2})",
        bruto,
    ):
        return None

    digitos = re.sub(r"[^0-9]", "", bruto)

    if len(set(digitos)) == 1:
        return None

    verificadores = (
        (12, (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)),
        (13, (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)),
    )

    for tamanho, pesos in verificadores:
        resto = sum(
            int(n) * peso
            for n, peso in zip(digitos[:tamanho], pesos)
        ) % 11

        esperado = 0 if resto < 2 else 11 - resto

        if int(digitos[tamanho]) != esperado:
            return None

    return digitos


def cep_valido(valor):
    bruto = texto(valor)

    if not re.fullmatch(r"[0-9]{5}-?[0-9]{3}", bruto):
        return None

    return bruto.replace("-", "")


def preco_decimal(valor):
    bruto = texto(valor)

    if (
        len(bruto) > 32
        or not re.fullmatch(
            r"[0-9]+(?:[.,][0-9]{1,6})?",
            bruto,
        )
    ):
        return None

    try:
        preco = Decimal(bruto.replace(",", "."))

        if not Decimal("0.01") <= preco <= Decimal("25.00"):
            return None

        # Não arredondar a fonte para fazer o valor caber no app.
        if preco != preco.quantize(Decimal("0.01")):
            return None

        return format(preco, ".2f")

    except InvalidOperation:
        return None


def data_iso(valor):
    if isinstance(valor, datetime):
        # A coleta representa um dia civil.
        return valor.date()

    if isinstance(valor, date):
        return valor

    bruto = texto(valor)

    try:
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", bruto):
            return date.fromisoformat(bruto)

        if re.fullmatch(r"[0-9]{2}/[0-9]{2}/[0-9]{4}", bruto):
            return datetime.strptime(bruto, "%d/%m/%Y").date()

    except ValueError:
        pass

    return None


def unidade_compativel(bruto, esperada):
    chave = normalizar(bruto).replace(" ", "")

    permitidas = (
        {"R$/LITRO", "R$/L"}
        if esperada == "L"
        else {"R$/M3"}
    )

    return chave in permitidas


def validar_periodo(inicio, fim, referencia):
    if not all(
        type(valor) is date
        for valor in (inicio, fim, referencia)
    ):
        raise ErroANP("Datas do período/referência inválidas.")

    if (
        inicio > fim
        or (fim - inicio).days != 6
        or fim > referencia
    ):
        raise ErroANP(
            "Informe uma semana de sete dias já encerrada "
            "na data de referência."
        )


def validar_url_fonte(url, inicio, fim):
    try:
        partes = urlsplit(url)

        if (
            partes.scheme != "https"
            or partes.hostname not in ("www.gov.br", "gov.br")
            or partes.netloc != partes.hostname
            or partes.query
            or partes.fragment
        ):
            raise ValueError

        prefixo = (
            "/anp/pt-br/assuntos/"
            "precos-e-defesa-da-concorrencia/"
            "precos/arquivos-lpc/"
        )

        nome = (
            f"{inicio.year}/"
            f"revendas_lpc_{inicio:%Y_%m_%d}-{fim:%Y_%m_%d}.xlsx"
        )

        if partes.path != prefixo + nome:
            raise ValueError

    except (ValueError, TypeError, AttributeError):
        raise ErroANP(
            "Use a URL oficial de revendas individuais correspondente "
            "à semana, sem credenciais ou parâmetros."
        ) from None

    return url