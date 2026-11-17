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
