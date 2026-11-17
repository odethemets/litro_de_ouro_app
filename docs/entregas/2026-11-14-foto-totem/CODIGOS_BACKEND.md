# CODIGOS BACKEND

Destinos relativos ao projeto. Aplicar conforme INSTRUCOES_CODEX_LOCAL.md.

## back_end/services/leitura_totem.py

```python
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
```

## back_end/tests/test_leitura_totem.py

```python
"""Pillow real e valores sintéticos; sem Gemini, Dropbox ou banco."""
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.leitura_totem import FotoTotemInvalida, normalizar_precos, preparar_imagem


def imagem(formato="JPEG", orientacao=None):
    with Image.new("RGB", (200, 100), "white") as foto:
        saida = io.BytesIO()
        exif = Image.Exif()
        exif[271] = "metadado-sintetico-que-deve-sumir"
        if orientacao:
            exif[274] = orientacao
        foto.save(saida, formato, exif=exif)
        return saida.getvalue()


class PrecosTests(unittest.TestCase):
    def test_preserva_preco_decimal_sem_fabricar_numeros(self):
        self.assertEqual(normalizar_precos({"Etanol": "R$ 4,55", "Diesel": 5.89}), {"Etanol": 4.55, "Diesel": 5.89})
        for valor in ("preço 5,89", "1e1", "5 reais", "6/7", "R$ 5,899", 5.899, True, None, float("nan"), float("inf")):
            with self.subTest(valor=valor):
                self.assertEqual(normalizar_precos({"Etanol": valor}), {})

    def test_limites_do_ocr_nao_alteram_cadastro_manual(self):
        for valor in (1, 25, "1,00", "25.00", "5.890"):
            self.assertTrue(normalizar_precos({"Etanol": valor}))
        for valor in (0.5, 0, -1, 25.01, 589):
            self.assertEqual(normalizar_precos({"Etanol": valor}), {})

    def test_produtos_de_outras_unidades_nao_viram_litros(self):
        self.assertEqual(normalizar_precos({"GNV": 4.5, "Recarga Elétrica": 2.2, "Etanol": 4.39}), {"Etanol": 4.39})
        self.assertEqual(normalizar_precos([5.89]), {})


class ImagemTests(unittest.TestCase):
    def test_corrige_orientacao_e_remove_metadados(self):
        jpeg = preparar_imagem(imagem(orientacao=6))
        with Image.open(io.BytesIO(jpeg)) as foto:
            self.assertEqual(foto.format, "JPEG")
            self.assertEqual(foto.size, (100, 200))
            self.assertEqual(len(foto.getexif()), 0)
            self.assertNotIn("icc_profile", foto.info)

    def test_png_vira_jpeg_e_respeita_dimensao(self):
        jpeg = preparar_imagem(imagem("PNG"), 80)
        with Image.open(io.BytesIO(jpeg)) as foto:
            self.assertEqual(foto.size, (80, 40))
            self.assertEqual(foto.format, "JPEG")

    def test_pixels_excessivos_sao_recusados_antes_de_load(self):
        original = MagicMock()
        original.format = "JPEG"
        original.width = 24_000_001
        original.height = 1
        original.__enter__.return_value = original
        with patch("services.leitura_totem.Image.open", return_value=original):
            with self.assertRaises(FotoTotemInvalida):
                preparar_imagem(b"imagem-sintetica")
        original.load.assert_not_called()
        original.draft.assert_not_called()

    def test_vazio_invalido_e_arquivo_grande_sao_recusados(self):
        for bruto in (b"", b"nao-e-foto", b"x" * (8 * 1024 * 1024 + 1)):
            with self.assertRaises(FotoTotemInvalida):
                preparar_imagem(bruto)

    def test_formato_fora_do_contrato_e_recusado(self):
        with self.assertRaises(FotoTotemInvalida):
            preparar_imagem(imagem("GIF"))


if __name__ == "__main__":
    unittest.main()
```

## Integração pontual em back_end/app/rotas/ia.py

Não substituir o arquivo inteiro. Preservar a classe local _FotoInvalida, SDK, modelo, prompt, autenticação, geofence e armazenamento existentes.

Acrescentar este import:

```python
from services.leitura_totem import (
    FotoTotemInvalida,
    preparar_imagem as preparar_imagem_totem,
    normalizar_precos as normalizar_precos_totem,
)
```

Substituir somente as implementações destas funções:

```python
def _preparar_imagem(bruto):
    """Prepara JPEG sem metadados e preserva a exceção já tratada pela rota."""
    try:
        return preparar_imagem_totem(bruto, LADO_MAX_PX)
    except FotoTotemInvalida as erro:
        raise _FotoInvalida(str(erro)) from erro


def _normalizar_precos(bruto):
    """Filtra sugestões do OCR sem fabricar números nem arredondar frações de centavo."""
    return normalizar_precos_totem(bruto)
```

No tratamento da preparação de imagem, manter HTTP 400 e usar a mensagem sanitizada:

```python
    try:
        jpeg = _preparar_imagem(bruto)
    except _FotoInvalida as erro:
        return jsonify({"error": str(erro)}), 400
```

As mensagens do novo helper são constantes de validação, sem conteúdo da foto ou detalhes internos de conexão. Se as funções/classes locais tiverem outro formato, adaptar apenas esses pontos preservando os demais comportamentos e registrar a diferença.
