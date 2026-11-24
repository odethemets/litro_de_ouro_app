/* global __dirname */
// Componentes reais com hooks, JSX, rede e GPS simulados.
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");
const assert = require("node:assert/strict");

let corrente;

const jsx = (type, props, key) => ({
  type,
  props: props || {},
  key,
});

const hooks = {
  useState(inicial) {
    const dono = corrente;
    const i = dono.indice++;

    if (!(i in dono.slots)) {
      dono.slots[i] = typeof inicial === "function" ? inicial() : inicial;
    }

    return [
      dono.slots[i],
      (v) => {
        if (!dono.montado) {
          dono.atualizacoesAposSaida++;
        }

        dono.slots[i] = typeof v === "function" ? v(dono.slots[i]) : v;
      },
    ];
  },

  useRef(inicial) {
    const dono = corrente;
    const i = dono.indice++;

    if (!(i in dono.slots)) {
      dono.slots[i] = {
        current: inicial,
      };
    }

    return dono.slots[i];
  },

  useCallback(fn, deps) {
    const dono = corrente;
    const i = dono.indice++;
    const antes = dono.slots[i];

    if (!antes || deps.some((v, j) => !Object.is(v, antes.deps[j]))) {
      dono.slots[i] = {
        deps,
        fn,
      };
    }

    return dono.slots[i].fn;
  },

  useEffect(fn, deps) {
    const dono = corrente;
    const i = dono.indice++;
    const antes = dono.slots[i];

    if (!antes || deps.some((v, j) => !Object.is(v, antes.deps[j]))) {
      dono.efeitos.push(() => {
        antes?.cleanup?.();

        dono.slots[i] = {
          deps,
          cleanup: fn(),
        };
      });
    }
  },
};

const turno = () => new Promise((r) => setImmediate(r));

const foto = () => ({
  uri: "file:///foto-sintetica.jpg",
  width: 100,
  height: 100,
  fileSize: 500,
  mimeType: "image/jpeg",
  type: "image",
});

function pendente() {
  let resolve;

  const promise = new Promise((r) => {
    resolve = r;
  });

  return {
    promise,
    resolve,
  };
}

function item(extra = {}) {
  return {
    id: 10,
    posto_id: 1,
    posto_nome: "Posto sintético",
    posto_endereco: "Endereço fictício",
    codigo: "recarga_eletrica",
    observacao: "Carregador",
    estado: "pendente",
    motivo: null,
    criado_em: "2026-11-23T10:00:00Z",
    revisado_em: null,
    distancia_m: 5,
    precisao_m: 10,
    pode_revisar: true,
    ...extra,
  };
}

