/* global __dirname */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");
const source = fs.readFileSync(
  path.join(__dirname, "../src/services/catalogoPostos.ts"),
  "utf8",
);
const modulo = { exports: {} };
const js = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;
vm.runInNewContext("(function(exports){" + js + "\n})", {
  console,
  Date,
  Number,
  Set,
})(modulo.exports);
const c = modulo.exports;
const simples = (v) => JSON.parse(JSON.stringify(v));
function posto() {
  return {
    id: 1,
    nome: "Teste",
    latitude: -7.11,
    longitude: -34.86,
    combustivel_referencia: "gasolina_comum",
    preco_referencia: 5.89,
    combustiveis: c.COMBUSTIVEIS.map((p) => ({
      codigo: p.codigo,
      disponivel: p.codigo === "etanol" ? true : null,
      origem: p.codigo === "etanol" ? "osm" : null,
      preco:
        p.codigo === "gasolina_comum"
          ? 5.89
          : p.codigo === "etanol"
            ? 4.29
            : null,
      atualizado_em: null,
      autor_nome: null,
    })),
  };
}
test("selecao inicial define primeira referencia e preserva ordem", () => {
  let f = c.alternarCombustivel(c.FILTROS_INICIAIS, "etanol");
  f = c.alternarCombustivel(f, "gasolina_comum");
  assert.equal(f.referencia, "etanol");
  assert.deepEqual(simples(f.combustiveis), ["etanol", "gasolina_comum"]);
});
test("remover referencia escolhe proximo produto selecionado", () => {
  const f = c.alternarCombustivel(
    {
      combustiveis: ["etanol", "diesel"],
      referencia: "etanol",
      marca: "Shell",
      ordenar: "preco",
    },
    "etanol",
  );
  assert.equal(f.referencia, "diesel");
  assert.equal(f.marca, "Shell");
});
test("segmentos sao intersecao de selecao e oferta confirmada", () => {
  const p = c.lerCatalogo([posto()], "gasolina_comum")[0];
  assert.deepEqual(simples(c.segmentosPosto(p, ["gasolina_comum"])), []);
  assert.deepEqual(
    simples(
      c.segmentosPosto(p, ["gasolina_comum", "etanol"]).map((o) => o.codigo),
    ),
    ["etanol"],
  );
});
test("todos exibe apenas segmentos confirmados", () => {
  const p = c.lerCatalogo([posto()], "gasolina_comum")[0];
  assert.deepEqual(simples(c.segmentosPosto(p, []).map((o) => o.codigo)), [
    "etanol",
  ]);
});
test("preco ausente nao usa preco de outro produto", () => {
  const p = posto();
  p.preco_referencia = null;
  p.combustiveis[0].preco = null;
  assert.equal(
    c.rotuloPreco(c.lerCatalogo([p], "gasolina_comum")[0]),
    "Ver preços",
  );
});
test("oferta confirmada sem preco tem estado proprio", () => {
  const p = posto();
  p.preco_referencia = null;
  p.combustiveis[0].preco = null;
  p.combustiveis[0].disponivel = true;
  assert.equal(
    c.rotuloPreco(c.lerCatalogo([p], "gasolina_comum")[0]),
    "Sem preço informado",
  );
});
test("referencia divergente e resposta invalida sao erros", () => {
  for (const p of [{}, null, [posto()]])
    assert.throws(() => c.lerCatalogo(p, "etanol"));
});
test("preco generico e numeros invalidos nao viram dados validos", () => {
  for (const preco of [undefined, 0, -1, NaN, Infinity, "5.89"]) {
    const p = posto();
    p.combustiveis[0].preco = preco;
    assert.throws(() => c.lerCatalogo([p], "gasolina_comum"));
  }
});
test("parametros nao inventam coordenadas para GPS ausente", () => {
  const p = c.parametrosPostos(c.FILTROS_INICIAIS, null);
  assert.ok(!("lat" in p));
  assert.ok(!("combustiveis" in p));
  assert.equal(
    c.parametrosPostos(c.FILTROS_INICIAIS, { lat: -7.11, lon: -34.86 }).lng,
    -34.86,
  );
});
test("paleta preserva seis identidades e unidades", () => {
  assert.equal(c.COMBUSTIVEIS.length, 6);
  assert.equal(c.produto("recarga_eletrica").cor, "#C026D3");
  assert.equal(c.produto("gnv").unidade, "m³");
  assert.equal(c.produto("recarga_eletrica").unidade, "kWh");
});
const agora = Date.parse("2026-11-11T15:00:00Z");
function recente(id, valor, data = "2026-11-11T09:30:00") {
  const p = posto();
  p.id = id;
  p.preco_referencia = valor;
  p.combustiveis[0].preco = valor;
  p.combustiveis[0].atualizado_em = data;
  return c.lerCatalogo([p], "gasolina_comum")[0];
}
test("classificacao usa tercos do intervalo de precos recentes da referencia", () => {
  const lista = [recente(1, 5), recente(2, 6), recente(3, 7)];
  assert.equal(c.classificarPreco(lista[0], lista, agora).cor, "#166534");
  assert.equal(c.classificarPreco(lista[1], lista, agora).cor, "#8A6500");
  assert.equal(c.classificarPreco(lista[2], lista, agora).cor, "#B42318");
});
test("preco antigo ou sem atualizacao nao distorce classificacao", () => {
  const lista = [
    recente(1, 5),
    recente(2, 6),
    recente(3, 1, "2026-10-01T10:00:00"),
    recente(4, 1, null),
  ];
  assert.equal(c.classificarPreco(lista[1], lista, agora).cor, "#B42318");
  assert.equal(c.classificarPreco(lista[2], lista, agora).cor, "#596273");
  assert.equal(c.classificarPreco(lista[3], lista, agora).cor, "#596273");
});
test("um unico preco ou valores iguais ficam neutros", () => {
  const a = recente(1, 5),
    b = recente(2, 5);
  assert.equal(c.classificarPreco(a, [a], agora).cor, "#171923");
  assert.equal(c.classificarPreco(a, [a, b], agora).cor, "#171923");
});
test("produto diferente e data futura nao entram na comparacao", () => {
  const a = recente(1, 5),
    b = recente(2, 6),
    outro = recente(3, 1);
  outro.combustivel_referencia = "etanol";
  const futuro = recente(4, 1, "2026-12-01T10:00:00");
  assert.equal(
    c.classificarPreco(a, [a, b, outro, futuro], agora).cor,
    "#166534",
  );
  assert.equal(
    c.classificarPreco(futuro, [a, b, futuro], agora).cor,
    "#596273",
  );
});
test("referencia desconhecida no filtro multiplo mostra Ver precos mesmo com registro historico", () => {
  const p = posto();
  p.preco_referencia = null;
  const resultado = c.lerCatalogo([p], "gasolina_comum", [
    "gasolina_comum",
    "etanol",
  ])[0];
  assert.equal(c.rotuloPreco(resultado), "Ver preços");
  assert.equal(resultado.combustiveis[0].preco, 5.89);
});
