"""Contrato de consulta, sem conexões externas ou alteração de dados."""
import copy
import sys
import unittest
from unittest.mock import patch
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.catalogo_postos import consultar_catalogo, validar_filtros  # type: ignore[reportMissingImports]


class Banco:
    def __init__(self):
        self.sql = []
        self.postos = [dict(id=i, nome=f"Posto {i}", bairro=None, endereco="Rua de teste",
            latitude=-7.11, longitude=-34.86, horario_funcionamento=None,
            tipo_posto="Eletroposto" if i == 5 else "Convencional",
            marca={1: "Shell", 2: "BR", 3: "Shell"}.get(i), marca_origem="osm") for i in range(1, 6)]
        self.ofertas = [dict(posto_id=i, combustivel_codigo=c, disponivel_osm=o, disponivel_manual=m)
            for i, c, o, m in [(1,"gasolina_comum",1,None), (1,"etanol",1,None),
            (2,"gasolina_comum",1,0), (2,"etanol",1,None), (3,"etanol",1,None),
            (3,"gasolina_comum",None,0), (5,"recarga_eletrica",1,None)]]
        self.precos = [dict(id=i, posto_id=p, tipo_combustivel=c, preco=Decimal(v),
            data_registro=datetime(2026,11,11,9,30), autor_nome="Autor público")
            for i,p,c,v in [(1,1,"Gasolina Comum","5.89"),(2,1,"Etanol","4.29"),
                (3,2,"Gasolina Comum","6.15"),(4,3,"Etanol","4.19"),
                (5,5,"Recarga Elétrica (kWh)","2.20"),(6,4,"Gasolina Comum","5.49")]]
    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def execute(self, sql, params):
        sql=" ".join(sql.split())
        if not sql.startswith("SELECT "): raise AssertionError("Escrita inesperada")
        self.sql.append((sql,params))
        self.resultado = self.ofertas if "FROM postos_combustiveis" in sql else self.precos if "FROM registos_preco r " in sql else self.postos
    def fetchall(self): return copy.deepcopy(self.resultado)


class CatalogoTests(unittest.TestCase):
    def consulta(self, args=None, banco=None, centro=None):
        banco=banco or Banco()
        return consultar_catalogo(banco,centro,25,500,validar_filtros(args or {}),lambda *a: 400)
    def test_todos_preserva_desconhecidos_e_seis_produtos(self):
        resultado=self.consulta()
        self.assertEqual(len(resultado),5)
        self.assertEqual(len(resultado[3]["combustiveis"]),6)
        self.assertIsNone(resultado[3]["combustiveis"][0]["disponivel"])
    def test_filtro_exige_oferta_confirmada_e_nao_preco(self):
        self.assertEqual([p["id"] for p in self.consulta({"combustiveis":"gasolina_comum"})],[1])
    def test_selecao_multipla_usa_intersecao_na_oferta(self):
        self.assertEqual([p["id"] for p in self.consulta({"combustiveis":"gasolina_comum,etanol"})],[1,2,3])
    def test_manual_negativo_prevalece_sobre_osm_positivo(self):
        p=self.consulta()[1]
        self.assertFalse(p["combustiveis"][0]["disponivel"])
        self.assertEqual(p["combustiveis"][0]["origem"],"manual")
        self.assertIsNone(p["preco_referencia"])
    def test_referencia_sem_preco_nao_empresta_etanol(self):
        resultado=self.consulta({"combustiveis":"gasolina_comum,etanol"})
        self.assertIsNone(resultado[2]["preco_referencia"])
        self.assertEqual(resultado[2]["combustiveis"][2]["preco"],4.19)
    def test_eletrico_nao_reutiliza_preco_gasolina(self):
        p=self.consulta({"combustiveis":"recarga_eletrica"})[0]
        self.assertIsNone(p["preco_gasolina"])
        self.assertEqual(p["preco_referencia"],2.2)
        self.assertEqual(p["unidade_referencia"],"kWh")
    def test_preco_e_autoria_data_do_mesmo_produto(self):
        p=self.consulta({"combustiveis":"etanol"})[0]
        self.assertEqual(p["preco_referencia"],4.29)
        self.assertEqual(p["autor_referencia"],"Autor público")
        self.assertEqual(p["data_atualizacao"],"2026-11-11T09:30:00")
    def test_marca_normalizada_e_cruzada_com_combustivel(self):
        self.assertEqual([p["id"] for p in self.consulta({"marca":"Petrobras","combustiveis":"etanol"})],[2])
    def test_categoria_marca_nao_informada(self):
        self.assertEqual([p["id"] for p in self.consulta({"marca":"nao_informada"})],[4,5])
    def test_referencia_pode_ser_trocada_sem_mudar_produtos(self):
        p=self.consulta({"combustiveis":"gasolina_comum,etanol","referencia":"etanol"})[0]
        self.assertEqual(p["preco_referencia"],4.29)
    def test_ordenacao_compara_somente_referencia_e_nulos_por_ultimo(self):
        ids=[p["id"] for p in self.consulta({"combustiveis":"gasolina_comum,etanol","referencia":"etanol","ordenar":"preco"})]
        self.assertEqual(ids,[3,1,2])
    def test_sem_coordenadas_nao_inventa_distancia(self):
        self.assertNotIn("distancia_m",self.consulta()[0])
        self.assertEqual(self.consulta(centro=(-7.11,-34.86))[0]["distancia_m"],400)
    def test_consulta_em_lote_sem_n_mais_um_ou_escrita(self):
        banco=Banco(); self.consulta(banco=banco)
        self.assertEqual(len(banco.sql),3)
        self.assertTrue(all(sql.startswith("SELECT ") for sql,_ in banco.sql))
    def test_coordenadas_invalidas_ignoradas(self):
        banco=Banco(); banco.postos[0]["latitude"]=None
        self.assertNotIn(1,[p["id"] for p in self.consulta(banco=banco)])
    def test_parametros_invalidos_rejeitados(self):
        for args in [{"combustiveis":"gasolina"},{"combustiveis":"etanol,"},
            {"combustiveis":"etanol","referencia":"diesel"},{"referencia":"outro"},
            {"ordenar":"sql"},{"marca":"x"*121}]:
            with self.subTest(args=args),self.assertRaises(ValueError): validar_filtros(args)
    def test_primeira_selecao_define_referencia_e_remove_duplicadas(self):
        selecionados,ref,_,_=validar_filtros({"combustiveis":"etanol,gasolina_comum,etanol"})
        self.assertEqual(selecionados,["etanol","gasolina_comum"])
        self.assertEqual(ref,"etanol")
    def test_referencia_desconhecida_nao_aparece_como_oferta_no_filtro_multiplo(self):
        banco=Banco()
        banco.ofertas.append(dict(posto_id=4,combustivel_codigo="etanol",disponivel_osm=1,disponivel_manual=None))
        todos=self.consulta(banco=banco)
        self.assertEqual(next(p for p in todos if p["id"]==4)["preco_referencia"],5.49)
        filtrados=self.consulta({"combustiveis":"gasolina_comum,etanol"},banco=banco)
        p=next(p for p in filtrados if p["id"]==4)
        self.assertIsNone(p["preco_referencia"])
        self.assertEqual(p["combustiveis"][0]["preco"],5.49)

