/* global __dirname */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");
const { createRequire } = require("node:module");
const raiz = path.resolve(__dirname, "..");
const externo = createRequire(path.join(raiz, "package.json"));

function ambiente({
  os = "web",
  apiUrl = "http://localhost:5001",
  gps = {},
  globals = {},
} = {}) {
  const memoria = new Map(),
    eventos = [],
    cache = new Map();
  const mockStorage = {
    async getItem(k) {
      eventos.push(["web.ler", k]);
      return memoria.get(k) ?? null;
    },
    async setItem(k, v) {
      eventos.push(["web.gravar", k]);
      memoria.set(k, v);
    },
    async removeItem(k) {
      eventos.push(["web.remover", k]);
      memoria.delete(k);
    },
  };
  const mocks = {
    "react-native": { Platform: { OS: os } },
    "@react-native-async-storage/async-storage": {
      default: mockStorage,
      ...mockStorage,
    },
    "expo-secure-store": {
      async getItemAsync(k) {
        eventos.push(["secure.ler", k]);
        return memoria.get(k) ?? null;
      },
      async setItemAsync(k, v) {
        eventos.push(["secure.gravar", k]);
        memoria.set(k, v);
      },
      async deleteItemAsync(k) {
        eventos.push(["secure.remover", k]);
        memoria.delete(k);
      },
    },
    "expo-location": gps,
  };
  function carregar(nome) {
    const arquivo = path.resolve(raiz, nome);
    if (cache.has(arquivo)) return cache.get(arquivo).exports;
    const modulo = { exports: {} };
    cache.set(arquivo, modulo);
    const js = ts.transpileModule(fs.readFileSync(arquivo, "utf8"), {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
        esModuleInterop: true,
      },
    }).outputText;
    const requerer = (id) => {
      if (id in mocks) return mocks[id];
      if (id.startsWith("."))
        return carregar(
          path.relative(raiz, path.resolve(path.dirname(arquivo), id + ".ts")),
        );
      return externo(id);
    };
    vm.runInNewContext(
      "(function(require,module,exports){" + js + "\n})",
      {
        console,
        URL,
        setTimeout,
        clearTimeout,
        process: { env: { EXPO_PUBLIC_API_URL: apiUrl } },
        __DEV__: true,
        ...globals,
      },
      { filename: arquivo },
    )(requerer, modulo, modulo.exports);
    return modulo.exports;
  }
  return { carregar, memoria, eventos };
}
const perfil = {
  nome: "Teste",
  email: "dev@litro.local",
  plano: "gratis",
  karma: 0,
  membro_desde: "09/11/2026",
};
function controle(token = null, validar = async () => perfil) {
  const { criarControleSessao } = ambiente().carregar(
    "src/services/controleSessao.ts",
  );
  let salvo = token,
    ativo = null,
    removidos = 0;
  const armazenamento = {
    async ler() {
      return salvo;
    },
    async gravar(v) {
      salvo = v;
    },
    async remover() {
      salvo = null;
      removidos++;
    },
  };
  const c = criarControleSessao({
    armazenamento,
    validar,
    publicarToken: (v) => {
      ativo = v;
    },
  });
  return {
    c,
    armazenamento,
    salvo: () => salvo,
    ativo: () => ativo,
    removidos: () => removidos,
  };
}
test("sem token abre entrada sem consultar perfil", async () => {
  let chamadas = 0;
  const x = controle(null, async () => {
    chamadas++;
    return perfil;
  });
  await x.c.inicializar();
  assert.equal(x.c.getSnapshot().status, "UNAUTHENTICATED");
  assert.equal(chamadas, 0);
});
test("sessao salva so autentica depois da confirmacao", async () => {
  let responder;
  const x = controle(
    "valido",
    () =>
      new Promise((r) => {
        responder = r;
      }),
  );
  const p = x.c.inicializar();
  await new Promise(setImmediate);
  assert.equal(x.c.getSnapshot().status, "INITIALIZING");
  assert.equal(x.ativo(), null);
  responder(perfil);
  await p;
  assert.equal(x.c.getSnapshot().status, "AUTHENTICATED");
  assert.equal(x.ativo(), "valido");
});
for (const falha of [
  { response: { status: 401 } },
  { response: { status: 404, data: { code: "ACCOUNT_DELETED" } } },
  { response: { status: 404, data: { error: "Utilizador não encontrado." } } },
])
  test(
    "sessao rejeitada ou conta removida apaga token: " + JSON.stringify(falha),
    async () => {
      const x = controle("antigo", async () => {
        throw falha;
      });
      await x.c.inicializar();
      assert.equal(x.salvo(), null);
      assert.equal(x.c.getSnapshot().status, "UNAUTHENTICATED");
    },
  );
