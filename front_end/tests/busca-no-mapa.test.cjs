/* global __dirname */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

function ambiente() {
  const e = {
    token: "sessao-sintetica-a",
    status: "AUTHENTICATED",
    focado: true,
    logins: [],
    aplicacoes: 0,
  };

  let dono;

  const hooks = {
    useState(inicial) {
      const estado = dono;
      const indice = estado.indice++;

      if (!(indice in estado.slots)) {
        estado.slots[indice] = inicial;
      }

      return [
        estado.slots[indice],
        (valor) => {
          estado.slots[indice] =
            typeof valor === "function" ? valor(estado.slots[indice]) : valor;
        },
      ];
    },
  };

  const jsx = (type, props, key) => ({
    type,
    props: props || {},
    key,
  });

  const mod = { exports: {} };

  const fonte = fs.readFileSync(
    path.join(__dirname, "../src/components/busca-no-mapa.tsx"),
    "utf8",
  );

  const js = ts.transpileModule(fonte, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
      jsx: ts.JsxEmit.ReactJSX,
    },
  }).outputText;

  const fronteiras = {
    react: hooks,

    "react/jsx-runtime": {
      jsx,
      jsxs: jsx,
      Fragment: "Fragment",
    },

    "@expo/vector-icons/Ionicons": {
      __esModule: true,
      default: "Ionicons",
    },

    "@react-navigation/native": {
      useIsFocused: () => e.focado,
    },

    "react-native": {
      Modal: "Modal",
      Pressable: "Pressable",
      View: "View",
    },

    "react-native-safe-area-context": {
      SafeAreaView: "SafeAreaView",
    },

    "../contexts/AuthContext": {
      useAuth: () => ({
        token: e.token,
        status: e.status,
        openAuth: (tela) => e.logins.push(tela),
      }),
    },

    "./busca-assistida": {
      FormularioBuscaAssistida: "FormularioBuscaAssistida",
    },

    "./design": {
      AppButton: "AppButton",
      Page: "Page",
      useAppTheme: () => ({ colors: {} }),
    },
  };

  vm.runInNewContext("(function(require,module,exports){" + js + "\n})")(
    (nome) => {
      assert.ok(nome in fronteiras, "Importação inesperada: " + nome);

      return fronteiras[nome];
    },
    mod,
    mod.exports,
  );

  let filho;

  e.render = () => {
    const elemento = mod.exports.AtalhoBuscaMapa({
      aoAplicar: () => {
        e.aplicacoes++;
      },
    });

    if (!filho || filho.key !== elemento.key || filho.type !== elemento.type) {
      filho = {
        key: elemento.key,
        type: elemento.type,
        slots: [],
      };
    }

    filho.indice = 0;
    dono = filho;
    e.arvore = elemento.type(elemento.props);
    dono = null;
  };

  e.render();

  e.abrir = () => {
    encontrar(e.arvore, "Pressable")[0].props.onPress();
    e.render();
  };

  return e;
}

function encontrar(no, tipo, itens = []) {
  if (Array.isArray(no)) {
    no.forEach((n) => encontrar(n, tipo, itens));
  } else if (no && typeof no === "object") {
    if (no.type === tipo) {
      itens.push(no);
    }

    encontrar(no.props?.children, tipo, itens);
  }

  return itens;
}

const formulario = (e) => encontrar(e.arvore, "FormularioBuscaAssistida");

test("sem sessão confirmada abre login e mantém a busca fechada", () => {
  const e = ambiente();

  e.status = "LOADING";
  e.render();
  e.abrir();

  assert.deepEqual(e.logins, ["Login"]);
  assert.equal(formulario(e).length, 0);
});

test("abre a busca da conta atual e aplicar fecha o modal", () => {
  const e = ambiente();

  e.abrir();

  const f = formulario(e)[0];

  assert.equal(f.props.token, e.token);
  assert.equal(f.props.mostrarPostos, false);

  f.props.aoAplicar();
  e.render();

  assert.equal(formulario(e).length, 0);
  assert.equal(e.aplicacoes, 1);
});

test("sair e voltar ao mapa não reabre uma busca anterior", () => {
  const e = ambiente();

  e.abrir();

  e.focado = false;
  e.render();

  assert.equal(formulario(e).length, 0);

  e.focado = true;
  e.render();

  assert.equal(formulario(e).length, 0);
});

test("trocar de conta fecha a busca antes de usar o novo token", () => {
  const e = ambiente();

  e.abrir();

  e.token = "sessao-sintetica-b";
  e.render();

  assert.equal(formulario(e).length, 0);

  e.abrir();

  assert.equal(formulario(e)[0].props.token, "sessao-sintetica-b");
});

test("logout e novo login não restauram o modal", () => {
  const e = ambiente();

  e.abrir();

  e.token = null;
  e.status = "ANONYMOUS";
  e.render();

  assert.equal(formulario(e).length, 0);

  e.token = "sessao-sintetica-c";
  e.status = "AUTHENTICATED";
  e.render();

  assert.equal(formulario(e).length, 0);
});

test("o botão fechar e o fechamento nativo dispensam a busca", () => {
  const e = ambiente();

  e.abrir();

  encontrar(e.arvore, "AppButton")[0].props.onPress();
  e.render();

  assert.equal(formulario(e).length, 0);

  e.abrir();

  encontrar(e.arvore, "Modal")[0].props.onRequestClose();
  e.render();

  assert.equal(formulario(e).length, 0);
});

test("renderizar novamente na mesma sessão mantém a busca aberta", () => {
  const e = ambiente();

  e.abrir();
  e.render();

  assert.equal(formulario(e).length, 1);
});
