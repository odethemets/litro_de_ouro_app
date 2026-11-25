/* global __dirname */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

const arquivo = path.join(__dirname, "../src/services/catalogoPostos.ts");

const modulo = { exports: {} };

const js = ts.transpileModule(fs.readFileSync(arquivo, "utf8"), {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;

vm.runInNewContext(js, {
  module: modulo,
  exports: modulo.exports,
  Date,
  Number,
});

const c = modulo.exports;

function bruto() {
  return {
    id: 1,
    nome: "Posto de teste",
    latitude: -7.11,
    longitude: -34.86,
    tipo_posto: "Convencional",
    combustivel_referencia: "gasolina_comum",
    preco_referencia: 6.2,
    combustiveis: c.COMBUSTIVEIS.map(({ codigo }) => ({
      codigo,
      disponivel: null,
      origem: null,
      preco: codigo === "gasolina_comum" ? 6.2 : null,
      atualizado_em: null,
      autor_nome: null,
      registo_id: null,
      ...(codigo === "gasolina_comum"
        ? {
            estimativa: {
              fonte: "ANP",
              tipo: "media_municipal",
              municipio: "JOAO PESSOA",
              uf: "PB",
              periodo_inicio: "2026-11-15",
              periodo_fim: "2026-11-21",
              amostra: 19,
            },
          }
        : {}),
    })),
  };
}

test("média é identificada no preço e na descrição com período", () => {
  const posto = c.lerCatalogo([bruto()], "gasolina_comum")[0];

  assert.equal(c.rotuloPreco(posto), "≈ R$ 6,20");

  const descricao = c.descricaoPreco(c.ofertaReferencia(posto));

  assert.match(descricao, /Estimativa/);
  assert.match(descricao, /15\/11\/2026 a 21\/11\/2026/);
  assert.match(descricao, /Não é preço observado/);
});

test("média não inventa disponibilidade, autoria ou registro votável", () => {
  const posto = c.lerCatalogo([bruto()], "gasolina_comum")[0];
  const oferta = c.ofertaReferencia(posto);

  assert.equal(oferta.disponivel, null);
  assert.equal(oferta.autor_nome, null);
  assert.equal(oferta.registo_id, null);
  assert.equal(oferta.atualizado_em, null);
  assert.equal(c.segmentosPosto(posto, []).length, 0);
});

test("média tem cor neutra e não entra na comparação de preços recentes", () => {
  const media = c.lerCatalogo([bruto()], "gasolina_comum")[0];

  assert.equal(c.classificarPreco(media, [media]).cor, "#596273");

  const dados = bruto();

  delete dados.combustiveis[0].estimativa;

  dados.combustiveis[0].atualizado_em = "2026-11-24T12:00:00-03:00";

  const real = c.lerCatalogo([dados], "gasolina_comum")[0];

  assert.equal(
    c.classificarPreco(real, [real, media], Date.parse("2026-11-24T16:00:00Z"))
      .texto,
    "Sem diferença de preço para comparar",
  );
});

test("procedência misturada com registro ou autoria é recusada", () => {
  for (const campo of ["registo_id", "autor_nome", "atualizado_em"]) {
    const posto = bruto();

    posto.combustiveis[0][campo] =
      campo === "registo_id" ? 90001 : "dado misturado";

    assert.throws(() => c.lerCatalogo([posto], "gasolina_comum"));
  }
});

test("fonte, período, amostra ou estado incompatíveis são recusados", () => {
  const alteracoes = [
    ["fonte", "outra"],
    ["periodo_inicio", "2026-11-22"],
    ["amostra", 0],
    ["amostra", true],
    ["municipio", "OUTRO"],
  ];

  for (const [campo, valor] of alteracoes) {
    const posto = bruto();

    posto.combustiveis[0].estimativa[campo] = valor;

    assert.throws(() => c.lerCatalogo([posto], "gasolina_comum"));
  }

  const posto = bruto();

  posto.combustiveis[0].disponivel = false;
  posto.preco_referencia = null;

  assert.throws(() => c.lerCatalogo([posto], "gasolina_comum"));
});

test("preço real mantém apresentação anterior", () => {
  const dados = bruto();

  delete dados.combustiveis[0].estimativa;

  dados.combustiveis[0].autor_nome = "Autor de teste";
  dados.combustiveis[0].registo_id = 90001;

  const posto = c.lerCatalogo([dados], "gasolina_comum")[0];

  assert.equal(c.rotuloPreco(posto), "R$ 6,20");

  assert.match(
    c.descricaoPreco(c.ofertaReferencia(posto)),
    /Informado por Autor de teste/,
  );
});

test("cliente pede estimativas explicitamente; contrato antigo fica disponível", () => {
  assert.equal(
    c.parametrosPostos(c.FILTROS_INICIAIS).incluir_estimativas,
    undefined,
  );

  assert.equal(
    c.parametrosPostos(c.FILTROS_INICIAIS, null, true).incluir_estimativas,
    "1",
  );
});

test("seleção de combustível continua exigindo oferta confirmada", () => {
  const dados = bruto();

  dados.preco_referencia = null;

  const posto = c.lerCatalogo([dados], "gasolina_comum", ["gasolina_comum"])[0];

  assert.equal(posto.preco_referencia, null);
});
