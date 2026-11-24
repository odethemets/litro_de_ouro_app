"""Flask/JWT reais; áudio sintético, Gemini e banco simulados, sem rede."""
import io
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jwt
from flask import Flask
from app.rotas import assistente, ia
from services.transcricao_voz import (
    AudioBuscaInvalido,
    LIMITE_AUDIO_BYTES,
    LIMITE_REQUISICAO_BYTES,
    TranscricaoInvalida,
    normalizar_transcricao,
    validar_audio,
)

MP4 = b"\x00\x00\x00\x18ftypM4A audio-sintetico"


class SessaoSimulada:
    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        if not sql.startswith(
            "SELECT versao_token FROM usuarios"
        ):
            raise AssertionError(
                "Somente a leitura de autenticação é permitida."
            )

    def fetchone(self):
        return {"versao_token": 0}

    def close(self):
        pass


class CorrecaoVozTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask("teste_transcricao_voz")
        self.app.config.update(
            TESTING=False,
            SECRET_KEY=(
                "segredo-sintetico-exclusivo-deste-teste-sem-uso-real"
            ),
        )
        self.app.register_blueprint(
            assistente.assistente_bp
        )
        self.client = self.app.test_client()

        self.token = jwt.encode(
            {
                "usuario_id": 7,
                "ver": 0,
                "exp": (
                    datetime.now(timezone.utc)
                    + timedelta(minutes=5)
                ),
            },
            self.app.config["SECRET_KEY"],
            algorithm="HS256",
        )

        self.gerar = Mock(
            return_value=SimpleNamespace(
                text='{"texto":"etanol Shell"}'
            )
        )
        self.part = Mock(
            side_effect=lambda **kw: SimpleNamespace(**kw)
        )
        self.tipos = SimpleNamespace(
            HttpOptions=lambda **kw: SimpleNamespace(**kw),
            GenerateContentConfig=lambda **kw: SimpleNamespace(**kw),
            ThinkingConfig=lambda **kw: SimpleNamespace(**kw),
            Part=SimpleNamespace(from_bytes=self.part),
        )
        self.db = Mock(
            return_value=SessaoSimulada()
        )

        for remendo in (
            patch.dict(
                os.environ,
                {"GEMINI_API_KEY": "chave-sintetica-teste"},
            ),
            patch(
                "app.utils.decorator.get_db_connection",
                self.db,
            ),
            patch.object(ia, "genai", object()),
            patch.object(ia, "types", self.tipos),
            patch.object(
                ia,
                "_cliente",
                return_value=SimpleNamespace(
                    models=SimpleNamespace(
                        generate_content=self.gerar
                    )
                ),
            ),
            patch.object(ia, "LIMITE_POR_HORA", 12),
        ):
            remendo.start()
            self.addCleanup(remendo.stop)

        ia._uso.clear()

    def enviar(
        self,
        audio=MP4,
        mime="audio/mp4",
        autenticado=True,
    ):
        resposta = self.client.post(
            "/ia/transcrever",
            data={
                "audio": (
                    io.BytesIO(audio),
                    "busca.m4a",
                    mime,
                )
            },
            headers=(
                {"Authorization": "Bearer " + self.token}
                if autenticado
                else {}
            ),
        )

        # Um corpo grande pode ser recusado antes de abrir o multipart.
        resposta.request.close()
        resposta.request.environ["wsgi.input"].close()
        return resposta

    def corpo(self, resposta) -> dict[str, Any]:
        dados = resposta.get_json()

        if not isinstance(dados, dict):
            self.fail(
                "A resposta precisa ser JSON, "
                "não a página HTML de erro."
            )

        return dados

    def test_token_ausente_retorna_401_antes_do_banco_e_provedor(self):
        resposta = self.enviar(autenticado=False)

        self.assertEqual(resposta.status_code, 401)
        self.assertIn("error", self.corpo(resposta))
        self.db.assert_not_called()
        self.gerar.assert_not_called()

    def test_sucesso_preserva_bytes_mime_modelo_e_configuracao(self):
        resposta = self.enviar()

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            self.corpo(resposta),
            {"texto": "etanol Shell"},
        )
        self.part.assert_called_once_with(
            data=MP4,
            mime_type="audio/mp4",
        )

        kwargs = self.gerar.call_args.kwargs

        self.assertEqual(kwargs["model"], ia.MODELO)
        self.assertEqual(
            kwargs["config"].http_options.timeout,
            45000,
        )
        self.assertEqual(
            kwargs["config"].max_output_tokens,
            4096,
        )

    def test_configuracao_compartilhada_retorna_objeto(self):
        with patch.object(
            ia,
            "NIVEL_RACIOCINIO",
            "low",
        ):
            config = ia._config_geracao()

        self.assertIsNotNone(config)
        self.assertEqual(
            config.response_mime_type,
            "application/json",
        )
        self.assertEqual(
            config.thinking_config.thinking_level,
            "low",
        )

    def test_extracao_json_compartilhada_continua_disponivel(self):
        self.assertEqual(
            ia._extrair_json(
                '```json\n{"texto":"etanol"}\n```'
            ),
            {"texto": "etanol"},
        )

    def test_consulta_texto_preserva_comando_sem_chamar_ia(self):
        filtros = {
            "combustiveis": [],
            "referencia": "gasolina_comum",
            "marca": "",
            "ordenar": "preco",
        }

        with patch.object(
            assistente,
            "get_db_connection",
            return_value=SessaoSimulada(),
        ):
            with patch.object(
                assistente,
                "consultar_catalogo",
                return_value=[],
            ):
                resposta = self.client.post(
                    "/ia/consultar",
                    json={
                        "mensagem": "etanol Shell mais barato",
                        "filtros": filtros,
                    },
                    headers={
                        "Authorization": "Bearer " + self.token
                    },
                )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            self.corpo(resposta)["filtros"]["referencia"],
            "etanol",
        )
        self.gerar.assert_not_called()

    def test_interpretacao_texto_usa_configuracao_valida(self):
        filtros = {
            "combustiveis": ["etanol"],
            "referencia": "etanol",
            "marca": "Shell",
            "ordenar": "preco",
        }
        self.gerar.return_value = SimpleNamespace(
            text=json.dumps({
                "filtros": filtros,
                "regiao": None,
                "esclarecimento": None,
            })
        )

        resultado = assistente._interpretar_ia(
            "busca sintética",
            ([], "gasolina_comum", None, "preco"),
        )

        self.assertEqual(resultado, filtros)

        config = self.gerar.call_args.kwargs["config"]
        self.assertEqual(
            config.http_options.timeout,
            12000,
        )
        self.assertEqual(
            config.max_output_tokens,
            2048,
        )

    def test_limitador_ausente_nao_produz_500_html(self):
        with patch.object(
            ia,
            "_excedeu_limite",
            None,
        ):
            resposta = self.enviar()

        self.assertEqual(resposta.status_code, 503)
        self.assertIn("error", self.corpo(resposta))
        self.gerar.assert_not_called()

    def test_falha_do_limitador_nao_expoe_excecao(self):
        segredo = "MARCADOR_PRIVADO_NAO_PUBLICAR"

        with patch.object(
            ia,
            "_excedeu_limite",
            side_effect=RuntimeError(segredo),
        ):
            with self.assertLogs(
                self.app.logger,
                level="WARNING",
            ) as logs:
                resposta = self.enviar()

        self.assertEqual(resposta.status_code, 503)
        self.assertNotIn(
            segredo,
            resposta.get_data(as_text=True),
        )
        self.assertNotIn(
            segredo,
            " ".join(logs.output),
        )
        self.gerar.assert_not_called()

    def test_extrator_ausente_bloqueia_antes_do_provedor(self):
        with patch.object(
            ia,
            "_extrair_json",
            None,
        ):
            resposta = self.enviar()

        self.assertEqual(resposta.status_code, 503)
        self.gerar.assert_not_called()

    def test_configuracao_none_retorna_503(self):
        with patch.object(
            ia,
            "_config_geracao",
            return_value=None,
        ):
            resposta = self.enviar()

        self.assertEqual(resposta.status_code, 503)
        self.assertIn("error", self.corpo(resposta))
        self.gerar.assert_not_called()

    def test_chave_ou_sdk_ausentes_retorna_503(self):
        with patch.dict(
            os.environ,
            {"GEMINI_API_KEY": ""},
        ):
            self.assertEqual(
                self.enviar().status_code,
                503,
            )

        with patch.object(ia, "types", None):
            self.assertEqual(
                self.enviar().status_code,
                503,
            )

        self.gerar.assert_not_called()

    def test_audio_invalido_recusado_antes_de_consumir_limite(self):
        with patch.object(
            ia,
            "_excedeu_limite",
        ) as limite:
            for audio, mime, status in (
                (b"", "audio/mp4", 400),
                (b"nao-e-audio", "audio/mp4", 415),
                (MP4, "application/octet-stream", 415),
                (
                    b"x" * (LIMITE_AUDIO_BYTES + 1),
                    "audio/mp4",
                    413,
                ),
            ):
                with self.subTest(status=status):
                    self.assertEqual(
                        self.enviar(audio, mime).status_code,
                        status,
                    )

            limite.assert_not_called()

        self.gerar.assert_not_called()

    def test_corpo_grande_e_campo_ausente_recusados(self):
        headers = {
            "Authorization": "Bearer " + self.token
        }

        resposta = self.client.post(
            "/ia/transcrever",
            headers=headers,
        )
        self.assertEqual(resposta.status_code, 400)

        resposta = self.client.post(
            "/ia/transcrever",
            headers=headers,
            environ_overrides={
                "CONTENT_LENGTH": str(
                    LIMITE_REQUISICAO_BYTES + 1
                )
            },
        )
        self.assertEqual(resposta.status_code, 413)
        self.gerar.assert_not_called()

    def test_limite_compartilhado_bloqueia_segunda_chamada(self):
        with patch.object(
            ia,
            "LIMITE_POR_HORA",
            1,
        ):
            self.assertEqual(
                self.enviar().status_code,
                200,
            )
            resposta = self.enviar()

        self.assertEqual(resposta.status_code, 429)
        self.assertEqual(
            self.corpo(resposta)["codigo"],
            "LIMITE_IA",
        )
        self.gerar.assert_called_once()

    def test_falha_provedor_retorna_503_sem_detalhes_privados(self):
        self.gerar.side_effect = RuntimeError(
            "MARCADOR_PRIVADO_NAO_PUBLICAR"
        )

        resposta = self.enviar()

        self.assertEqual(resposta.status_code, 503)
        self.assertNotIn(
            "MARCADOR_PRIVADO_NAO_PUBLICAR",
            json.dumps(self.corpo(resposta)),
        )
        self.gerar.assert_called_once()

    def test_resposta_invalida_retorna_422(self):
        for texto in (
            "nao-json",
            '{"texto":""}',
            '{"texto":1}',
            '{"texto":"a","extra":1}',
        ):
            with self.subTest(texto=texto):
                self.gerar.return_value = SimpleNamespace(
                    text=texto
                )
                resposta = self.enviar()

                self.assertEqual(
                    resposta.status_code,
                    422,
                )
                self.assertIn(
                    "error",
                    self.corpo(resposta),
                )

    def test_audio_nao_consulta_catalogo_gps_ou_dropbox(self):
        with patch.object(
            assistente,
            "get_db_connection",
        ) as catalogo:
            with patch.object(
                ia,
                "upload_foto_totem",
            ) as dropbox:
                with patch.object(
                    ia,
                    "validar_proximidade",
                ) as gps:
                    self.assertEqual(
                        self.enviar().status_code,
                        200,
                    )

        catalogo.assert_not_called()
        dropbox.assert_not_called()
        gps.assert_not_called()

    def test_quatro_formatos_preservam_bytes(self):
        for audio, mime in (
            (MP4, "audio/mp4"),
            (
                b"\x1a\x45\xdf\xa3audio",
                "audio/webm",
            ),
            (b"OggSaudio", "audio/ogg"),
            (
                b"RIFF\x00\x00\x00\x00WAVEaudio",
                "audio/wav",
            ),
        ):
            with self.subTest(mime=mime):
                self.assertEqual(
                    validar_audio(
                        audio,
                        mime + "; codecs=teste",
                    ),
                    (audio, mime),
                )

    def test_audio_invalido_e_transcricao_longa_recusados(self):
        with self.assertRaises(AudioBuscaInvalido):
            validar_audio(None, None)

        for texto in (
            "",
            "a" * 501,
            "etanol\x00Shell",
        ):
            with (
                self.subTest(texto=texto[:20]),
                self.assertRaises(TranscricaoInvalida),
            ):
                normalizar_transcricao({
                    "texto": texto
                })

        self.assertEqual(
            normalizar_transcricao({
                "texto": "  etanol\n  Shell "
            }),
            "etanol Shell",
        )


if __name__ == "__main__":
    unittest.main()