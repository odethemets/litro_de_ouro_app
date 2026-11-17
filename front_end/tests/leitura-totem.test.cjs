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
