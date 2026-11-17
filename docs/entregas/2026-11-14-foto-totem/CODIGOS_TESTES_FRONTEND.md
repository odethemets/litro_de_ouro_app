# CODIGOS TESTES FRONTEND

Destinos relativos ao projeto. Aplicar conforme INSTRUCOES_CODEX_LOCAL.md.

## front_end/tests/apoio-leitor-totem.cjs

```javascript
/* global __dirname */
// Simula hooks/JSX/foco/picker/API; não renderiza React Native nem abre a galeria.
const fs = require("node:fs"), path = require("node:path"), vm = require("node:vm");
const ts = require("typescript"), assert = require("node:assert/strict");
let corrente;
const jsx = (type, props, key) => ({ type, props: props || {}, key });
const hooks = {
  useState(inicial) {
    const dono = corrente, i = dono.indice++;
    if (!(i in dono.slots)) dono.slots[i] = inicial;
    return [dono.slots[i], (v) => {
      if (!dono.montado) dono.atualizacoesAposSaida++;
      dono.slots[i] = typeof v === "function" ? v(dono.slots[i]) : v;
    }];
  },
  useRef(inicial) {
    const dono = corrente, i = dono.indice++;
    if (!(i in dono.slots)) dono.slots[i] = { current: inicial };
    return dono.slots[i];
  },
  useCallback: (fn) => fn,
  useEffect(fn, deps) {
    const dono = corrente, i = dono.indice++, antes = dono.slots[i];
    if (!antes || deps.some((v, j) => !Object.is(v, antes.deps[j]))) {
      dono.efeitos.push(() => { antes?.cleanup?.(); dono.slots[i] = { deps, cleanup: fn() }; });
    }
  },
};
function foto(uri = "blob:foto-sintetica") {
  return { uri, width: 200, height: 100, fileSize: 20, mimeType: "image/jpeg", type: "image" };
}
const turno = () => new Promise((resolve) => setImmediate(resolve));
function pendente() {
  let resolve;
  const promise = new Promise((fn) => { resolve = fn; });
  return { promise, resolve };
}

// Carrega os fontes reais instalados, mantendo apenas as fronteiras simuladas.
function ambiente() {
  const e = { chamadas: [], usados: [], ordem: [], limpezas: 0,
    auth: { token: "sessao-sintetica", status: "AUTHENTICATED" }, plataforma: "web" };
  e.pickImpl = async () => ({ canceled: false, assets: [foto()] });
  e.gpsImpl = async () => ({ latitude: -7.11, longitude: -34.86, precisaoM: 10, obtidaEm: Date.now(), simulada: false });
  e.postImpl = async () => ({ data: { sucesso: true, precos: { Etanol: 4.39 }, foto_url: null } });
  const cache = new Map();
  function carregar(relativo) {
    if (cache.has(relativo)) return cache.get(relativo);
    const arquivo = path.resolve(__dirname, "../src", relativo);
    let codigo = fs.readFileSync(arquivo, "utf8");
    if (relativo.endsWith("leitor-totem.tsx")) codigo += "\nexport { ConteudoLeitor };";
    const js = ts.transpileModule(codigo, { compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
    } }).outputText;
    const modulo = { exports: {} };
    const importar = (nome) => {
      if (nome === "react") return hooks;
      if (nome === "react/jsx-runtime") return { jsx, jsxs: jsx };
      if (nome === "@react-navigation/native") return { useFocusEffect: (fn) => hooks.useEffect(fn, []) };
      if (nome === "react-native") return { View: "View", Image: "Image", Platform: { OS: e.plataforma } };
      if (nome === "expo-image-picker") return { launchImageLibraryAsync: (...args) => e.pickImpl(...args), getPendingResultAsync: async () => null };
      if (nome.endsWith("/AuthContext")) return { useAuth: () => e.auth };
      if (nome.endsWith("/localizacao")) return { obterPosicao: () => { e.ordem.push("gps"); return e.gpsImpl(); } };
      if (nome.endsWith("/API")) return { api: { post: async (...args) => {
        e.chamadas.push(args); e.ordem.push("api"); return e.postImpl(...args);
      } } };
      if (nome === "./design") return { AppButton: "AppButton", Notice: "Notice", Surface: "Surface" };
      const destino = path.resolve(path.dirname(arquivo), nome);
      const ext = [".ts", ".tsx"].find((s) => fs.existsSync(destino + s));
      if (!ext) throw new Error("Import não simulado: " + nome);
      return carregar(path.relative(path.resolve(__dirname, "../src"), destino + ext));
    };
    vm.runInNewContext("(function(require,module,exports){" + js + "\n})", {
      Error, Date, AbortController, Blob, FormData, URL,
      fetch: async () => { e.ordem.push("arquivo"); return { ok: true, blob: async () => new Blob(["imagem"], { type: "image/jpeg" }) }; },
    })(importar, modulo, modulo.exports);
    cache.set(relativo, modulo.exports); return modulo.exports;
  }
  e.leitor = carregar("components/leitor-totem.tsx");
  e.props = { postoId: 10, token: e.auth.token, bloqueado: false,
    usar: (...args) => e.usados.push(args), limparComprovante: () => { e.limpezas++; } };
  return e;
}

function montar(fn, inicial) {
  let props = inicial;
  const d = { slots: [], indice: 0, efeitos: [], montado: true, atualizacoesAposSaida: 0,
    render(novos = {}) {
      props = { ...props, ...novos }; this.indice = 0; this.efeitos = []; corrente = this;
      try { this.arvore = fn(props); } finally { corrente = null; }
      for (const efeito of this.efeitos) efeito();
    },
    sair() { this.montado = false; for (const slot of this.slots) slot?.cleanup?.(); },
  };
  d.render(); return d;
}
function todos(no, tipo, itens = []) {
  if (Array.isArray(no)) no.forEach((n) => todos(n, tipo, itens));
  else if (no && typeof no === "object") {
    if (no.type === tipo) itens.push(no);
    todos(no.props?.children, tipo, itens);
  }
  return itens;
}
function botao(d, nome) {
  const b = todos(d.arvore, "AppButton").find((n) => n.props.label === nome);
  assert.ok(b, "Botão ausente: " + nome); return b;
}
async function clicar(d, nome) {
  botao(d, nome).props.onPress(); await turno(); d.render();
}
module.exports = { ambiente, montar, todos, botao, clicar, pendente, turno, foto };
```

