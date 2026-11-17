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
