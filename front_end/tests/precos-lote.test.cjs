const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

const cache = new Map();

function carregar(nome) {
  const arquivo = path.join(__dirname, "../src/services", nome + ".ts");

  if (cache.has(arquivo)) return cache.get(arquivo).exports;

  const modulo = { exports: {} };
  cache.set(arquivo, modulo);

  const { outputText } = ts.transpileModule(fs.readFileSync(arquivo, "utf8"), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
  });

  vm.runInNewContext(
    outputText,
    {
      module: modulo,
      exports: modulo.exports,
      Error,
      Date,
      Set,
      require(id) {
        if (id.startsWith("./")) return carregar(id.slice(2));
        throw new Error("Dependencia inesperada: " + id);
      },
    },
    { filename: arquivo },
  );

  return modulo.exports;
}

const { COMBUSTIVEIS } = carregar("catalogoPostos");
const { criarEnvioPrecosLote, payloadPrecosLote } = carregar("precosLote");
const { lerTextoPrecos, mesclarSugestoes } = carregar("rascunhoPrecos");

const normal = (v) => JSON.parse(JSON.stringify(v));
const tipo = (esperado) => (erro) => erro.tipo === esperado;

const gps = () => ({
  latitude: -7.115,
  longitude: -34.861,
  precisaoM: 10,
  obtidaEm: Date.now(),
  simulada: false,
});

function pedido() {
  return {
    token: "sessao-de-teste",
    posto: {
      id: 11,
      nome: "Posto de teste",
      latitude: -7.115,
      longitude: -34.861,
      tipo_posto: "Posto",
      combustiveis: COMBUSTIVEIS.map((p) => ({
        codigo: p.codigo,
        disponivel: p.codigo === "recarga_eletrica" ? null : true,
      })),
    },
    itens: [
      {
        codigo: "gasolina_comum",
        textoPreco: "6,19",
        fotoUrl: "https://www.dropbox.com/s/teste/foto.jpg",
      },
      {
        codigo: "etanol",
        textoPreco: "4,29",
        fotoUrl: null,
      },
    ],
  };
}

function resposta(payload) {
  return {
    status: 201,
    data: {
      posto_id: 11,
      total: payload.itens.length,
      karma_ganho: payload.itens.length * 5,
      registros: payload.itens.map((i, indice) => ({
        tipo_combustivel: i.tipo_combustivel,
        preco: i.preco,
        registo_id: 101 + indice,
        karma_ganho: 5,
      })),
    },
  };
}

function preparar(extras = {}) {
  const chamadas = [];
  let leituras = 0;

  const fluxo = criarEnvioPrecosLote({
    tokenAtual: () => "sessao-de-teste",
    obterGps: async () => {
      leituras++;
      return gps();
    },
    postar: async (payload, token) => {
      chamadas.push({ payload, token });
      return resposta(payload);
    },
    ...extras,
  });

  return {
    fluxo,
    chamadas,
    leituras: () => leituras,
  };
}

test("envia dois precos em uma chamada e consulta GPS uma vez", async () => {
  const t = preparar();
  const r = await t.fluxo.enviar(pedido());

  assert.equal(t.leituras(), 1);
  assert.equal(t.chamadas.length, 1);

  assert.deepEqual(normal(t.chamadas[0].payload.itens), [
    {
      tipo_combustivel: "Gasolina Comum",
      preco: "6.19",
      foto_url: "https://www.dropbox.com/s/teste/foto.jpg",
    },
    {
      tipo_combustivel: "Etanol",
      preco: "4.29",
    },
  ]);

  assert.equal(r.karmaGanho, 10);
  assert.deepEqual(
    Array.from(r.registros, (i) => i.registoId),
    [101, 102],
  );
});

