/* global __dirname */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

function load(file, deps = {}) {
  const module = { exports: {} };

  const source = fs.readFileSync(
    path.resolve(__dirname, "../src", file),
    "utf8",
  );

  vm.runInNewContext(
    ts.transpileModule(source, {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
      },
    }).outputText,
    {
      module,
      exports: module.exports,
      require: (name) => {
        if (Object.hasOwn(deps, name)) return deps[name];
        throw Error("Dependência inesperada: " + name);
      },
    },
  );

  return module.exports;
}

const s = load("services/atividadeConta.ts", {
  "../theme/design": load("theme/design.ts"),
});

const base = {
  id: 1,
  posto_nome: "Posto A",
  posto_endereco: "Rua A",
  tipo_combustivel: "Gasolina Comum",
  preco: 5.89,
  data_formatada: "10/11/2026 09:40",
};

test("historico preserva IDs, produto e data e aceita decimal serializado", () => {
  const [r] = s.validarRegistos([{ ...base, preco: "5.89" }]);
  assert.deepEqual(JSON.parse(JSON.stringify(r)), base);
});

test("historico distingue vazio valido de resposta invalida", () => {
  assert.equal(s.validarRegistos([]).length, 0);

  for (const value of [null, {}, "", [null], [{ ...base, posto_nome: null }]]) {
    assert.throws(() => s.validarRegistos(value));
  }
});

test("precos ausentes, invalidos ou nao positivos nao viram zero", () => {
  for (const preco of [
    null,
    undefined,
    "",
    "5,89",
    "Infinity",
    NaN,
    Infinity,
    0,
    -1,
  ]) {
    assert.throws(() => s.validarRegistos([{ ...base, preco }]));
  }
});

test("IDs invalidos e duplicados nao sao renderizados como contribuicoes validas", () => {
  for (const id of [0, -1, 1.5, "1"]) {
    assert.throws(() => s.validarRegistos([{ ...base, id }]));
  }

  assert.throws(() => s.validarRegistos([base, base]));
});

test("unidades e cores acompanham o produto original", () => {
  for (const [tipo, cor, unidade] of [
    ["Gasolina Comum", "#1D4ED8", "L"],
    ["gasolina_aditivada", "#0891B2", "L"],
    ["Etanol", "#7C3AED", "L"],
    ["Diesel", "#374151", "L"],
    ["GNV", "#8B5E3C", "m³"],
    ["Recarga Elétrica (kWh)", "#C026D3", "kWh"],
  ]) {
    const p = s.produtoHistorico(tipo);
    assert.equal(p.cor, cor);
    assert.equal(p.unidade, unidade);
  }
});

test("produto desconhecido nao herda unidade nem cor da gasolina", () => {
  assert.equal(s.produtoHistorico("Outro produto"), null);
  assert.equal(s.produtoHistorico("toString"), null);
});

test("historico local ausente e vazio; corrompido e erro", () => {
  assert.equal(s.validarVistos(null).length, 0);

  for (const raw of ["x", "{}", "[null]", '[{"id":1}]']) {
    assert.throws(() => s.validarVistos(raw));
  }
});

test("historico local preserva endereco e data sem inventar GPS", () => {
  const p = {
    id: 1,
    nome: "Posto A",
    endereco: "Rua A",
    dataVisualizacao: "10/11/2026",
  };

  assert.deepEqual(
    JSON.parse(JSON.stringify(s.validarVistos(JSON.stringify([p])))),
    [p],
  );
});

test("iniciais toleram espacos, nome unico e vazio", () => {
  assert.equal(s.iniciaisNome("  Pedro   Henrique Silva "), "PH");
  assert.equal(s.iniciaisNome("Ana"), "A");
  assert.equal(s.iniciaisNome(" "), "U");
});

test("valor monetario usa duas casas e separador brasileiro", () => {
  assert.equal(s.formatarPreco(5.89), "5,89");
  assert.equal(s.formatarPreco(2.2), "2,20");
});