## front_end/tests/leitor-totem-sessao.test.cjs

```javascript
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { ambiente, montar, todos, botao, clicar, pendente, turno, foto } = require("./apoio-leitor-totem.cjs");

test("leitor isola foto por conta/posto e não aparece para visitante", () => {
  const e = ambiente(), inicial = e.leitor.LeitorTotem(e.props).key;
  assert.notEqual(e.leitor.LeitorTotem({ ...e.props, postoId: 11 }).key, inicial);
  e.auth.token = "outra-sessao"; assert.notEqual(e.leitor.LeitorTotem(e.props).key, inicial);
  e.auth.status = "GUEST"; e.auth.token = null;
  assert.equal(e.leitor.LeitorTotem(e.props), null);
});

test("seleção não envia; arquivo é preparado antes do GPS e comprovante começa desativado", async () => {
  const e = ambiente(), d = montar(e.leitor.ConteudoLeitor, e.props);
  await clicar(d, "Escolher foto do totem");
  assert.equal(e.chamadas.length, 0); assert.equal(e.ordem.length, 0);
  await clicar(d, "Ler preços da foto");
  assert.equal(e.ordem.join(","), "arquivo,gps,api");
  assert.equal(e.chamadas[0][1].get("guardar_comprovante"), "false");
  assert.equal(e.usados.length, 0);
  await clicar(d, "Usar Etanol: R$ 4,39 / L");
  assert.equal(e.usados[0][0], "etanol"); assert.equal(e.usados[0][1], "4.39");
  assert.equal(e.chamadas[0][0], "/ia/ler-totem"); assert.equal(e.chamadas.length, 1);
});

test("última seleção web vence sem bloquear se um cancelamento não resolveu", async () => {
  const e = ambiente(), a = pendente(), b = pendente();
  let numero = 0; e.pickImpl = () => (++numero === 1 ? a.promise : b.promise);
  const d = montar(e.leitor.ConteudoLeitor, e.props);
  await clicar(d, "Escolher foto do totem"); await clicar(d, "Escolher foto do totem");
  b.resolve({ canceled: false, assets: [foto("blob:B")] }); await turno(); d.render();
  a.resolve({ canceled: false, assets: [foto("blob:A")] }); await turno(); d.render();
  assert.equal(todos(d.arvore, "Image")[0].props.source.uri, "blob:B");
});

test("nova seleção invalida leitura anterior ainda em andamento", async () => {
  const e = ambiente(), leitura = pendente(), picker = pendente();
  const d = montar(e.leitor.ConteudoLeitor, e.props);
  await clicar(d, "Escolher foto do totem");
  e.pickImpl = () => picker.promise;
  await clicar(d, "Escolher outra foto");
  e.postImpl = () => leitura.promise;
  await clicar(d, "Ler preços da foto");
  picker.resolve({ canceled: false, assets: [foto("blob:nova")] }); await turno(); d.render();
  assert.equal(e.chamadas[0][2].signal.aborted, true);
  leitura.resolve({ data: { sucesso: true, precos: { Etanol: 4.39 } } }); await turno(); d.render();
  assert.equal(todos(d.arvore, "Image")[0].props.source.uri, "blob:nova");
  assert.equal(todos(d.arvore, "AppButton").some((b) => b.props.label.startsWith("Usar ")), false);
});

test("sair durante GPS impede POST e atualizações após desmontagem", async () => {
  const e = ambiente(), espera = pendente(); e.gpsImpl = () => espera.promise;
  const d = montar(e.leitor.ConteudoLeitor, e.props);
  await clicar(d, "Escolher foto do totem"); await clicar(d, "Ler preços da foto"); d.sair();
  espera.resolve({ latitude: -7.11, longitude: -34.86, precisaoM: 10, obtidaEm: Date.now(), simulada: false });
  await turno(); assert.equal(e.chamadas.length, 0); assert.equal(d.atualizacoesAposSaida, 0);
});

test("cancelar leitura ignora retorno tardio sem preencher cadastro", async () => {
  const e = ambiente(), espera = pendente(); e.postImpl = () => espera.promise;
  const d = montar(e.leitor.ConteudoLeitor, e.props);
  await clicar(d, "Escolher foto do totem"); await clicar(d, "Ler preços da foto");
  await clicar(d, "Cancelar leitura");
  espera.resolve({ data: { sucesso: true, precos: { Etanol: 4.39 } } }); await turno(); d.render();
  assert.equal(e.chamadas[0][2].signal.aborted, true); assert.equal(e.usados.length, 0);
  assert.equal(todos(d.arvore, "AppButton").some((b) => b.props.label.startsWith("Usar ")), false);
});

test("cadastro em andamento aborta leitura e impede reaproveitar resposta", async () => {
  const e = ambiente(), espera = pendente(); e.postImpl = () => espera.promise;
  const d = montar(e.leitor.ConteudoLeitor, e.props);
  await clicar(d, "Escolher foto do totem"); await clicar(d, "Ler preços da foto");
  d.render({ bloqueado: true });
  assert.equal(e.chamadas[0][2].signal.aborted, true);
  espera.resolve({ data: { sucesso: true, precos: { Etanol: 4.39 } } }); await turno(); d.render();
  assert.equal(e.usados.length, 0);
});

test("produto não permitido não é levado ao formulário", async () => {
  const e = ambiente(), d = montar(e.leitor.ConteudoLeitor, { ...e.props, permitidos: ["diesel"] });
  await clicar(d, "Escolher foto do totem"); await clicar(d, "Ler preços da foto");
  const usar = botao(d, "Usar Etanol: R$ 4,39 / L"); assert.equal(usar.props.disabled, true);
  usar.props.onPress(); assert.equal(e.usados.length, 0);
});

test("comprovante só é anexado com opção ativa e confirmação Dropbox", async () => {
  const e = ambiente();
  e.postImpl = async () => ({ data: { sucesso: true, precos: { Etanol: 4.39 }, foto_url: "https://www.dropbox.com/s/prova.jpg?raw=1" } });
  const d = montar(e.leitor.ConteudoLeitor, e.props);
  await clicar(d, "Escolher foto do totem"); await clicar(d, "Salvar comprovante: desativado");
  await clicar(d, "Ler preços da foto");
  assert.equal(e.chamadas[0][1].get("guardar_comprovante"), "true");
  await clicar(d, "Usar Etanol: R$ 4,39 / L");
  assert.equal(e.usados[0][2], "https://www.dropbox.com/s/prova.jpg?raw=1");
});
```

