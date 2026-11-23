import json
import unittest
from types import SimpleNamespace

from services.transcricao_voz import (
    AudioBuscaInvalido,
    TranscricaoInvalida,
    TranscricaoIndisponivel,
    LIMITE_AUDIO_BYTES,
    validar_audio,
    normalizar_transcricao,
    transcrever_audio,
)

WEBM = b"\x1a\x45\xdf\xa3" + b"audio-teste"


class TranscricaoVozTests(unittest.TestCase):
    def provedor(self, texto='{"texto":"  etanol Shell  "}'):
        chamadas = []

        def gerar(**kwargs):
            chamadas.append(kwargs)
            return SimpleNamespace(text=texto)

        provedor = SimpleNamespace(
            MODELO="modelo-teste",
            types=SimpleNamespace(
                HttpOptions=lambda **kw: SimpleNamespace(**kw),
                Part=SimpleNamespace(
                    from_bytes=lambda **kw: kw
                ),
            ),
            _config_geracao=lambda: SimpleNamespace(),
            _cliente=lambda: SimpleNamespace(
                models=SimpleNamespace(generate_content=gerar)
            ),
            _extrair_json=json.loads,
        )

        return provedor, chamadas

    def test_formatos_e_bytes_preservados(self):
        formatos = (
            ("audio/webm;codecs=opus", WEBM),
            (
                "audio/mp4",
                b"\x00\x00\x00\x18ftypM4A " + b"audio",
            ),
            ("audio/ogg", b"OggS" + b"audio"),
            ("audio/wav", b"RIFF1234WAVE" + b"audio"),
        )

        for mime, audio in formatos:
            with self.subTest(mime=mime):
                bruto, tipo = validar_audio(audio, mime)
                self.assertEqual(bruto, audio)
                self.assertEqual(tipo, mime.split(";")[0])

    def test_vazio_e_formato_invalido(self):
        casos = (
            (b"", "audio/webm"),
            (b"texto", "audio/webm"),
            (WEBM, "text/plain"),
        )

        for audio, mime in casos:
            with self.subTest(mime=mime, tamanho=len(audio)):
                with self.assertRaises(AudioBuscaInvalido):
                    validar_audio(audio, mime)

    def test_limite_de_tamanho(self):
        with self.assertRaises(AudioBuscaInvalido) as erro:
            validar_audio(
                b"x" * (LIMITE_AUDIO_BYTES + 1),
                "audio/webm",
            )

        self.assertEqual(erro.exception.status, 413)

    def test_normaliza_espacos(self):
        self.assertEqual(
            normalizar_transcricao(
                {"texto": " etanol\n Shell "}
            ),
            "etanol Shell",
        )

    def test_contrato_e_limite_do_texto(self):
        self.assertEqual(
            len(normalizar_transcricao({"texto": "a" * 500})),
            500,
        )

        casos = (
            {},
            {"texto": None},
            {"texto": ""},
            {"texto": "a" * 501},
            {"texto": "busca", "extra": 1},
            {"texto": "a\x00b"},
        )

        for dados in casos:
            with self.subTest(dados=dados):
                with self.assertRaises(TranscricaoInvalida):
                    normalizar_transcricao(dados)

    def test_provedor_recebe_audio_e_configuracao(self):
        provedor, chamadas = self.provedor()

        self.assertEqual(
            transcrever_audio(WEBM, "audio/webm", provedor),
            "etanol Shell",
        )

        self.assertEqual(len(chamadas), 1)
        chamada = chamadas[0]

        self.assertEqual(chamada["model"], "modelo-teste")
        self.assertEqual(
            chamada["contents"][0]["data"],
            WEBM,
        )
        self.assertEqual(
            chamada["config"].http_options.timeout,
            45000,
        )

    def test_audio_invalido_nao_chama_provedor(self):
        provedor, chamadas = self.provedor()

        with self.assertRaises(AudioBuscaInvalido):
            transcrever_audio(
                b"texto", "audio/webm", provedor
            )

        self.assertEqual(chamadas, [])

    def test_resposta_invalida_do_provedor(self):
        provedor, _ = self.provedor("fora do JSON")

        with self.assertRaises(TranscricaoInvalida):
            transcrever_audio(
                WEBM, "audio/webm", provedor
            )

    def test_falha_do_provedor_nao_expoe_detalhe(self):
        provedor, _ = self.provedor()

        def falhar():
            raise RuntimeError("detalhe-interno")

        provedor._cliente = falhar

        with self.assertRaises(
            TranscricaoIndisponivel
        ) as erro:
            transcrever_audio(
                WEBM, "audio/webm", provedor
            )

        self.assertNotIn(
            "detalhe-interno", str(erro.exception)
        )


if __name__ == "__main__":
    unittest.main()