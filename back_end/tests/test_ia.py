"""Testa app/rotas/ia.py com Flask real, Pillow real e SDK/banco/Dropbox simulados."""
import io, os, sys, types, logging
from functools import wraps

BASE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, BASE)
logging.disable(logging.CRITICAL)

def _pkg(nome, caminho):
    m = types.ModuleType(nome); m.__path__ = [caminho]; sys.modules[nome] = m; return m
_pkg("app", os.path.join(BASE, "app")); _pkg("app.rotas", os.path.join(BASE, "app", "rotas")); _pkg("app.utils", os.path.join(BASE, "app", "utils"))
db = types.ModuleType("app.db"); db.get_db_connection = lambda: None; sys.modules["app.db"] = db
dec = types.ModuleType("app.utils.decorator")
USUARIO = [7]
def token_required(f):
    @wraps(f)
    def w(*a, **k): return f(USUARIO[0], *a, **k)
    return w
dec.token_required = token_required; sys.modules["app.utils.decorator"] = dec

# ---- SDK google-genai simulado
class _Obj:
    def __init__(self, **kw): self.__dict__.update(kw)
class Part(_Obj):
    @staticmethod
    def from_bytes(data, mime_type): return Part(data=data, mime_type=mime_type)
gtypes = types.ModuleType("google.genai.types")
gtypes.Part = Part
gtypes.GenerateContentConfig = lambda **kw: _Obj(**kw)
gtypes.ThinkingConfig = lambda **kw: _Obj(**kw)
gtypes.HttpOptions = lambda **kw: _Obj(**kw)
chamadas, clientes = [], []
RESP = {"texto": '{"Gasolina Comum": 6.29, "Etanol": 4.59}', "erro": None}
class _Modelos:
    def generate_content(self, model, contents, config):
        chamadas.append(_Obj(model=model, contents=contents, config=config))
        if RESP["erro"]: raise RESP["erro"]
        return _Obj(text=RESP["texto"])
class Client:
    def __init__(self, api_key, http_options): clientes.append(_Obj(api_key=api_key, http_options=http_options)); self.models = _Modelos()
genai = types.ModuleType("google.genai"); genai.Client = Client; genai.types = gtypes
google = types.ModuleType("google"); google.__path__ = []; google.genai = genai
sys.modules.update({"google": google, "google.genai": genai, "google.genai.types": gtypes})

uploads = []
dbx = types.ModuleType("services.dropbox_services")
def upload_foto_totem(stream, nome): 
    uploads.append((stream.read(), nome)); return "https://dropbox/prova.jpg"
dbx.upload_foto_totem = upload_foto_totem; sys.modules["services.dropbox_services"] = dbx

os.environ["GEMINI_API_KEY"] = "chave-teste"
from flask import Flask
from PIL import Image
from app.rotas import ia as IA

app = Flask(__name__); app.register_blueprint(IA.ia_bp, url_prefix="/ia"); cli = app.test_client()

class Cur:
    def __init__(self, r): self.r = r
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, s, p=()): pass
    def fetchone(self): return self.r
class Conn:
    open = True
    def __init__(self, r): self.r = r
    def cursor(self): return Cur(self.r)
    def close(self): self.open = False
POSTO = {"latitude": -7.1149075, "longitude": -34.86109731, "tipo_posto": "Convencional"}
IA.get_db_connection = lambda: Conn(POSTO)

def jpeg(w=3000, h=2000, orientacao=None):
    img = Image.new("RGB", (w, h), (200, 30, 30)); buf = io.BytesIO()
    if orientacao:
        ex = img.getexif(); ex[0x0112] = orientacao; img.save(buf, "JPEG", exif=ex)
    else:
        img.save(buf, "JPEG")
    return buf.getvalue()

def enviar(foto=None, **campos):
    form = {"posto_id": "1", "latitude": "-7.1150", "longitude": "-34.8611", "precisao_m": "10"}
    form.update(campos); form = {k: v for k, v in form.items() if v != "__remover__"}
    if foto is not False: form["foto"] = (io.BytesIO(foto if foto is not None else jpeg(400, 300)), "t.jpg")
    return cli.post("/ia/ler-totem", data=form, content_type="multipart/form-data")

def zerar():
    chamadas.clear(); uploads.clear(); IA._uso.clear(); IA.LIMITE_POR_HORA = 12
    RESP.update(texto='{"Gasolina Comum": 6.29, "Etanol": 4.59}', erro=None)
    IA.get_db_connection = lambda: Conn(POSTO); IA.MODELO = "gemini-3.1-pro-preview"; IA.NIVEL_RACIOCINIO = ""

# ---------- sucesso: modelo, JSON, imagem reduzida, prova guardada
zerar(); r = enviar(jpeg())
assert r.status_code == 200, r.get_json()
j = r.get_json(); assert j == {"sucesso": True, "precos": {"Gasolina Comum": 6.29, "Etanol": 4.59}, "foto_url": "https://dropbox/prova.jpg"}
c = chamadas[0]
assert c.model == "gemini-3.1-pro-preview" and c.config.response_mime_type == "application/json"
assert not hasattr(c.config, "thinking_config") and not hasattr(c.config, "temperature")   # padrão da API (high) e temperatura intocada
img_enviada = Image.open(io.BytesIO(c.contents[0].data)); assert max(img_enviada.size) == 1600 and c.contents[0].mime_type == "image/jpeg"
assert Image.open(io.BytesIO(uploads[0][0])).size == img_enviada.size and uploads[0][1] == "totem.jpg"
assert clientes[0].api_key == "chave-teste" and clientes[0].http_options.timeout == 45000

