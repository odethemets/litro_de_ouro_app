"""Fronteira Dropbox simulada: fotos privadas e erros sem detalhes do SDK."""
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import fotos_servicos as fotos


class FotosTests(unittest.TestCase):
    def setUp(self):
        self.cliente = MagicMock()
        self.p = patch.object(fotos, "_cliente")
        self.criar = self.p.start()
        self.criar.return_value.__enter__.return_value = self.cliente

    def tearDown(self):
        self.p.stop()

    def test_upload_nao_cria_link_publico_e_usa_nome_gerado(self):
        nome = fotos.guardar(b"\xff\xd8\xff\xd9")
        self.assertRegex(nome, r"^[0-9a-f]{32}\.jpg$")

        chamada = self.cliente.files_upload.call_args
        self.assertEqual(
            chamada.args[1],
            "/litro_de_ouro_servicos/" + nome,
        )
        self.assertFalse(chamada.kwargs["autorename"])
        self.cliente.sharing_create_shared_link.assert_not_called()

    def test_download_fecha_resposta_e_nao_aceita_caminho_arbitrario(self):
        resposta = MagicMock(content=b"\xff\xd8\xff\xd9")
        self.cliente.files_download.return_value = (None, resposta)

        self.assertEqual(
            fotos.ler("a" * 32 + ".jpg"),
            resposta.content,
        )
        resposta.close.assert_called_once()

        self.criar.reset_mock()

        for caminho in [
            "../arquivo",
            "/outra_pasta/foto.jpg",
            "https://externo/foto.jpg",
            "a.jpg",
        ]:
            with self.assertRaises(fotos.FotoServicoIndisponivel):
                fotos.ler(caminho)

        self.criar.assert_not_called()

    def test_download_sem_retorno_e_recusado(self):
        self.cliente.files_download.return_value = None

        with self.assertRaises(fotos.FotoServicoIndisponivel) as erro:
            fotos.ler("a" * 32 + ".jpg")

        self.assertEqual(
            str(erro.exception),
            "Não foi possível abrir o comprovante.",
        )
        self.cliente.files_download.assert_called_once_with(
            "/litro_de_ouro_servicos/" + "a" * 32 + ".jpg"
        )

    def test_arquivo_grande_ou_nao_jpeg_e_recusado(self):
        for bruto in [
            b"",
            b"svg",
            b"\xff\xd8" + b"x" * fotos.MAX_JPEG,
        ]:
            resposta = MagicMock(content=bruto)
            self.cliente.files_download.return_value = (None, resposta)

            with self.assertRaises(fotos.FotoServicoIndisponivel):
                fotos.ler("a" * 32 + ".jpg")

            resposta.close.assert_called_once()

    def test_falha_sdk_nao_expoe_mensagem_original(self):
        self.cliente.files_upload.side_effect = RuntimeError(
            "detalhe-interno-que-nao-pode-sair"
        )

        with self.assertRaises(fotos.FotoServicoIndisponivel) as erro:
            fotos.guardar(b"\xff\xd8\xff\xd9")

        self.assertNotIn("detalhe-interno", str(erro.exception))

    def test_pasta_existente_e_aceita_mas_conflito_com_arquivo_e_recusado(self):
        from dropbox.files import (
            CreateFolderError,
            WriteError,
            WriteConflictError,
        )
        from dropbox.exceptions import ApiError

        conflito = CreateFolderError.path(
            WriteError.conflict(WriteConflictError.folder)
        )
        self.cliente.files_create_folder_v2.side_effect = ApiError(
            "fixture",
            conflito,
            "erro sintético",
            None,
        )

        self.assertRegex(
            fotos.guardar(b"\xff\xd8\xff\xd9"),
            r"\.jpg$",
        )

        self.cliente.files_upload.reset_mock()

        conflito = CreateFolderError.path(
            WriteError.conflict(WriteConflictError.file)
        )
        self.cliente.files_create_folder_v2.side_effect = ApiError(
            "fixture",
            conflito,
            "erro sintético",
            None,
        )

        with self.assertRaises(fotos.FotoServicoIndisponivel):
            fotos.guardar(b"\xff\xd8\xff\xd9")

        self.cliente.files_upload.assert_not_called()

    def test_limpeza_compensatoria_tem_resultado_controlado(self):
        self.assertTrue(fotos.remover("a" * 32 + ".jpg"))

        self.cliente.files_delete_v2.side_effect = RuntimeError(
            "erro-sintetico"
        )

        self.assertFalse(fotos.remover("a" * 32 + ".jpg"))


if __name__ == "__main__":
    unittest.main()