for (const falha of [
  Error("rede"),
  { code: "ECONNABORTED" },
  { response: { status: 500 } },
  { response: { status: 429 } },
  { response: { status: 404, data: { error: "Rota não encontrada." } } },
])
  test(
    "falha transitoria/generica preserva token e nao autentica: " +
      JSON.stringify(falha),
    async () => {
      const x = controle("salvo", async () => {
        throw falha;
      });
      await x.c.inicializar();
      assert.equal(x.salvo(), "salvo");
      assert.equal(x.ativo(), null);
      assert.equal(x.c.getSnapshot().status, "INITIALIZING");
      assert.ok(x.c.getSnapshot().erroInicializacao);
    },
  );
test("nova tentativa apos falha valida a sessao preservada", async () => {
  let falhar = true;
  const x = controle("salvo", async () => {
    if (falhar) throw Error("rede");
    return perfil;
  });
  await x.c.inicializar();
  falhar = false;
  await x.c.inicializar();
  assert.equal(x.ativo(), "salvo");
});
test("visitante nunca recebe token ativo e pode abrir login", async () => {
  const x = controle();
  x.c.visitante();
  assert.equal(x.c.getSnapshot().status, "GUEST");
  assert.equal(x.ativo(), null);
  x.c.abrirEntrada("Login");
  assert.equal(x.c.getSnapshot().destinoAuth, "Login");
  assert.equal(x.c.getSnapshot().status, "UNAUTHENTICATED");
});
test("login valida antes de persistir e logout remove a sessao", async () => {
  const x = controle();
  await x.c.entrar("novo");
  assert.equal(x.salvo(), "novo");
  assert.equal(x.ativo(), "novo");
  await x.c.sair();
  assert.equal(x.salvo(), null);
  assert.equal(x.ativo(), null);
});
test("login com perfil rejeitado nao persiste", async () => {
  const x = controle(null, async () => {
    throw { response: { status: 401 } };
  });
  await assert.rejects(x.c.entrar("invalido"));
  assert.equal(x.salvo(), null);
  assert.equal(x.ativo(), null);
});
test("falha ao gravar nao libera area autenticada", async () => {
  const x = controle();
  x.armazenamento.gravar = async () => {
    throw Error("storage");
  };
  await assert.rejects(x.c.entrar("novo"));
  assert.notEqual(x.c.getSnapshot().status, "AUTHENTICATED");
});
test("resposta atrasada da inicializacao nao desfaz login novo", async () => {
  let concluir;
  const x = controle("antigo", (t) =>
    t === "antigo"
      ? new Promise((r) => {
          concluir = r;
        })
      : Promise.resolve(perfil),
  );
  const antigo = x.c.inicializar();
  await new Promise(setImmediate);
  await x.c.entrar("novo");
  concluir(perfil);
  await antigo;
  assert.equal(x.ativo(), "novo");
  x.c.rejeitar("antigo");
  assert.equal(x.ativo(), "novo");
});
test("resposta apos logout nao restaura sessao", async () => {
  let concluir;
  const x = controle(
    "antigo",
    () =>
      new Promise((r) => {
        concluir = r;
      }),
  );
  const p = x.c.inicializar();
  await new Promise(setImmediate);
  await x.c.sair();
  concluir(perfil);
  await p;
  assert.equal(x.ativo(), null);
  assert.equal(x.c.getSnapshot().status, "UNAUTHENTICATED");
});
test("falha ao apagar mostra erro e permite repetir a saida", async () => {
  const x = controle("salvo");
  let falhar = true;
  x.armazenamento.remover = async () => {
    if (falhar) throw Error("storage");
  };
  await x.c.sair();
  assert.ok(x.c.getSnapshot().erroInicializacao);
  assert.equal(x.ativo(), null);
  falhar = false;
  await x.c.inicializar();
  assert.equal(x.c.getSnapshot().status, "UNAUTHENTICATED");
});
for (const os of ["web", "android", "ios"])
  test("adaptador usa armazenamento correto em " + os, async () => {
    const a = ambiente({ os });
    const s = a.carregar("src/services/sessao.ts");
    await s.armazenamentoSessao.gravar("token");
    assert.equal(await s.armazenamentoSessao.ler(), "token");
    await s.armazenamentoSessao.remover();
    assert.equal(await s.armazenamentoSessao.ler(), null);
    assert.ok(
      a.eventos.every(([nome]) =>
        nome.startsWith(os === "web" ? "web." : "secure."),
      ),
    );
  });
