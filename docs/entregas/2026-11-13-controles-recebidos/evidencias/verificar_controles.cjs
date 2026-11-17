/* Verificação lógica dos TSX com hooks/API/GPS simulados; não renderiza React real. */
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const front = path.resolve(process.argv[2] || "front_end");
const ts = require(path.join(front, "node_modules/typescript"));
let corrente = null;
const resultados = [];

// Simula somente os hooks usados nestes controles, mantendo efeitos e desmontagem.
const hooks = {
  useState(inicial) {
    const dono = corrente, i = dono.indice++;
    if (!(i in dono.slots)) dono.slots[i] = typeof inicial === "function" ? inicial() : inicial;
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
  useEffect(efeito, deps) {
    const dono = corrente, i = dono.indice++, antes = dono.slots[i];
    if (!antes || !deps || deps.some((v, j) => !Object.is(v, antes.deps[j]))) {
      dono.efeitos.push(() => {
        antes?.cleanup?.();
        dono.slots[i] = { deps, cleanup: efeito() };
      });
    }
  },
};

// Representa JSX como objetos para inspecionar props, textos e handlers.
const jsx = (type, props, key) => ({ type, props: props || {}, key });
function ambiente() {
  const chamadas = [], gps = [];
  const auth = { token: "sessao-sintetica", status: "AUTHENTICATED", openAuth: (destino) => chamadas.push({ login: destino }) };
  const env = { auth, chamadas, gps, gpsImpl: async () => ({ latitude: -7.11, longitude: -34.86,
    precisaoM: 10, obtidaEm: Date.now(), simulada: false }),
  getImpl: async () => ({ data: resumo() }), postImpl: async () => ({ data: resumo() }) };
  const cache = new Map();
  function carregar(relativo) {
    const arquivo = path.join(front, relativo);
    if (cache.has(arquivo)) return cache.get(arquivo);
    let codigo = fs.readFileSync(arquivo, "utf8");
    if (relativo.endsWith("confirmar-oferta.tsx")) codigo += "\nexport { ControlesOferta };";
    if (relativo.endsWith("votar-preco.tsx")) codigo += "\nexport { ControlesVoto };";
    if (relativo.endsWith("detalhes.tsx")) codigo += "\nexport { CartaoCombustivel };";
    const js = ts.transpileModule(codigo, { compilerOptions: {
      target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
      jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true,
    } }).outputText;
    const modulo = { exports: {} };
    const importar = (nome) => {
      if (nome === "react") return hooks;
      if (nome === "react/jsx-runtime") return { jsx, jsxs: jsx, Fragment: "Fragment" };
      if (nome === "react-native") return { View: "View", Text: "Text", Pressable: "Pressable",
        Linking: { openURL: async (url) => chamadas.push({ rota: url }) } };
      if (nome === "@expo/vector-icons/Ionicons") return { __esModule: true, default: "Ionicons" };
      if (nome.endsWith("/AuthContext")) return { useAuth: () => auth };
      if (nome.endsWith("/API")) return { api: {
        get: async (url, config) => { chamadas.push({ metodo: "GET", url, config }); return env.getImpl(url, config); },
        post: async (url, body, config) => { chamadas.push({ metodo: "POST", url, body, config }); return env.postImpl(url, body, config); },
      } };
      if (nome.endsWith("/localizacao")) return { obterPosicao: async (perfil) => { gps.push(perfil); return env.gpsImpl(); } };
      if (nome.endsWith("/design")) return { AppButton: "AppButton", Notice: "Notice", useAppTheme: () => ({ colors: {
        textPrimary: "#111", textSecondary: "#555", border: "#ddd", surface: "#fff",
      } }) };
      if (nome.endsWith("/favoritos")) return { BotaoFavorito: "BotaoFavorito" };
      if (nome === "./layout") return { styles: {} };
      const destino = path.resolve(path.dirname(arquivo), nome);
      const extensao = [".ts", ".tsx"].find((e) => fs.existsSync(destino + e));
      if (!extensao) throw new Error("Import não simulado: " + nome);
      return carregar(path.relative(front, destino + extensao));
    };
    vm.runInNewContext("(function(require,module,exports){" + js + "\n})", { AbortController, Error, Date })(importar, modulo, modulo.exports);
    cache.set(arquivo, modulo.exports);
    return modulo.exports;
  }
  env.oferta = carregar("src/components/confirmar-oferta.tsx");
  env.voto = carregar("src/components/votar-preco.tsx");
  env.detalhes = carregar("src/screens/ConsultaPostos/detalhes.tsx");
  return env;
}

// Mantém o estado de uma instância entre ações; as chaves são verificadas à parte.
function montar(funcao, props) {
  const dono = { slots: [], indice: 0, efeitos: [], montado: true, atualizacoesAposSaida: 0,
    render() {
      this.indice = 0; this.efeitos = []; corrente = this;
      try { this.arvore = funcao(props); } finally { corrente = null; }
      for (const efeito of this.efeitos) efeito();
      return this.arvore;
    },
    sair() { this.montado = false; for (const slot of this.slots) slot?.cleanup?.(); },
  };
  dono.render(); return dono;
}
function todos(no, filtro, itens = []) {
  if (Array.isArray(no)) no.forEach((n) => todos(n, filtro, itens));
  else if (no && typeof no === "object") {
    if (filtro(no)) itens.push(no);
    todos(no.props?.children, filtro, itens);
  }
  return itens;
}
const botoes = (dono) => todos(dono.arvore, (n) => n.type === "AppButton");
const botao = (dono, nome) => {
  const b = botoes(dono).find((n) => n.props.label === nome);
  assert.ok(b, "Botão ausente: " + nome); return b;
};
const texto = (no) => Array.isArray(no) ? no.map(texto).join(" ") : no && typeof no === "object" ? texto(no.props?.children) : String(no ?? "");
const turno = () => new Promise((resolve) => setImmediate(resolve));
const pendente = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };
const propsOferta = (extra = {}) => ({ postoId: 12, codigo: "gnv", nome: "GNV", onAtualizar() {}, ...extra });
const propsVoto = (extra = {}) => ({ registoId: 30, nome: "GNV", ...extra });
const resumo = (extra = {}) => ({ registo_id: 30, positivos: 0, negativos: 0, confianca_score: 1, meu_voto: null, pode_votar: true, ...extra });
function revisar(env, props = propsOferta()) {
  const dono = montar(env.oferta.ControlesOferta, props);
  botao(dono, "Confirmar disponibilidade").props.onPress(); dono.render(); return dono;
}
async function confirmar(dono) { botao(dono, "Sim, verifiquei neste local").props.onPress(); await turno(); dono.render(); }
async function consultar(dono) { botao(dono, "Consultar avaliações").props.onPress(); await turno(); dono.render(); }
async function caso(nome, fn) {
  try { await fn(); resultados.push({ nome, resultado: "aprovado" }); }
  catch (erro) { resultados.push({ nome, resultado: "falhou", erro: erro.message }); }
}

