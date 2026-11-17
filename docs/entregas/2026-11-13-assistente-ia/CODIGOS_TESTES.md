# CODIGOS TESTES FRONTEND

Aplicar conforme INSTRUCOES_CODEX_LOCAL.md. Os caminhos indicam os destinos no projeto.

## front_end/tests/apoio-assistente.cjs

```javascript
/* global __dirname */
// Simula hooks/JSX, foco, API e voz. Não renderiza React ou React Native reais.
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const ts = require("typescript");
let corrente = null;

const hooks = {
  useState(inicial) {
    const dono = corrente, i = dono.indice++;
    if (!(i in dono.slots)) dono.slots[i] = inicial;
    return [dono.slots[i], (valor) => {
      if (!dono.montado) dono.atualizacoesAposSaida++;
      dono.slots[i] = typeof valor === "function" ? valor(dono.slots[i]) : valor;
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
      dono.efeitos.push(() => {
        antes?.cleanup?.();
        dono.slots[i] = { deps, cleanup: fn() };
      });
    }
  },
};
const jsx = (type, props, key) => ({ type, props: props || {}, key });
const turno = () => new Promise((resolve) => setImmediate(resolve));

// Lê os fontes instalados, trocando somente as fronteiras externas por simuladores.
function ambiente() {
  const env = {
    chamadas: [], navegacoes: [], aplicacoes: [],
    auth: { token: "sessao-sintetica-a", status: "AUTHENTICATED", openAuth() {} },
    contexto: { filtros: { combustiveis: [], referencia: "gasolina_comum", marca: "", ordenar: "preco" }, usuario: null },
    vozAtiva: false,
  };
  env.contexto.aplicar = (filtros) => env.aplicacoes.push(filtros);
  env.resposta = () => ({ filtros: { combustiveis: ["etanol"], referencia: "etanol", marca: "Shell", ordenar: "preco" },
    postos: [], total: 0, interpretacao: "comando", localizacao_usada: false, mensagem: "Nenhum posto encontrado." });
  env.postImpl = async () => ({ data: env.resposta() });
  const cache = new Map();
  function carregar(relativo) {
    const arquivo = path.resolve(__dirname, "../src", relativo);
    if (cache.has(arquivo)) return cache.get(arquivo);
    let codigo = fs.readFileSync(arquivo, "utf8");
    if (relativo.endsWith("Assistente/index.tsx")) codigo += "\nexport { ConteudoAssistente };";
    const js = ts.transpileModule(codigo, { compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
    } }).outputText;
    const modulo = { exports: {} };
    const importar = (nome) => {
      if (nome === "react") return hooks;
      if (nome === "react/jsx-runtime") return { jsx, jsxs: jsx, Fragment: "Fragment" };
      if (nome === "react-native") return { View: "View" };
      if (nome === "@react-navigation/native") return {
        useNavigation: () => ({ navigate: (rota) => env.navegacoes.push(rota) }),
        useFocusEffect: (fn) => hooks.useEffect(() => {
          const fechar = fn(); env.desfocar = fechar; env.refocar = fn;
          return fechar;
        }, []),
      };
      if (nome.endsWith("/AuthContext")) return { useAuth: () => env.auth };
      if (nome.endsWith("/FiltrosPostosContext")) return { useFiltrosPostos: () => env.contexto };
      if (nome.endsWith("/API")) return { api: { post: async (...args) => {
        env.chamadas.push(args); return env.postImpl(...args);
      } } };
      if (nome === "axios") return { isAxiosError: (erro) => !!erro?.isAxiosError };
      if (nome.endsWith("/design")) return { AppButton: "AppButton", AppField: "AppField", Notice: "Notice", Page: "Page", Surface: "Surface" };
      if (nome.endsWith("/cartao-posto")) return { CartaoPosto: "CartaoPosto" };
      if (nome.endsWith("/voz")) return {
        vozDisponivel: () => env.vozAtiva,
        iniciarVoz: (texto, fim, erro) => {
          env.transcrever = texto; env.fimVoz = fim; env.erroVoz = erro;
          return () => { env.abortouVoz = true; fim(); };
        },
      };
      const destino = path.resolve(path.dirname(arquivo), nome);
      const ext = [".ts", ".tsx"].find((sufixo) => fs.existsSync(destino + sufixo));
      if (!ext) throw new Error("Import não simulado: " + nome);
      return carregar(path.relative(path.resolve(__dirname, "../src"), destino + ext));
    };
    vm.runInNewContext("(function(require,module,exports){" + js + "\n})", { AbortController, Error, Date })(importar, modulo, modulo.exports);
    cache.set(arquivo, modulo.exports);
    return modulo.exports;
  }
  env.tela = carregar("screens/Assistente/index.tsx");
  env.servico = carregar("services/assistente.ts");
  return env;
}

// Mantém uma instância entre handlers; verificação de chaves é separada.
function montar(funcao, props = {}) {
  const dono = { slots: [], indice: 0, efeitos: [], montado: true, atualizacoesAposSaida: 0,
    render() {
      this.indice = 0; this.efeitos = []; corrente = this;
      try { this.arvore = funcao(props); } finally { corrente = null; }
      for (const efeito of this.efeitos) efeito();
      return this.arvore;
    },
    sair() { this.montado = false; for (const slot of this.slots) slot?.cleanup?.(); },
  };
  dono.render();
  return dono;
}

function todos(no, filtro, itens = []) {
  if (Array.isArray(no)) no.forEach((n) => todos(n, filtro, itens));
  else if (no && typeof no === "object") {
    if (filtro(no)) itens.push(no);
    todos(no.props?.children, filtro, itens);
  }
  return itens;
}
function botao(dono, nome) {
  const b = todos(dono.arvore, (n) => n.type === "AppButton" && n.props.label === nome)[0];
  assert.ok(b, "Botão ausente: " + nome);
  return b;
}
function editar(dono, texto) {
  todos(dono.arvore, (n) => n.type === "AppField")[0].props.onChangeText(texto);
  dono.render();
}
async function buscar(dono, texto = "etanol Shell mais barato") {
  editar(dono, texto);
  botao(dono, "Buscar postos").props.onPress();
  await turno(); dono.render();
}
function pendente() {
  let resolve;
  const promise = new Promise((fn) => { resolve = fn; });
  return { promise, resolve };
}
module.exports = { ambiente, montar, todos, botao, editar, buscar, pendente, turno };
```

