"""Verifica o SDK/configurações reais sem chave, cliente ou chamada ao Gemini."""
import json
import platform
import sys
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def verificar():
    from google import genai
    from google.genai import types
    from app.rotas import ia

    declarada = next(
        linha.split("==", 1)[1].strip()
        for linha in (ROOT / "requirements.txt").read_text().splitlines()
        if linha.startswith("google-genai==")
    )
    instalada = version("google-genai")
    if instalada != declarada or ia.genai is not genai or ia.types is not types:
        raise RuntimeError("SDK instalado/importado difere do requisito declarado")

    # Mesmos tipos e atributos usados por foto e interpretação de texto.
    http = types.HttpOptions(timeout=45000)
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        thinking_config=types.ThinkingConfig(thinking_level="low"),
    )
    config.http_options = types.HttpOptions(timeout=12000)
    config.max_output_tokens = 2048
    part = types.Part.from_bytes(data=b"imagem-sintetica-nao-enviada", mime_type="image/jpeg")
    if http.timeout != 45000 or config.http_options.timeout != 12000 or not part.inline_data:
        raise RuntimeError("Tipos de configuração incompatíveis")

    return {
        "status": "ok",
        "python": platform.python_version(),
        "sdk": "google-genai",
        "versao_declarada": declarada,
        "versao_instalada": instalada,
        "import_google_genai": True,
        "rotas_usam_mesmo_sdk": True,
        "tipos_foto_texto": True,
        "cliente_criado": False,
        "chamada_provedor": False,
    }


if __name__ == "__main__":
    print(json.dumps(verificar(), ensure_ascii=False, indent=2))