test("lote vazio, repetido ou com preco invalido e recusado antes do GPS", async () => {
  for (const itens of [
    [],
    [pedido().itens[0], pedido().itens[0]],
    [{ codigo: "etanol", textoPreco: "4.299" }],
  ]) {
    const t = preparar();

    await assert.rejects(
      t.fluxo.enviar({ ...pedido(), itens }),
      tipo("validacao"),
    );

    assert.equal(t.leituras(), 0);
    assert.equal(t.chamadas.length, 0);
  }
});

test("produto indisponivel ou eletrico em posto convencional nao chega a API", async () => {
  for (const alterar of [
    (p) => {
      p.posto.combustiveis.find((i) => i.codigo === "etanol").disponivel =
        false;
    },
    (p) => {
      p.itens = [
        {
          codigo: "recarga_eletrica",
          textoPreco: "2,50",
        },
      ];
    },
  ]) {
    const p = pedido();
    alterar(p);

    const t = preparar();

    await assert.rejects(t.fluxo.enviar(p), tipo("validacao"));

    assert.equal(t.chamadas.length, 0);
  }
});

test("eletroposto conserva preco por kWh", () => {
  const p = pedido();
  p.posto.tipo_posto = "Eletroposto";
  p.itens = [
    {
      codigo: "recarga_eletrica",
      textoPreco: "2,50",
    },
  ];

  const payload = payloadPrecosLote(p, gps());

  assert.equal(payload.itens[0].tipo_combustivel, "Recarga Elétrica (kWh)");
  assert.equal(payload.itens[0].preco, "2.50");
});

test("GPS impreciso impede o envio do lote", async () => {
  const t = preparar({
    obterGps: async () => ({
      ...gps(),
      precisaoM: 151,
    }),
  });

  await assert.rejects(t.fluxo.enviar(pedido()), tipo("gps"));

  assert.equal(t.chamadas.length, 0);
});

test("mudanca de sessao durante o GPS impede o envio", async () => {
  let token = "sessao-de-teste";

  const t = preparar({
    tokenAtual: () => token,
    obterGps: async () => {
      token = "outra";
      return gps();
    },
  });

  await assert.rejects(t.fluxo.enviar(pedido()), tipo("sessao"));

  assert.equal(t.chamadas.length, 0);
});

test("edicao do objeto original durante GPS nao muda o lote capturado", async () => {
  const p = pedido();

  const t = preparar({
    obterGps: async () => {
      p.itens[0].textoPreco = "9.99";
      return gps();
    },
  });

  await t.fluxo.enviar(p);

  assert.equal(t.chamadas[0].payload.itens[0].preco, "6.19");
});

test(
  "dois envios simultaneos pela mesma instancia fazem uma chamada",
  { timeout: 5000 },
  async () => {
    let liberar, avisar;

    const iniciou = new Promise((r) => {
      avisar = r;
    });

    const t = preparar({
      obterGps: () =>
        new Promise((r) => {
          liberar = r;
          avisar();
        }),
    });

    const primeiro = t.fluxo.enviar(pedido());
    await iniciou;

    await assert.rejects(t.fluxo.enviar(pedido()), tipo("rejeitado"));

    liberar(gps());
    await primeiro;

    assert.equal(t.chamadas.length, 1);
  },
);

for (const [status, esperado] of [
  [401, "sessao"],
  [429, "rejeitado"],
  [408, "incerto"],
  [503, "incerto"],
]) {
  for (const lancar of [false, true]) {
    test(`HTTP ${status} por ${lancar ? "excecao" : "retorno"}: ${esperado}`, async () => {
      let chamadas = 0;

      const t = preparar({
        postar: async () => {
          chamadas++;

          const r = {
            status,
            data: { error: "Mensagem do servidor" },
          };

          if (lancar) throw { response: r };

          return r;
        },
      });

      await assert.rejects(t.fluxo.enviar(pedido()), (e) => {
        assert.equal(e.tipo, esperado);

        if (esperado !== "incerto") {
          assert.equal(e.message, "Mensagem do servidor");
        }

        return true;
      });

      assert.equal(chamadas, 1);
    });
  }
}