test("chaves diferentes por API e caracteres validos para SecureStore", () => {
  const a = ambiente();
  const { chaveDaSessao } = a.carregar("src/services/configuracao.ts");
  const local = chaveDaSessao("http://localhost:5001"),
    remota = chaveDaSessao("https://api.example.com");
  assert.notEqual(local, remota);
  assert.match(local, /^[a-zA-Z0-9._-]+$/);
});
test("API publica nao injeta token salvo ainda nao validado; visitante nao recebe JWT", async () => {
  const a = ambiente();
  const s = a.carregar("src/services/sessao.ts");
  const { api } = a.carregar("src/services/API.ts");
  await s.armazenamentoSessao.gravar("guardado");
  const adapter = async (config) => ({
    data: {},
    status: 200,
    statusText: "OK",
    headers: {},
    config,
  });
  const publico = await api.get("/postos", { adapter });
  assert.equal(publico.config.headers.get("Authorization"), undefined);
  s.definirTokenAtivo("validado");
  const privado = await api.get("/auth/perfil", { adapter });
  assert.equal(privado.config.headers.get("Authorization"), "Bearer validado");
  s.definirTokenAtivo(null);
  const visitante = await api.get("/postos", { adapter });
  assert.equal(visitante.config.headers.get("Authorization"), undefined);
});
test("401 autenticado invalida somente a sessao correspondente", async () => {
  const a = ambiente();
  const s = a.carregar("src/services/sessao.ts");
  const { api } = a.carregar("src/services/API.ts");
  const rejeitados = [];
  s.aoRejeitarToken((t) => rejeitados.push(t));
  s.definirTokenAtivo("novo");
  const { AxiosError } = externo("axios");
  const adapter = async (config) => {
    throw new AxiosError("teste", "ERR_BAD_REQUEST", config, null, {
      status: 401,
      data: {},
      config,
      headers: {},
    });
  };
  await assert.rejects(
    api.get("/auth/perfil", {
      adapter,
      headers: { Authorization: "Bearer antigo" },
    }),
  );
  assert.equal(s.lerTokenAtivo(), "novo");
  assert.equal(rejeitados.length, 0);
  await assert.rejects(api.get("/auth/perfil", { adapter }));
  assert.equal(s.lerTokenAtivo(), null);
  assert.deepEqual(rejeitados, ["novo"]);
});
const fix = (extra = {}) => ({
  coords: { latitude: -7.11, longitude: -34.86, accuracy: 20, ...extra },
  timestamp: Date.now(),
});
test("GPS valida coordenadas, precisao e idade, sem usar centro padrao", () => {
  const { validarPosicao } = ambiente().carregar("src/utils/localizacao.ts");
  const p = validarPosicao(fix(), "mapa");
  assert.equal(p.latitude, -7.11);
  assert.equal(p.precisaoM, 20);
  for (const c of [
    { latitude: 91 },
    { longitude: -181 },
    { accuracy: null },
    { accuracy: -1 },
    { accuracy: 12000 },
  ]) {
    assert.throws(() => validarPosicao(fix(c), "mapa"));
  }
  assert.equal(validarPosicao(fix({ accuracy: 8000 }), "mapa").precisaoM, 8000);
  assert.throws(() =>
    validarPosicao({ ...fix(), timestamp: Date.now() - 120000 }, "mapa"),
  );
  assert.throws(() => validarPosicao(fix({ accuracy: 200 }), "registro"));
  assert.equal(validarPosicao(fix({ accuracy: 200 }), "mapa").precisaoM, 200);
});
test("GPS negado nao pede coordenadas nem inventa posicao", async () => {
  let chamadas = 0;
  const gps = {
    getForegroundPermissionsAsync: async () => ({
      granted: false,
      canAskAgain: false,
    }),
    getCurrentPositionAsync: async () => {
      chamadas++;
      return fix();
    },
  };
  const { obterPosicao } = ambiente({ os: "android", gps }).carregar(
    "src/utils/localizacao.ts",
  );
  await assert.rejects(obterPosicao(), (e) => e.codigo === "PERMISSAO_NEGADA");
  assert.equal(chamadas, 0);
});
test("GPS atual pede alta precisao e nao usa cache antigo", async () => {
  let alta = false;
  const gps = {
    Accuracy: { High: 4 },
    getForegroundPermissionsAsync: async () => ({ granted: true }),
    hasServicesEnabledAsync: async () => true,
    getCurrentPositionAsync: async (op) => {
      alta = op.accuracy === 4;
      return fix();
    },
    getLastKnownPositionAsync: async () => {
      throw Error("nao deve consultar cache");
    },
  };
  const { obterPosicao } = ambiente({ os: "android", gps }).carregar(
    "src/utils/localizacao.ts",
  );
  assert.equal((await obterPosicao()).longitude, -34.86);
  assert.equal(alta, true);
});
test("GPS indisponivel tem limite de tempo e nao inventa fallback", async () => {
  const gps = {
    Accuracy: { High: 4 },
    getForegroundPermissionsAsync: async () => ({ granted: true }),
    hasServicesEnabledAsync: async () => true,
    getCurrentPositionAsync: () => new Promise(() => {}),
  };
  const { obterPosicao } = ambiente({
    os: "android",
    gps,
    globals: { setTimeout: (fn) => setTimeout(fn, 5) },
  }).carregar("src/utils/localizacao.ts");
  await assert.rejects(obterPosicao(), (e) => e.codigo === "TIMEOUT");
});
