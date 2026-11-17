"""Diagnóstico sem rede por padrão; --teste-provedor envia uma frase sintética ao Gemini."""
import argparse
import importlib
from importlib import metadata
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# Consulta instalação/configuração sem mostrar segredos ou acessar catálogo/banco.
def diagnosticar(ambiente=None, importar=importlib.import_module, versao=metadata.version):
    ambiente = os.environ if ambiente is None else ambiente
    chave = bool(ambiente.get("GEMINI_API_KEY", "").strip())
    modelo = ambiente.get("GEMINI_MODEL", "").strip()
    segredo = ambiente.get("SECRET_KEY", "")
    segredo_valido = (len(segredo.strip().encode("utf-8")) >= 32
                      and segredo.strip() != "segredo-padrao-temporario")
    resultado = {
        "status": "pendencias",
        "chave_configurada": chave,
        "modelo_explicito": bool(modelo),
        "secret_key_valida": segredo_valido,
        "sdk_importavel": False,
        "rotas_usam_sdk_atual": False,
        "versao_sdk": None,
        "modulos_assistente_importaveis": False,
        "modelo_corresponde_ambiente": False,
        "comando_objetivo_validado": False,
        "rota_consulta_registrada": False,
        "catalogo_consultado": False,
        "tentativa_provedor": False,
        "pendencias": [],
    }
    if not chave:
        resultado["pendencias"].append("GEMINI_API_KEY ausente: interpretação livre indisponível.")
    if not modelo:
        resultado["pendencias"].append("Defina GEMINI_MODEL com um modelo disponível na sua conta.")
    if not segredo_valido:
        resultado["pendencias"].append("SECRET_KEY ausente ou inválida para verificar as rotas.")
    sdk = tipos = None
    try:
        sdk = importar("google.genai")
        tipos = importar("google.genai.types")
        resultado["versao_sdk"] = versao("google-genai")
        resultado["sdk_importavel"] = True
    except Exception as erro:
        resultado["pendencias"].append("SDK indisponível: " + type(erro).__name__)
    try:
        ia = importar("app.rotas.ia")
        comandos = importar("services.comandos_ia")
        importar("app.rotas.assistente")
        resultado["modulos_assistente_importaveis"] = True
        resultado["rotas_usam_sdk_atual"] = bool(
            sdk is not None and tipos is not None and ia.genai is sdk and ia.types is tipos
        )
        if not resultado["rotas_usam_sdk_atual"]:
            resultado["pendencias"].append("SDK das rotas difere da instalação; verifique o runtime e reinicie.")
        resultado["modelo_corresponde_ambiente"] = bool(modelo and ia.MODELO == modelo)
        if modelo and not resultado["modelo_corresponde_ambiente"]:
            resultado["pendencias"].append("Modelo carregado difere do ambiente; reinicie o processo.")
        esperado = {"combustiveis": ["etanol"], "referencia": "etanol", "marca": "Shell", "ordenar": "preco"}
        resultado["comando_objetivo_validado"] = comandos.interpretar_comando(
            "etanol Shell mais barato", ([], "gasolina_comum", None, "distancia"),
        ) == esperado
        if not resultado["comando_objetivo_validado"]:
            resultado["pendencias"].append("O comando objetivo não preservou combustível, bandeira e referência.")
        if segredo_valido:
            app = importar("app").create_app()
            resultado["rota_consulta_registrada"] = any(
                regra.rule.rstrip("/") == "/ia/consultar" and "POST" in regra.methods
                for regra in app.url_map.iter_rules()
            )
            if not resultado["rota_consulta_registrada"]:
                resultado["pendencias"].append("POST /ia/consultar não foi registrado.")
    except Exception as erro:
        resultado["pendencias"].append("Módulos/rotas indisponíveis: " + type(erro).__name__)
    if not resultado["pendencias"]:
        resultado["status"] = "pronto_para_teste"
    return resultado


# É uma única chamada opcional, sem coordenadas, foto, conta real ou consulta ao banco.
def testar_provedor(resultado, importar=importlib.import_module):
    if resultado["status"] != "pronto_para_teste":
        resultado["teste_provedor"] = "nao_executado"
        return resultado
    resultado["tentativa_provedor"] = True
    try:
        assistente = importar("app.rotas.assistente")
        filtros = assistente._interpretar_ia(
            "Quero etanol da Shell, ordenando por menor preço.",
            ([], "gasolina_comum", None, "distancia"),
        )
        esperado = {"combustiveis": ["etanol"], "referencia": "etanol", "marca": "Shell", "ordenar": "preco"}
        if filtros != esperado:
            raise ValueError("Filtros sintéticos incompatíveis")
        resultado["teste_provedor"] = "aprovado"
    except Exception as erro:
        resultado["status"] = "falha_provedor"
        resultado["teste_provedor"] = "falhou"
        resultado["erro_tipo"] = type(erro).__name__
        codigo = getattr(erro, "code", None)
        resultado["status_http"] = codigo if isinstance(codigo, int) and not isinstance(codigo, bool) else None
    return resultado


# A chamada externa exige a opção explícita; o comando comum não cria cliente Gemini.
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--teste-provedor", action="store_true",
                        help="Envia uma frase sintética ao Gemini; pode consumir quota. Não acessa o banco.")
    args = parser.parse_args(argv)
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
    resultado = diagnosticar()
    if args.teste_provedor:
        testar_provedor(resultado)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0 if resultado["status"] == "pronto_para_teste" else 1


if __name__ == "__main__":
    raise SystemExit(main())
