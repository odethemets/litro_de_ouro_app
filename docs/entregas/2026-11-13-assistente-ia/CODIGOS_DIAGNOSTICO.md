# CODIGOS DIAGNOSTICO

Aplicar conforme INSTRUCOES_CODEX_LOCAL.md. Os caminhos indicam os destinos no projeto.

## back_end/scripts/verificar_assistente.py

```python
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
```

## back_end/tests/test_verificar_assistente.py

```python
"""Diagnóstico com módulos sintéticos; não chama Gemini, Flask ou banco reais."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

CAMINHO = Path(__file__).resolve().parents[1] / "scripts" / "verificar_assistente.py"
SPEC = importlib.util.spec_from_file_location("verificador_assistente", CAMINHO)
verificador = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verificador)

FILTROS = {"combustiveis": ["etanol"], "referencia": "etanol", "marca": "Shell", "ordenar": "preco"}
AMBIENTE = {"GEMINI_API_KEY": "chave-sintetica-nao-real", "GEMINI_MODEL": "modelo-sintetico", "SECRET_KEY": "x" * 40}


# Separa módulos e permite comprovar que o diagnóstico não invoca o modelo.
def modulos():
    provedor = Mock(return_value=FILTROS)
    regra = SimpleNamespace(rule="/ia/consultar", methods={"POST"})
    app = SimpleNamespace(url_map=SimpleNamespace(iter_rules=lambda: [regra]))
    sdk, tipos = object(), object()
    fontes = {
        "google.genai": sdk, "google.genai.types": tipos,
        "app.rotas.ia": SimpleNamespace(MODELO="modelo-sintetico", genai=sdk, types=tipos),
        "services.comandos_ia": SimpleNamespace(interpretar_comando=Mock(return_value=FILTROS)),
        "app.rotas.assistente": SimpleNamespace(_interpretar_ia=provedor),
        "app": SimpleNamespace(create_app=lambda: app),
    }
    return fontes, provedor


class DiagnosticoTests(unittest.TestCase):
    def test_padrao_so_verifica_e_nao_chama_provedor(self):
        fontes, provedor = modulos()
        r = verificador.diagnosticar(AMBIENTE, fontes.__getitem__, lambda _: "2.34.0")
        self.assertEqual(r["status"], "pronto_para_teste")
        self.assertFalse(r["tentativa_provedor"])
        self.assertFalse(r["catalogo_consultado"])
        provedor.assert_not_called()
        self.assertNotIn(AMBIENTE["GEMINI_API_KEY"], str(r))
        self.assertNotIn(AMBIENTE["SECRET_KEY"], str(r))

    def test_sem_chave_nao_testa_provedor(self):
        fontes, provedor = modulos()
        r = verificador.diagnosticar({**AMBIENTE, "GEMINI_API_KEY": ""}, fontes.__getitem__, lambda _: "2.34.0")
        verificador.testar_provedor(r, fontes.__getitem__)
        self.assertEqual(r["teste_provedor"], "nao_executado")
        provedor.assert_not_called()

    def test_modelo_deve_ser_explicito_e_corresponder_ao_runtime(self):
        fontes, _ = modulos()
        for valor in ("", "outro-modelo"):
            r = verificador.diagnosticar({**AMBIENTE, "GEMINI_MODEL": valor}, fontes.__getitem__, lambda _: "2.34.0")
            self.assertEqual(r["status"], "pendencias")

    def test_sdk_ausente_e_reportado_sem_stack_ou_segredo(self):
        fontes, _ = modulos()
        def importar(nome):
            if nome == "google.genai":
                raise ModuleNotFoundError("detalhe-privado-nao-deve-sair")
            return fontes[nome]
        r = verificador.diagnosticar(AMBIENTE, importar, lambda _: "2.34.0")
        self.assertEqual(r["status"], "pendencias")
        self.assertNotIn("detalhe-privado", str(r))

    def test_rotas_com_sdk_antigo_exigem_reinicio(self):
        fontes, _ = modulos()
        fontes["app.rotas.ia"].genai = None
        r = verificador.diagnosticar(AMBIENTE, fontes.__getitem__, lambda _: "2.34.0")
        self.assertEqual(r["status"], "pendencias")
        self.assertFalse(r["rotas_usam_sdk_atual"])

    def test_teste_explicito_faz_uma_chamada_sintetica(self):
        fontes, provedor = modulos()
        r = verificador.diagnosticar(AMBIENTE, fontes.__getitem__, lambda _: "2.34.0")
        verificador.testar_provedor(r, fontes.__getitem__)
        self.assertEqual(r["teste_provedor"], "aprovado")
        provedor.assert_called_once()

    def test_filtros_inventados_nao_passam_na_homologacao(self):
        fontes, provedor = modulos()
        provedor.return_value = {**FILTROS, "referencia": "diesel"}
        r = verificador.diagnosticar(AMBIENTE, fontes.__getitem__, lambda _: "2.34.0")
        verificador.testar_provedor(r, fontes.__getitem__)
        self.assertEqual(r["status"], "falha_provedor")

    def test_falha_do_provedor_omite_detalhes_sensiveis(self):
        fontes, provedor = modulos()
        provedor.side_effect = RuntimeError("segredo-privado-nao-deve-sair")
        r = verificador.diagnosticar(AMBIENTE, fontes.__getitem__, lambda _: "2.34.0")
        verificador.testar_provedor(r, fontes.__getitem__)
        self.assertEqual(r["erro_tipo"], "RuntimeError")
        self.assertNotIn("segredo-privado", str(r))


if __name__ == "__main__":
    unittest.main()
```
