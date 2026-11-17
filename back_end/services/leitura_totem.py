"""Imagem preparada e preços do OCR; sem modelo, banco ou armazenamento externo."""
from decimal import Decimal, InvalidOperation
import io
import re

from PIL import Image, ImageOps, UnidentifiedImageError

COMBUSTIVEIS_FOTO = ("Gasolina Comum", "Gasolina Aditivada", "Etanol", "Diesel")
MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 24_000_000
FORMATOS = {"JPEG", "PNG", "WEBP"}


class FotoTotemInvalida(ValueError):
    pass


# Reduz JPEG antes de decodificar quando possível; a saída não carrega EXIF/ICC.
def preparar_imagem(bruto, lado_maximo=1600):
    if not isinstance(bruto, bytes) or not 0 < len(bruto) <= MAX_BYTES:
        raise FotoTotemInvalida("Envie uma imagem de até 8 MB.")
    if not isinstance(lado_maximo, int) or isinstance(lado_maximo, bool) or not 1 <= lado_maximo <= 1600:
        raise FotoTotemInvalida("Dimensão de saída inválida.")
    try:
        with Image.open(io.BytesIO(bruto)) as original:
            if original.format not in FORMATOS:
                raise FotoTotemInvalida("Use uma imagem JPEG, PNG ou WebP.")
            if original.width * original.height > MAX_PIXELS:
                raise FotoTotemInvalida("Escolha uma imagem de até 24 megapixels.")
            original.draft("RGB", (lado_maximo, lado_maximo))
            original.load()
            imagem = ImageOps.exif_transpose(original).convert("RGB")
            try:
                imagem.thumbnail((lado_maximo, lado_maximo))
                imagem.info.clear()
                saida = io.BytesIO()
                imagem.save(saida, "JPEG", quality=88)
                return saida.getvalue()
            finally:
                imagem.close()
    except FotoTotemInvalida:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError) as erro:
        raise FotoTotemInvalida("A imagem não pôde ser preparada.") from erro


# Aceita apenas um literal monetário; não remove letras para fabricar um número.
def _preco(valor):
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, str):
        texto = valor.strip()
        if not re.fullmatch(r"(?:R\$\s*)?[0-9]{1,2}(?:[.,][0-9]{1,3})?", texto):
            return None
        texto = re.sub(r"^R\$\s*", "", texto).replace(",", ".")
    elif isinstance(valor, (int, float, Decimal)):
        texto = str(valor)
    else:
        return None
    try:
        numero = Decimal(texto)
        # Mantém o intervalo de OCR anterior; o formulário manual continua independente.
        if not numero.is_finite() or not Decimal("1.00") <= numero <= Decimal("25.00"):
            return None
        centavos = numero.quantize(Decimal("0.01"))
        if numero != centavos:
            return None
        return float(centavos)
    except (InvalidOperation, ValueError, OverflowError):
        return None


# Uma foto de totem só sugere os quatro combustíveis líquidos, todos em R$/L.
def normalizar_precos(bruto):
    if not isinstance(bruto, dict):
        return {}
    resultado = {}
    for nome in COMBUSTIVEIS_FOTO:
        preco = _preco(bruto.get(nome))
        if preco is not None:
            resultado[nome] = preco
    return resultado