## front_end/tests/assistente-sessao.test.cjs

```javascript
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { ambiente, montar, todos, botao, buscar, pendente, turno } = require("./apoio-assistente.cjs");

test("assistente separa rascunho e resultado por sessão", () => {
  const e = ambiente(), primeira = e.tela.default().key;
  e.auth.token = "sessao-sintetica-b";
  assert.notEqual(e.tela.default().key, primeira);
  e.auth.status = "GUEST"; e.auth.token = null;
  const pagina = montar(e.tela.default);
  botao(pagina, "Entrar para usar o assistente");
  assert.equal(e.chamadas.length, 0);
});

test("busca não aplica filtros ou navega antes da confirmação", async () => {
  const e = ambiente(), d = montar(e.tela.ConteudoAssistente, { token: e.auth.token });
  await buscar(d);
  assert.equal(e.aplicacoes.length, 0); assert.equal(e.navegacoes.length, 0);
  assert.equal(e.chamadas[0][2].headers.Authorization, "Bearer sessao-sintetica-a");
  botao(d, "Aplicar esta busca no mapa").props.onPress();
  assert.equal(e.aplicacoes[0].referencia, "etanol");
  assert.equal(e.aplicacoes[0].combustiveis.join(","), "etanol");
  assert.equal(e.navegacoes[0], "Mapa");
});

test("cancelar ignora retorno tardio e permite outra busca", async () => {
  const e = ambiente(), espera = pendente(); e.postImpl = () => espera.promise;
  const d = montar(e.tela.ConteudoAssistente, { token: e.auth.token });
  await buscar(d);
  botao(d, "Cancelar busca").props.onPress(); d.render();
  assert.equal(e.chamadas[0][2].signal.aborted, true);
  e.postImpl = async () => ({ data: e.resposta() });
  await buscar(d, "etanol");
  espera.resolve({ data: { ...e.resposta(), mensagem: "RESULTADO ANTIGO" } });
  await turno(); d.render();
  assert.equal(JSON.stringify(d.arvore).includes("RESULTADO ANTIGO"), false);
  assert.equal(e.chamadas.length, 2);
});

test("duplo clique inicia uma única busca", async () => {
  const e = ambiente(), espera = pendente(); e.postImpl = () => espera.promise;
  const d = montar(e.tela.ConteudoAssistente, { token: e.auth.token });
  await buscar(d);
  botao(d, "Buscar postos").props.onPress(); await turno();
  assert.equal(e.chamadas.length, 1);
  d.sair(); espera.resolve({ data: e.resposta() }); await turno();
  assert.equal(d.atualizacoesAposSaida, 0);
});

test("desfocar aborta pedido e não deixa a tela ocupada ao voltar", async () => {
  const e = ambiente(), espera = pendente(); e.postImpl = () => espera.promise;
  const d = montar(e.tela.ConteudoAssistente, { token: e.auth.token });
  await buscar(d); e.desfocar();
  assert.equal(e.chamadas[0][2].signal.aborted, true);
  espera.resolve({ data: e.resposta() }); await turno();
  e.refocar(); d.render();
  assert.equal(botao(d, "Buscar postos").props.busy, false);
});

test("mudança dos filtros ou GPS impede aplicar uma prévia anterior", async () => {
  for (const alteracao of [
    (e) => { e.contexto.filtros = { ...e.contexto.filtros, marca: "Ipiranga" }; },
    (e) => { e.contexto.usuario = { lat: -7.12, lon: -34.87 }; },
  ]) {
    const e = ambiente(), d = montar(e.tela.ConteudoAssistente, { token: e.auth.token });
    await buscar(d); alteracao(e); d.render();
    const aplicar = botao(d, "Aplicar esta busca no mapa");
    assert.equal(aplicar.props.disabled, true);
    aplicar.props.onPress(); assert.equal(e.aplicacoes.length, 0);
  }
});

test("fala preenche texto sem consultar nem aplicar automaticamente", () => {
  const e = ambiente(); e.vozAtiva = true;
  const d = montar(e.tela.ConteudoAssistente, { token: e.auth.token });
  botao(d, "Falar busca").props.onPress(); e.transcrever("diesel e etanol"); e.fimVoz(); d.render();
  assert.equal(todos(d.arvore, (n) => n.type === "AppField")[0].props.value, "diesel e etanol");
  assert.equal(e.chamadas.length, 0); assert.equal(e.aplicacoes.length, 0);
});

test("sair durante escuta ignora transcrição tardia", () => {
  const e = ambiente(); e.vozAtiva = true;
  const d = montar(e.tela.ConteudoAssistente, { token: e.auth.token });
  botao(d, "Falar busca").props.onPress(); d.sair();
  e.transcrever("resposta antiga");
  assert.equal(e.abortouVoz, true); assert.equal(d.atualizacoesAposSaida, 0);
});

test("serviço recusa mensagem inválida, GPS fictício e sessão vazia antes do POST", async () => {
  const e = ambiente(), signal = new AbortController().signal;
  for (const mensagem of ["", "x".repeat(501)]) {
    await assert.rejects(e.servico.consultarAssistente(mensagem, e.contexto.filtros, null, signal));
  }
  await assert.rejects(e.servico.consultarAssistente("etanol", e.contexto.filtros, { lat: 0, lon: 0 }, signal));
  await assert.rejects(e.servico.consultarAssistente("etanol", e.contexto.filtros, null, signal, ""));
  assert.equal(e.chamadas.length, 0);
});

test("busca já cancelada não envia e filtros são copiados", async () => {
  const e = ambiente(), controller = new AbortController(); controller.abort();
  await assert.rejects(e.servico.consultarAssistente("etanol", e.contexto.filtros, null, controller.signal));
  assert.equal(e.chamadas.length, 0);
  const filtros = e.servico.validarFiltrosBusca(e.contexto.filtros);
  filtros.combustiveis.push("etanol");
  assert.equal(e.contexto.filtros.combustiveis.length, 0);
});
```

