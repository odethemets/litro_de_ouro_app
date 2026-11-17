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