test("falha de rede fica incerta e nao repete o lote", async () => {
  let chamadas = 0;

  const t = preparar({
    postar: async () => {
      chamadas++;
      throw new Error("rede");
    },
  });

  await assert.rejects(t.fluxo.enviar(pedido()), tipo("incerto"));

  assert.equal(chamadas, 1);
});

test("confirmacao parcial, preco errado, IDs repetidos ou Karma divergente ficam incertos", async () => {
  for (const alterar of [
    (r) => {
      r.data.registros.pop();
    },
    (r) => {
      r.data.registros[0].preco = "6.29";
    },
    (r) => {
      r.data.registros[1].registo_id = r.data.registros[0].registo_id;
    },
    (r) => {
      r.data.karma_ganho = 15;
    },
    (r) => {
      r.data.posto_id = 12;
    },
  ]) {
    const t = preparar({
      postar: async (p) => {
        const r = resposta(p);
        alterar(r);
        return r;
      },
    });

    await assert.rejects(t.fluxo.enviar(pedido()), tipo("incerto"));
  }
});

test("confirmacao pode chegar em outra ordem mantendo os produtos", async () => {
  const t = preparar({
    postar: async (p) => {
      const r = resposta(p);
      r.data.registros.reverse();
      return r;
    },
  });

  const r = await t.fluxo.enviar(pedido());

  assert.deepEqual(
    Array.from(r.registros, (i) => i.codigo),
    ["etanol", "gasolina_comum"],
  );
});

test("recusa libera a instancia para nova tentativa explicita", async () => {
  let chamadas = 0;

  const t = preparar({
    postar: async (p) =>
      ++chamadas === 1 ? { status: 429, data: {} } : resposta(p),
  });

  await assert.rejects(t.fluxo.enviar(pedido()), tipo("rejeitado"));

  assert.equal((await t.fluxo.enviar(pedido())).registros.length, 2);
});

test("texto preserva unidades de litro e metro cubico", () => {
  const r = lerTextoPrecos("Gasolina comum: R$ 6,19 / L; GNV: 4,89 / m³", [
    "gasolina_comum",
    "gnv",
  ]);

  assert.deepEqual(normal(r), [
    {
      codigo: "gasolina_comum",
      textoPreco: "6.19",
      fotoUrl: null,
    },
    {
      codigo: "gnv",
      textoPreco: "4.89",
      fotoUrl: null,
    },
  ]);
});

test("texto nao ignora trechos, nao troca variantes e nao escolhe preco duplicado", () => {
  for (const texto of [
    "Etanol: 4,29; algo errado",
    "Diesel S10: 6,19",
    "Etanol: 4,29; Etanol: 4,39",
    "GNV: 4,89 / L",
  ]) {
    assert.throws(
      () => lerTextoPrecos(texto, ["etanol", "diesel", "gnv"]),
      tipo("validacao"),
    );
  }
});

test("preencher vazios preserva edicoes e liga a foto somente ao produto sugerido", () => {
  const atual = [
    {
      codigo: "gasolina_comum",
      textoPreco: "6,29",
      selecionado: true,
      fotoUrl: null,
    },
    {
      codigo: "etanol",
      textoPreco: "",
      selecionado: false,
      fotoUrl: null,
    },
  ];

  const foto = "https://www.dropbox.com/s/teste/totem.jpg";

  const sugestoes = [
    {
      codigo: "gasolina_comum",
      textoPreco: "6.19",
      fotoUrl: foto,
    },
    {
      codigo: "etanol",
      textoPreco: "4.29",
      fotoUrl: foto,
    },
  ];

  const r = mesclarSugestoes(atual, sugestoes);

  assert.equal(r[0].textoPreco, "6,29");
  assert.equal(r[0].fotoUrl, null);
  assert.equal(r[1].selecionado, true);
  assert.equal(r[1].fotoUrl, foto);
  assert.equal(atual[1].textoPreco, "");

  assert.equal(mesclarSugestoes(atual, sugestoes, true)[0].textoPreco, "6.19");
});