# nível de raciocínio explícito e modelo configurável por ambiente
zerar(); IA.NIVEL_RACIOCINIO = "high"; IA.MODELO = "outro-modelo"; enviar()
assert chamadas[0].config.thinking_config.thinking_level == "high" and chamadas[0].model == "outro-modelo"
zerar(); IA.NIVEL_RACIOCINIO = "banana"; enviar(); assert not hasattr(chamadas[0].config, "thinking_config")   # valor inválido é ignorado

# foto de celular com rotação EXIF vem "em pé" para o modelo
zerar(); enviar(jpeg(200, 100, orientacao=6)); assert Image.open(io.BytesIO(chamadas[0].contents[0].data)).size == (100, 200)

# ---------- geofencing ANTES de gastar IA/Dropbox
zerar()
for campos, codigo, status in [({"latitude": "-6.9", "longitude": "-34.8611"}, "FORA_DO_RAIO", 403),
                               ({"latitude": "__remover__", "longitude": "__remover__"}, "GPS_AUSENTE", 400),
                               ({"latitude": "abc"}, "GPS_INVALIDO", 400),
                               ({"precisao_m": "900"}, "GPS_IMPRECISO", 422),
                               ({"simulada": "true"}, "GPS_SIMULADO", 403)]:
    r = enviar(**campos); assert (r.status_code, r.get_json()["codigo"]) == (status, codigo), (campos, r.get_json())
assert not chamadas and not uploads, "NÃO pode chamar Gemini nem Dropbox quando a localização é recusada"

# posto: ausente, inválido, inexistente, eletroposto
zerar(); assert enviar(posto_id="__remover__").status_code == 400 and enviar(posto_id="x").status_code == 400
IA.get_db_connection = lambda: Conn(None); assert enviar().status_code == 404
IA.get_db_connection = lambda: Conn({**POSTO, "tipo_posto": "Eletroposto"}); assert enviar().status_code == 400
def banco_quebrado(): raise RuntimeError("segredo-do-banco")
IA.get_db_connection = banco_quebrado; r = enviar(); assert r.status_code == 500 and "segredo" not in r.get_data(as_text=True)
assert not chamadas

# ---------- foto
zerar(); assert enviar(foto=False).status_code == 400
assert enviar(foto=b"").status_code == 400
assert enviar(foto=b"isto nao e imagem").status_code == 400
big = b"\xff\xd8" + b"0" * (IA.TAMANHO_MAX_FOTO + 10); r = enviar(foto=big); assert r.status_code == 413
r = cli.post("/ia/ler-totem", data=b"x", content_type="multipart/form-data", environ_overrides={"CONTENT_LENGTH": str(IA.TAMANHO_MAX_REQUISICAO + 1)})
assert r.status_code == 413, r.status_code      # recusado só pelo cabeçalho, sem ler o corpo
assert not chamadas

# ---------- limite de uso por utilizador
zerar(); IA.LIMITE_POR_HORA = 2
assert enviar().status_code == 200 and enviar().status_code == 200
r = enviar(); assert r.status_code == 429 and r.get_json()["codigo"] == "LIMITE_IA" and len(chamadas) == 2
USUARIO[0] = 8; assert enviar().status_code == 200; USUARIO[0] = 7          # outro utilizador não é afetado
IA.LIMITE_POR_HORA = 0; assert enviar().status_code == 200                  # 0 desativa

# ---------- respostas da IA
zerar(); RESP["texto"] = '```json\n{"Diesel": "R$ 4,55", "Etanol": 4.59}\n```'; r = enviar()
assert r.get_json()["precos"] == {"Etanol": 4.59, "Diesel": 4.55}            # cerca markdown e "R$ 4,55" tratados
zerar(); RESP["texto"] = 'Claro! Aqui está: {"Gasolina Comum": 5.89} espero ajudar'; assert enviar().get_json()["precos"] == {"Gasolina Comum": 5.89}
zerar(); RESP["texto"] = '{"Gasolina Comum": 589, "Etanol": 0.5, "Diesel": null, "GNV": 4.0, "Gasolina Aditivada": true}'
r = enviar(); assert r.status_code == 422 and r.get_json()["codigo"] == "LEITURA_VAZIA" and not uploads   # valores absurdos/chaves alheias descartados; sem prova
zerar(); RESP["texto"] = '{"Gasolina Comum": 589, "Etanol": 4.59}'; assert enviar().get_json()["precos"] == {"Etanol": 4.59}
for ruim in ["não sei", "", None, "[1,2]", '"texto"', "{quebrado"]:
    zerar(); RESP["texto"] = ruim; r = enviar(); assert r.status_code == 422 and not uploads, ruim

# ---------- falhas do Gemini / Dropbox
class ErroApi(Exception):
    def __init__(self, code): super().__init__("detalhe interno com chave"); self.code = code
for erro in [ErroApi(404), ErroApi(503), TimeoutError("lento")]:
    zerar(); RESP["erro"] = erro; r = enviar()
    assert r.status_code == 502 and "chave" not in r.get_data(as_text=True) and not uploads
zerar(); dbx.upload_foto_totem = lambda s, n: (_ for _ in ()).throw(RuntimeError("dropbox fora"))
IA.upload_foto_totem = dbx.upload_foto_totem; r = enviar()
assert r.status_code == 200 and r.get_json()["foto_url"] is None             # a leitura não se perde por falha do cofre
print("ia.py: todos os testes passaram")