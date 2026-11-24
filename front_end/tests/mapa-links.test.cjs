/* global __dirname */
const test = require("node:test");
const assert = require("node:assert/strict");
const { existsSync, readFileSync } = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

function preparar() {
  const arquivos = ["mapaHtml.ts", "mapaHtml.tsx"]
    .map((nome) => path.join(__dirname, "../src/components/mapa", nome))
    .filter((arquivo) => existsSync(arquivo));

  assert.equal(
    arquivos.length,
    1,
    "Mantenha apenas um mapaHtml.ts ou mapaHtml.tsx.",
  );

  const { outputText } = ts.transpileModule(readFileSync(arquivos[0], "utf8"), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
    },
  });

  const modulo = { exports: {} };

  vm.runInNewContext(outputText, {
    module: modulo,
    exports: modulo.exports,
    process: { env: {} },
    require(id) {
      assert.equal(id, "../../utils/precisaoGps");
      return { PRECISAO_MAPA_MAX_M: 200 };
    },
  });

  const html = modulo.exports.MAPA_HTML;
  const script = html.match(/<script>([\s\S]*?)<\/script>/)?.[1];

  assert.ok(script, "O HTML precisa conter o script do mapa.");

  let aoClicar;
  const enviados = [];

  const mapa = {
    setView() {
      return mapa;
    },
    on() {
      return mapa;
    },
  };

  const camada = () => ({
    addTo() {},
  });

  const janela = {
    parent: {
      postMessage: (json) => enviados.push(JSON.parse(json)),
    },
    addEventListener() {},
  };

  vm.runInNewContext(script, {
    window: janela,
    document: {
      addEventListener(tipo, callback) {
        if (tipo === "click") aoClicar = callback;
      },
    },
    L: {
      map: () => mapa,
      control: {
        attribution: camada,
        zoom: camada,
      },
      tileLayer: camada,
    },
    setTimeout,
    clearTimeout,
  });

  assert.equal(typeof aoClicar, "function");
  enviados.length = 0;

  function clicar(href, filho = false) {
    const ancora = {
      tagName: "A",
      getAttribute: (nome) => (nome === "href" ? href : null),
      href: new URL(href, "https://app.example/").href,
      parentElement: null,
    };

    const evento = {
      target: filho ? { tagName: "SPAN", parentElement: ancora } : ancora,
      defaultPrevented: false,
      preventDefault() {
        this.defaultPrevented = true;
      },
    };

    aoClicar(evento);
    return evento;
  }

  return { clicar, enviados };
}

test("zoom + não encaminha o endereço do próprio aplicativo", () => {
  const t = preparar();

  assert.equal(t.clicar("#").defaultPrevented, false);
  assert.deepEqual(t.enviados, []);
});

test("zoom - com elemento filho mantém o clique sob controle do Leaflet", () => {
  const t = preparar();

  assert.equal(t.clicar("#", true).defaultPrevented, false);
  assert.deepEqual(t.enviados, []);
});

test("fragmentos internos não viram links externos", () => {
  const t = preparar();

  t.clicar("#mapa");

  assert.deepEqual(t.enviados, []);
});

test("atribuição HTTPS continua abrindo pelo aplicativo", () => {
  const t = preparar();
  const url = "https://www.openstreetmap.org/copyright";

  assert.equal(t.clicar(url, true).defaultPrevented, true);
  assert.deepEqual(t.enviados, [{ tipo: "abrir_link", url }]);
});

for (const href of ["http://example.test/", "javascript:void(0)", "/mapa"]) {
  test("bloqueia navegação do mapa para " + href, () => {
    const t = preparar();

    assert.equal(t.clicar(href).defaultPrevented, true);
    assert.deepEqual(t.enviados, []);
  });
}

test("âncora sem destino não encaminha endereço implícito", () => {
  const t = preparar();

  t.clicar("");

  assert.deepEqual(t.enviados, []);
});