class RotasCatalogoTests(unittest.TestCase):
    def setUp(self):
        from app import create_app
        from app.rotas import postos
        self.conexoes=[]
        def conectar():
            db=Banco();db.open=True
            db.close=lambda: setattr(db,"open",False)
            self.conexoes.append(db)
            return db
        self.patch=patch.object(postos,"get_db_connection",conectar)
        self.patch.start();self.addCleanup(self.patch.stop)
        with patch.dict("os.environ",{"SECRET_KEY":"chave-exclusiva-do-teste-sem-credencial-real-20261111"}):
            self.client=create_app().test_client()
    def conferir(self,query,ids):
        response=self.client.get("/postos"+query)
        self.assertEqual(response.status_code,200)
        self.assertEqual([p["id"] for p in response.get_json()],ids)
        self.assertTrue(all(not db.open for db in self.conexoes))
    def test_rota_publica_sem_token(self): self.conferir("",[1,2,3,4,5])
    def test_rota_gasolina(self): self.conferir("?combustiveis=gasolina_comum",[1])
    def test_rota_multiplos_referencia_e_ordem(self): self.conferir("?combustiveis=gasolina_comum,etanol&referencia=etanol&ordenar=preco",[3,1,2])
    def test_rota_eletrica(self): self.conferir("?combustiveis=recarga_eletrica",[5])
    def test_rota_bandeira_e_produto(self): self.conferir("?marca=Shell&combustiveis=etanol",[1,3])
    def test_rota_produto_invalido_antes_de_conectar(self):
        self.assertEqual(self.client.get("/postos?combustiveis=produto_inventado").status_code,400)
        self.assertEqual(self.conexoes,[])
    def test_rota_referencia_invalida_antes_de_conectar(self):
        self.assertEqual(self.client.get("/postos?combustiveis=etanol&referencia=diesel").status_code,400)
        self.assertEqual(self.conexoes,[])
    def test_rota_coordenada_invalida_antes_de_conectar(self):
        self.assertEqual(self.client.get("/postos?lat=texto&lng=-34.86").status_code,400)
        self.assertEqual(self.conexoes,[])

if __name__ == "__main__": unittest.main()