function ambiente() {
  const e = {
    plataforma: "android",
    auth: {
      token: "sessao-sintetica",
      status: "AUTHENTICATED",
    },
    chamadas: [],
    recargas: 0,
    token: "sessao-sintetica",
  };

  e.pick = async () => ({
    canceled: false,
    assets: [foto()],
  });

  e.gps = async () => ({
    latitude: -7.11,
    longitude: -34.86,
    precisaoM: 10,
    obtidaEm: Date.now(),
    simulada: false,
  });

  e.post = async () => ({
    status: 201,
    data: item({
      pode_revisar: false,
    }),
  });

  e.get = async () => ({
    data: {
      itens: [item()],
      antes_de: null,
    },
  });

  const cache = new Map();

  function carregar(rel) {
    if (cache.has(rel)) {
      return cache.get(rel);
    }

    const arquivo = path.resolve(__dirname, "../src", rel);

    let fonte = fs.readFileSync(arquivo, "utf8");

    if (rel.endsWith("solicitar-servico.tsx")) {
      fonte += "\nexport { FormularioServico };";
    }

    if (rel.endsWith("leitor-totem.tsx")) {
      fonte += "\nexport { ConteudoLeitor };";
    }

    if (rel.endsWith("painel-servicos.tsx")) {
      fonte += "\nexport { ConteudoPainel };";
    }

    const js = ts.transpileModule(fonte, {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
        jsx: ts.JsxEmit.ReactJSX,
      },
    }).outputText;

    const modulo = {
      exports: {},
    };

    vm.runInNewContext("(function(require,module,exports){" + js + "\n})", {
      Date,
      Error,
      Number,
      AbortController,
      Blob,
      FormData,
      URL,
      Set,
      Map,
    })(
      (nome) => {
        if (nome === "react") {
          return hooks;
        }

        if (nome === "react/jsx-runtime") {
          return {
            jsx,
            jsxs: jsx,
          };
        }

        if (nome === "@react-navigation/native") {
          return {
            useFocusEffect: (fn) => hooks.useEffect(fn, [fn]),
          };
        }

        if (nome === "react-native") {
          return {
            View: "View",
            Image: "Image",
            Text: "Text",
            Modal: "Modal",
            ScrollView: "ScrollView",
            Platform: {
              get OS() {
                return e.plataforma;
              },
            },
          };
        }

        if (nome === "react-native-safe-area-context") {
          return {
            SafeAreaView: "SafeAreaView",
          };
        }

        if (nome === "expo-image-picker") {
          return {
            getPendingResultAsync: async () => null,
            launchImageLibraryAsync: (...a) => e.pick(...a),
          };
        }

        if (nome.endsWith("/AuthContext")) {
          return {
            useAuth: () => e.auth,
          };
        }

        if (nome.endsWith("/FiltrosPostosContext")) {
          return {
            useFiltrosPostos: () => ({
              recarregar: () => {
                e.recargas++;
              },
            }),
          };
        }

        if (nome.endsWith("/sessao")) {
          return {
            lerTokenAtivo: () => e.token,
          };
        }

        if (nome.endsWith("/localizacao")) {
          return {
            obterPosicao: () => e.gps(),
          };
        }

        if (nome.endsWith("/API")) {
          return {
            api: {
              post: (...a) => {
                e.chamadas.push(["POST", ...a]);
                return e.post(...a);
              },

              get: (...a) => {
                e.chamadas.push(["GET", ...a]);
                return e.get(...a);
              },
            },
          };
        }

        if (nome.endsWith("/design")) {
          return {
            AppButton: "AppButton",
            AppField: "AppField",
            Notice: "Notice",
            Surface: "Surface",
            useAppTheme: () => ({
              colors: {},
            }),
          };
        }

        const base = path.resolve(path.dirname(arquivo), nome);

        const ext = [".ts", ".tsx"].find((s) => fs.existsSync(base + s));

        if (!ext) {
          throw new Error("Import não simulado: " + nome);
        }

        return carregar(
          path.relative(path.resolve(__dirname, "../src"), base + ext),
        );
      },
      modulo,
      modulo.exports,
    );

    cache.set(rel, modulo.exports);

    return modulo.exports;
  }

  // Carrega somente o componente usado pelo teste.
  // Arquivo ausente continua causando erro quando necessário.
  const componentes = {
    formulario: "components/servicos/solicitar-servico.tsx",
    painel: "components/servicos/painel-servicos.tsx",
    leitor: "components/leitor-totem.tsx",
    cadastro: "screens/AdicionarPreco/useCadastroLote.ts",
  };

  for (const [nome, arquivo] of Object.entries(componentes)) {
    Object.defineProperty(e, nome, {
      enumerable: true,
      get: () => carregar(arquivo),
    });
  }

  return e;
}

function montar(fn, inicial) {
  let props = inicial;

  const d = {
    slots: [],
    indice: 0,
    efeitos: [],
    montado: true,
    atualizacoesAposSaida: 0,

    render(novos = {}) {
      props = {
        ...props,
        ...novos,
      };

      this.indice = 0;
      this.efeitos = [];
      corrente = this;

      try {
        this.arvore = fn(props);
      } finally {
        corrente = null;
      }

      for (const efeito of this.efeitos) {
        efeito();
      }
    },

    sair() {
      this.montado = false;

      for (const s of this.slots) {
        s?.cleanup?.();
      }
    },
  };

  d.render();

  return d;
}

function todos(n, tipo, itens = []) {
  if (Array.isArray(n)) {
    n.forEach((x) => todos(x, tipo, itens));
  } else if (n && typeof n === "object") {
    if (n.type === tipo) {
      itens.push(n);
    }

    todos(n.props?.children, tipo, itens);
  }

  return itens;
}

function botao(d, nome) {
  const b = todos(d.arvore, "AppButton").find((x) => x.props.label === nome);

  assert.ok(b, "Botão ausente: " + nome);

  return b;
}

async function clicar(d, nome) {
  botao(d, nome).props.onPress();

  await turno();
  d.render();
}

module.exports = {
  ambiente,
  montar,
  todos,
  botao,
  clicar,
  pendente,
  turno,
  foto,
  item,
};
