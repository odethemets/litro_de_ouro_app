/* global __dirname */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

function carregar(nome) {
  const arquivo = path.resolve(__dirname, "../src/services", nome + ".ts");
  const modulo = { exports: {} };
  const js = ts.transpileModule(fs.readFileSync(arquivo, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  vm.runInNewContext("(function(require,module,exports){" + js + "\n})", { Date, Number, Set })(
    (alvo) => carregar(alvo.replace("./", "")), modulo, modulo.exports);
  return modulo.exports;
}
const ofertas = carregar("ofertas");
const votos = carregar("votos");
const agora = Date.now();
const gps = { latitude: -7.11, longitude: -34.86, precisaoM: 15, obtidaEm: agora, simulada: false };
test("confirmacao explicita envia apenas oferta e GPS, sem preco ou Karma", () => {
  const p = ofertas.payloadOferta(gps, agora);
  assert.equal(p.confirmado, true);
  assert.equal(p.simulada, false);
  assert.equal(p.latitude, gps.latitude);
  assert.equal(p.preco, undefined);
  assert.equal(p.karma, undefined);
});
test("oferta recusa GPS antigo, impreciso, simulado ou invalido", () => {
  for (const mudanca of [{ latitude: NaN }, { longitude: 181 }, { latitude: 0, longitude: 0 },
    { precisaoM: 151 }, { precisaoM: -1 }, { precisaoM: Infinity }, { simulada: true },
    { obtidaEm: agora - 15001 }, { obtidaEm: agora + 5001 }]) {
    assert.throws(() => ofertas.payloadOferta({ ...gps, ...mudanca }, agora));
  }
});
test("oferta exige resposta do mesmo posto e produto", () => {
  const ok = { posto_id: 10, codigo: "gnv", disponivel: true, origem: "manual" };
  ofertas.validarConfirmacaoOferta(ok, 10, "gnv");
  for (const mudanca of [{ posto_id: 11 }, { codigo: "diesel" }, { disponivel: false }, { origem: null }]) {
    assert.throws(() => ofertas.validarConfirmacaoOferta({ ...ok, ...mudanca }, 10, "gnv"));
  }
});
test("confirmacao idempotente conserva origem OSM", () => {
  ofertas.validarConfirmacaoOferta({ posto_id: 10, codigo: "gnv", disponivel: true, origem: "osm" }, 10, "gnv");
});
const avaliacao = { registo_id: 20, positivos: 0, negativos: 0, confianca_score: 1, meu_voto: null, pode_votar: false };
test("pontuacao inicial nao fabrica confirmacoes nem libera voto proprio", () => {
  const r = votos.lerAvaliacao(avaliacao, 20);
  assert.equal(r.positivos, 0);
  assert.equal(r.confianca_score, 1);
  assert.equal(r.pode_votar, false);
});
test("avaliacao identifica registro exato", () => {
  assert.throws(() => votos.lerAvaliacao(avaliacao, 21));
});
test("avaliacao recusa contagens e tipos invalidos", () => {
  for (const mudanca of [{ positivos: -1 }, { negativos: 1.5 }, { positivos: "1" },
    { confianca_score: NaN }, { pode_votar: 1 }, { meu_voto: "sim" }]) {
    assert.throws(() => votos.lerAvaliacao({ ...avaliacao, ...mudanca }, 20));
  }
});
test("voto negativo e pontuacao negativa sao dados validos", () => {
  const r = votos.lerAvaliacao({ ...avaliacao, negativos: 3, confianca_score: -2, meu_voto: "negativo", pode_votar: true }, 20);
  assert.equal(r.meu_voto, "negativo");
  assert.equal(r.confianca_score, -2);
});