## front_end/tests/voz-revisao.test.cjs

```javascript
/* global __dirname */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs"), path = require("node:path"), vm = require("node:vm");
const ts = require("typescript");

// O navegador é simulado; estes casos verificam limpeza e integridade da transcrição.
function ambiente() {
  let voz, fim = 0;
  const textos = [], erros = [], timers = new Map();
  class Reconhecimento {
    constructor() { voz = this; }
    start() {}
    abort() { this.abortos = (this.abortos || 0) + 1; }
  }
  const modulo = { exports: {} };
  const js = ts.transpileModule(fs.readFileSync(path.resolve(__dirname, "../src/services/voz.web.ts"), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  vm.runInNewContext(js, { module: modulo, exports: modulo.exports, Error,
    SpeechRecognition: Reconhecimento, isSecureContext: true,
    setTimeout: (fn) => { timers.set(1, fn); return 1; }, clearTimeout: (id) => timers.delete(id),
  });
  return {
    iniciar(callback = (texto) => textos.push(texto)) {
      return modulo.exports.iniciarVoz(callback, () => { fim++; }, (erro) => erros.push(erro));
    },
    voz: () => voz, fim: () => fim, textos, erros, timers,
  };
}

test("fim da escuta sem resultado produz orientação e limpa recursos", () => {
  const e = ambiente(); e.iniciar(); e.voz().onend();
  assert.equal(e.fim(), 1); assert.equal(e.timers.size, 0);
  assert.equal(e.voz().abortos, 1); assert.equal(e.erros.length, 1);
  assert.equal(e.textos.length, 0);
});

test("fala longa não é truncada nem enviada como outra busca", () => {
  const e = ambiente(); e.iniciar(); e.voz().onresult({ results: [[{ transcript: "x".repeat(501) }]] });
  assert.equal(e.textos.length, 0); assert.match(e.erros[0], /500/);
  assert.equal(e.fim(), 1); assert.equal(e.timers.size, 0);
});

test("exceção no consumidor não deixa escuta e temporizador ativos", () => {
  const e = ambiente(); e.iniciar(() => { throw new Error("consumidor falhou"); });
  assert.throws(() => e.voz().onresult({ results: [[{ transcript: "etanol" }]] }), /consumidor falhou/);
  assert.equal(e.fim(), 1); assert.equal(e.timers.size, 0); assert.equal(e.voz().onresult, null);
});
```
