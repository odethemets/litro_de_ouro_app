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