(async () => {
  await caso("Oferta visitante abre login sem GPS", () => {
    const e = ambiente(); e.auth.token = null; e.auth.status = "GUEST";
    const d = montar(e.oferta.ControlesOferta, propsOferta());
    botao(d, "Entrar para confirmar oferta").props.onPress();
    assert.equal(e.chamadas[0].login, "Login"); assert.equal(e.gps.length, 0);
  });
  await caso("Cancelar revisão não solicita GPS", () => {
    const e = ambiente(), d = revisar(e);
    botao(d, "Cancelar").props.onPress(); d.render();
    botao(d, "Confirmar disponibilidade"); assert.equal(e.gps.length, 0);
  });
  await caso("GPS negado permite nova tentativa sem POST", async () => {
    const e = ambiente(); e.gpsImpl = async () => { throw new Error("GPS negado"); };
    const d = revisar(e); await confirmar(d);
    assert.match(texto(d.arvore), /GPS negado/); botao(d, "Sim, verifiquei neste local");
    assert.equal(e.chamadas.length, 0);
  });
  await caso("Confirmação válida mantém sucesso mesmo se recarga lançar erro", async () => {
    const e = ambiente(); e.postImpl = async () => ({ data: { posto_id: 12, codigo: "gnv", disponivel: true, origem: "manual" } });
    const d = revisar(e, propsOferta({ onAtualizar() { throw new Error("falha de recarga"); } })); await confirmar(d);
    assert.match(texto(d.arvore), /Oferta confirmada/); assert.match(texto(d.arvore), /Não foi possível iniciar/);
    botao(d, "Atualizar catálogo"); assert.ok(!botoes(d).some((b) => b.props.label === "Sim, verifiquei neste local"));
  });
  await caso("Resposta inválida da oferta fica incerta", async () => {
    const e = ambiente(), d = revisar(e); await confirmar(d);
    assert.match(texto(d.arvore), /pode ter sido confirmada/); botao(d, "Atualizar catálogo");
    assert.ok(!botoes(d).some((b) => b.props.label === "Sim, verifiquei neste local"));
  });
  for (const status of [408, 503]) await caso("Oferta HTTP " + status + " exige reconciliação", async () => {
    const e = ambiente(); e.postImpl = async () => { throw { response: { status } }; };
    const d = revisar(e); await confirmar(d); assert.match(texto(d.arvore), /pode ter sido confirmada/);
  });
  await caso("Recusa 409 mantém revisão e explica a negativa", async () => {
    const e = ambiente(); e.postImpl = async () => { throw { response: { status: 409, data: { error: "Oferta indisponível" } } }; };
    const d = revisar(e); await confirmar(d); assert.match(texto(d.arvore), /Oferta indisponível/);
    botao(d, "Sim, verifiquei neste local");
  });
  await caso("Duplo clique de oferta envia um único POST", async () => {
    const e = ambiente(), espera = pendente(); e.postImpl = () => espera.promise;
    const d = revisar(e), acao = botao(d, "Sim, verifiquei neste local").props.onPress;
    acao(); acao(); await turno(); assert.equal(e.chamadas.length, 1);
    d.sair(); espera.reject(new Error("cancelado")); await turno();
    assert.equal(d.atualizacoesAposSaida, 0);
  });
  await caso("Desmontagem durante GPS impede envio", async () => {
    const e = ambiente(), espera = pendente(); e.gpsImpl = () => espera.promise;
    const d = revisar(e); botao(d, "Sim, verifiquei neste local").props.onPress(); d.sair();
    espera.resolve({ latitude: -7.11, longitude: -34.86, precisaoM: 10, obtidaEm: Date.now(), simulada: false }); await turno();
    assert.equal(e.chamadas.length, 0); assert.equal(d.atualizacoesAposSaida, 0);
  });
  await caso("Chaves da oferta mudam por conta/status/posto/produto", () => {
    const e = ambiente(), inicial = e.oferta.ConfirmarOferta(propsOferta()).key;
    for (const props of [propsOferta({ postoId: 13 }), propsOferta({ codigo: "etanol" })]) assert.notEqual(e.oferta.ConfirmarOferta(props).key, inicial);
    e.auth.status = "GUEST"; assert.notEqual(e.oferta.ConfirmarOferta(propsOferta()).key, inicial);
    e.auth.status = "AUTHENTICATED"; e.auth.token = "outra-sessao-sintetica";
    assert.notEqual(e.oferta.ConfirmarOferta(propsOferta()).key, inicial);
  });
  await caso("Voto não consulta ao montar e visitante abre login", () => {
    const e = ambiente(); e.auth.status = "GUEST"; e.auth.token = null;
    const d = montar(e.voto.ControlesVoto, propsVoto()); assert.equal(e.chamadas.length, 0);
    botao(d, "Entrar para avaliar preço").props.onPress(); assert.equal(e.chamadas[0].login, "Login");
  });
  await caso("Autor consulta contagens mas não recebe ações de voto", async () => {
    const e = ambiente(); e.getImpl = async () => ({ data: resumo({ pode_votar: false }) });
    const d = montar(e.voto.ControlesVoto, propsVoto()); await consultar(d);
    assert.match(texto(d.arvore), /autor deste preço/); assert.equal(botoes(d).length, 1);
  });
  await caso("Voto selecionado fica bloqueado e troca é permitida", async () => {
    const e = ambiente(); e.getImpl = async () => ({ data: resumo({ positivos: 1, confianca_score: 2, meu_voto: "positivo" }) });
    e.postImpl = async () => ({ data: resumo({ negativos: 1, confianca_score: 0, meu_voto: "negativo" }) });
    const d = montar(e.voto.ControlesVoto, propsVoto()); await consultar(d);
    const positivo = botao(d, "Preço confere"); assert.equal(positivo.props.disabled, true);
    positivo.props.onPress(); await turno(); assert.equal(e.chamadas.length, 1);
    botao(d, "Preço está diferente").props.onPress(); await turno(); d.render();
    assert.equal(e.chamadas[1].url, "/precos/30/votar"); assert.equal(e.chamadas[1].body.voto, "negativo");
    assert.match(texto(d.arvore), /Seu voto foi registrado/); assert.equal(botao(d, "Preço está diferente").props.selected, true);
  });
  await caso("Falha de voto elimina resumo e exige GET", async () => {
    const e = ambiente(); e.postImpl = async () => { throw new Error("rede"); };
    const d = montar(e.voto.ControlesVoto, propsVoto()); await consultar(d);
    botao(d, "Preço confere").props.onPress(); await turno(); d.render();
    assert.match(texto(d.arvore), /Consulte as avaliações antes/); botao(d, "Consultar avaliações");
    assert.ok(!botoes(d).some((b) => b.props.label === "Preço confere"));
  });
  await caso("Resumo de outro ID é recusado", async () => {
    const e = ambiente(); e.getImpl = async () => ({ data: resumo({ registo_id: 31 }) });
    const d = montar(e.voto.ControlesVoto, propsVoto()); await consultar(d);
    assert.match(texto(d.arvore), /Não foi possível consultar/); assert.equal(botoes(d).length, 1);
  });
  await caso("Desmontagem aborta GET e ignora sua resposta", async () => {
    const e = ambiente(), espera = pendente(); e.getImpl = () => espera.promise;
    const d = montar(e.voto.ControlesVoto, propsVoto()); botao(d, "Consultar avaliações").props.onPress();
    d.sair(); assert.equal(e.chamadas[0].config.signal.aborted, true);
    espera.resolve({ data: resumo() }); await turno(); assert.equal(d.atualizacoesAposSaida, 0);
  });
  await caso("Novo preço e nova sessão mudam chave do voto", () => {
    const e = ambiente(), chave = e.voto.VotarPreco(propsVoto()).key;
    assert.notEqual(e.voto.VotarPreco(propsVoto({ registoId: 31 })).key, chave);
    e.auth.token = "outra-sessao-sintetica"; assert.notEqual(e.voto.VotarPreco(propsVoto()).key, chave);
  });
  await caso("Detalhes ordenam referência sem alterar a lista original", () => {
    const e = ambiente(), combustiveis = ["gnv", "etanol"].map((codigo) => ({ codigo, disponivel: null, preco: null }));
    const posto = { id: 12, nome: "Posto sintético", tipo_posto: "Convencional", combustiveis, latitude: -7.11, longitude: -34.86 };
    const d = montar(e.detalhes.DetalhesPostoConsulta, { posto, referencia: "etanol", usuario: null, erroRota: "", onErroRota() {}, onRegistrar() {}, onVoltar() {}, onAtualizar() {} });
    const cartoes = todos(d.arvore, (n) => n.type?.name === "CartaoCombustivel");
    assert.equal(cartoes[0].props.oferta.codigo, "etanol"); assert.equal(combustiveis[0].codigo, "gnv");
  });
  await caso("Cartão não referência só monta controles ao expandir", () => {
    const e = ambiente(), d = montar(e.detalhes.CartaoCombustivel, { postoId: 12, oferta: { codigo: "gnv", disponivel: null, preco: 3.5, registo_id: 30, autor_nome: "Autor sintético", atualizado_em: null }, referencia: false, podeRegistrar: true, onAtualizar() {}, onRegistrar() {} });
    assert.match(texto(d.arvore), /Autor sintético/);
    assert.equal(todos(d.arvore, (n) => n.type?.name === "VotarPreco").length, 0);
    todos(d.arvore, (n) => n.type === "Pressable")[0].props.onPress(); d.render();
    assert.equal(todos(d.arvore, (n) => n.type?.name === "VotarPreco").length, 1);
    assert.equal(todos(d.arvore, (n) => n.type === "Pressable")[0].props.accessibilityState.expanded, true);
  });
  const falhas = resultados.filter((r) => r.resultado === "falhou");
  fs.writeFileSync(path.join(__dirname, "LOGICA.json"), JSON.stringify({ tipo: "Hooks, JSX, API e GPS simulados; sem React/React Native reais", cenarios: resultados.length, aprovados: resultados.length - falhas.length, resultados }, null, 2));
  console.log(JSON.stringify({ cenarios: resultados.length, aprovados: resultados.length - falhas.length, falhas }, null, 2));
  if (falhas.length) process.exitCode = 1;
})().catch((erro) => { console.error(erro); process.exitCode = 1; });
