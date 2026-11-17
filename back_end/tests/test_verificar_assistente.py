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