## front_end/tests/leitura-totem.test.cjs

```javascript
/* global __dirname */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs"), path = require("node:path"), vm = require("node:vm");
const ts = require("typescript");

// Contratos reais do serviço, fronteira HTTP simulada e FormData/Blob reais do Node.
function ambiente(api) {
  const chamadas = [], cache = new Map();
  function carregar(nome) {
    if (cache.has(nome)) return cache.get(nome);
    const modulo = { exports: {} };
    const js = ts.transpileModule(fs.readFileSync(path.resolve(__dirname, "../src/services", nome + ".ts"), "utf8"), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    }).outputText;
    const importar = (alvo) => alvo === "./API" ? { api: api || { post: async (...args) => {
      chamadas.push(args); return { data: { sucesso: true, precos: { Etanol: 4.39 }, foto_url: null } };
    } } } : carregar(alvo.replace("./", ""));
    vm.runInNewContext("(function(require,module,exports){" + js + "\n})", { Blob, FormData, URL, fetch, Error })(importar, modulo, modulo.exports);
    cache.set(nome, modulo.exports); return modulo.exports;
  }
  return { servico: carregar("leituraTotem"), chamadas };
}
const foto = (extra = {}) => ({ uri: "blob:foto-sintetica", width: 200, height: 100, mimeType: "image/jpeg", fileSize: 20, type: "image", ...extra });
const gps = (extra = {}) => ({ latitude: -7.11, longitude: -34.86, precisaoM: 10, obtidaEm: Date.now(), simulada: false, ...extra });

test("OCR não arredonda centavos nem mistura produtos de outras unidades", () => {
  const { servico } = ambiente();
  const r = servico.validarLeitura({ sucesso: true, precos: { Etanol: 4.39, Diesel: 5.899, GNV: 4.1, "Recarga Elétrica": 2.2 } }, false);
  assert.equal(r.valores.length, 1); assert.equal(r.valores[0].codigo, "etanol");
  for (const valor of [true, "4.39", NaN, Infinity, 0.5, 25.01]) {
    assert.throws(() => servico.validarLeitura({ sucesso: true, precos: { Etanol: valor } }, false));
  }
});

test("comprovante depende de consentimento e de URL Dropbox válida", () => {
  const { servico } = ambiente();
  const corpo = { sucesso: true, precos: { Etanol: 4.39 }, foto_url: "https://www.dropbox.com/s/prova.jpg?raw=1" };
  assert.equal(servico.validarLeitura(corpo, false).fotoUrl, null);
  assert.equal(servico.validarLeitura(corpo, true).fotoUrl, corpo.foto_url);
  for (const url of ["http://www.dropbox.com/prova", "https://www.dropbox.com.evil.test/prova", "https://usuario:senha@www.dropbox.com/prova", "javascript:alert(1)"]) {
    const r = servico.validarLeitura({ ...corpo, foto_url: url }, true);
    assert.equal(r.fotoUrl, null); assert.equal(r.valores.length, 1);
  }
});

test("foto inválida ou grande é recusada antes do envio", () => {
  const { servico } = ambiente();
  for (const alteracao of [{ uri: "" }, { type: "video" }, { mimeType: "image/heic" }, { fileSize: 0 }, { fileSize: 8 * 1024 * 1024 + 1 }, { width: 6001, height: 4000 }]) {
    assert.throws(() => servico.validarFoto(foto(alteracao)));
  }
});

test("corpo contém foto e GPS, sem confirmar oferta nem cadastrar preço", () => {
  const { servico } = ambiente();
  const dados = servico.formularioLeitura(10, foto(), new Blob(["imagem"], { type: "image/jpeg" }), gps(), false);
  assert.equal(dados.get("posto_id"), "10"); assert.equal(dados.get("guardar_comprovante"), "false");
  assert.equal(dados.get("simulada"), "false"); assert.ok(dados.get("foto"));
  for (const campo of ["preco", "karma", "confirmado"]) assert.equal(dados.has(campo), false);
});

test("GPS antigo, fictício ou impreciso não gera formulário", () => {
  const { servico } = ambiente();
  for (const alteracao of [{ latitude: 0, longitude: 0 }, { precisaoM: 151 }, { simulada: true }, { obtidaEm: Date.now() - 16000 }]) {
    assert.throws(() => servico.formularioLeitura(10, foto(), null, gps(alteracao), false));
  }
});

test("web verifica tamanho real do arquivo antes de usar o GPS", async () => {
  const { servico } = ambiente(), signal = new AbortController().signal;
  await assert.rejects(servico.prepararFotoWeb(foto({ file: new Blob([]) }), signal));
  const arquivo = new Blob(["imagem"], { type: "image/png" });
  assert.equal(await servico.prepararFotoWeb(foto({ file: arquivo }), signal), arquivo);
});

test("envio é somente leitura e preserva sessão capturada e cancelamento", async () => {
  const { servico, chamadas } = ambiente(), signal = new AbortController().signal;
  const dados = servico.formularioLeitura(10, foto(), new Blob(["imagem"], { type: "image/jpeg" }), gps(), false);
  await servico.lerFotoTotem(dados, "sessao-sintetica", signal, false);
  assert.equal(chamadas.length, 1); assert.equal(chamadas[0][0], "/ia/ler-totem");
  assert.equal(chamadas[0][2].headers.Authorization, "Bearer sessao-sintetica");
  assert.equal(chamadas[0][2].headers["Content-Type"], undefined);
  assert.equal(chamadas[0][2].signal, signal);
});

test("Axios não transforma o multipart em JSON por herdar Content-Type global", async () => {
  const axios = require("axios"), capturas = [];
  const cliente = axios.create({ headers: { "Content-Type": "application/json" }, adapter: async (config) => {
    capturas.push(config);
    return { status: 200, statusText: "OK", headers: {}, config,
      data: { sucesso: true, precos: { Etanol: 4.39 }, foto_url: null } };
  } });
  const { servico } = ambiente(cliente);
  const dados = servico.formularioLeitura(10, foto(), new Blob(["imagem"], { type: "image/jpeg" }), gps(), false);
  await servico.lerFotoTotem(dados, "sessao-sintetica", new AbortController().signal, false);
  assert.ok(capturas[0].data instanceof FormData);
  assert.notEqual(capturas[0].headers.getContentType(), "application/json");
});
```
