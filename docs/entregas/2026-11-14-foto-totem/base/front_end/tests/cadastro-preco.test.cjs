/* global __dirname */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

const cache = new Map();

function carregar(nome) {
  const arquivo = path.resolve(__dirname, "../src/services", nome + ".ts");

  if (cache.has(arquivo)) return cache.get(arquivo);

  const modulo = { exports: {} };

  const js = ts.transpileModule(fs.readFileSync(arquivo, "utf8"), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;

  cache.set(arquivo, modulo.exports);

  vm.runInNewContext("(function(require,module,exports){" + js + "\n})", {
    Date,
    Number,
    Set,
  })((alvo) => carregar(alvo.replace("./", "")), modulo, modulo.exports);

  return modulo.exports;
}

const c = carregar("cadastroPreco");
const catalogo = carregar("catalogoPostos");
const simples = (v) => JSON.parse(JSON.stringify(v));

function posto(tipo = "Convencional") {
  return {
    id: 10,
    nome: "Posto de teste",
    tipo_posto: tipo,
    latitude: -7.11,
    longitude: -34.86,
    combustiveis: catalogo.COMBUSTIVEIS.map((p) => ({
      codigo: p.codigo,
      disponivel: null,
      origem: null,
      preco: null,
      atualizado_em: null,
      autor_nome: null,
    })),
  };
}

function pedido(alteracoes = {}) {
  return {
    posto: posto(),
    combustivel: "gasolina_comum",
    textoPreco: "5,89",
    token: "token-do-teste",
    ...alteracoes,
  };
}

function gps(alteracoes = {}) {
  return {
    latitude: -7.1101,
    longitude: -34.8601,
    precisaoM: 10,
    obtidaEm: Date.now(),
    simulada: false,
    ...alteracoes,
  };
}

function deps(alteracoes = {}) {
  return {
    tokenAtual: () => "token-do-teste",
    obterGps: async () => gps(),
    postar: async () => ({
      status: 201,
      data: {
        registo_id: 123,
        posto_id: 10,
        karma_ganho: 5,
      },
    }),
    ...alteracoes,
  };
}

function erro(tipo) {
  return (e) => e instanceof c.FalhaCadastro && e.tipo === tipo;
}

test("aceita o intervalo e a precisao decimal do backend ate 25", () => {
  for (const [texto, valor] of [
    ["0,01", "0.01"],
    ["5.89", "5.89"],
    ["25", "25.00"],
    [" 12,3 ", "12.30"],
  ]) {
    assert.equal(c.precoCadastro(texto), valor);
  }
});

test("rejeita lixo, milhar, negativos e mais de duas casas", () => {
  for (const texto of [
    "",
    "0",
    "25.01",
    "-1",
    "5,899",
    "5,89abc",
    "1.000,00",
    "R$ 5,89",
    "NaN",
    "Infinity",
    "1e1",
    ".99",
  ]) {
    assert.equal(c.precoCadastro(texto), null);
  }
});

test("posto convencional preserva cinco produtos e exclui recarga", () => {
  assert.deepEqual(simples(c.produtosCadastro(posto()).map((p) => p.codigo)), [
    "gasolina_comum",
    "gasolina_aditivada",
    "etanol",
    "diesel",
    "gnv",
  ]);
});

test("eletroposto usa somente recarga em kWh", () => {
  const p = posto("Eletroposto");

  assert.deepEqual(simples(c.produtosCadastro(p).map((p) => p.codigo)), [
    "recarga_eletrica",
  ]);

  assert.equal(
    c.produtoInicialCadastro(p, "gasolina_comum"),
    "recarga_eletrica",
  );
});

test("disponibilidade negativa nao vira opcao confirmavel", () => {
  const p = posto();
  p.combustiveis[0].disponivel = false;

  assert.ok(!c.produtosCadastro(p).some((p) => p.codigo === "gasolina_comum"));

  assert.throws(
    () => c.payloadCadastro(pedido({ posto: p }), gps()),
    erro("validacao"),
  );
});

test("produto preferido e mantido quando compativel", () => {
  assert.equal(c.produtoInicialCadastro(posto(), "diesel"), "diesel");
});

test("oferta desconhecida pode receber preco sem alterar disponibilidade", () => {
  const p = posto();
  const antes = JSON.stringify(p);

  c.payloadCadastro(pedido({ posto: p, combustivel: "etanol" }), gps());

  assert.equal(JSON.stringify(p), antes);
  assert.equal(p.combustiveis[2].disponivel, null);
});

test("payload de GNV usa nome proprio e coordenadas do aparelho", () => {
  const payload = c.payloadCadastro(pedido({ combustivel: "gnv" }), gps());

  assert.deepEqual(simples(payload), {
    posto_id: 10,
    tipo_combustivel: "GNV",
    preco: "5.89",
    latitude: -7.1101,
    longitude: -34.8601,
    precisao_m: 10,
    simulada: false,
  });

  assert.ok(!("token" in payload));
  assert.ok(!("usuario_id" in payload));
});

test("payload eletrico respeita nome legado esperado pelo backend", () => {
  const p = pedido({
    posto: posto("Eletroposto"),
    combustivel: "recarga_eletrica",
  });

  assert.equal(
    c.payloadCadastro(p, gps()).tipo_combustivel,
    "Recarga Elétrica (kWh)",
  );
});

test("nao usa posicao ausente, invalida ou Null Island", () => {
  for (const g of [
    gps({ latitude: NaN }),
    gps({ longitude: 181 }),
    gps({ latitude: "-7.11" }),
    gps({ latitude: 0, longitude: 0 }),
  ]) {
    assert.throws(() => c.payloadCadastro(pedido(), g), erro("gps"));
  }
});

test("precisao atualizada e GPS nao simulado sao obrigatorios", () => {
  for (const g of [
    gps({ precisaoM: 151 }),
    gps({ precisaoM: null }),
    gps({ precisaoM: -1 }),
    gps({ simulada: true }),
    gps({ obtidaEm: Date.now() - 16000 }),
    gps({ obtidaEm: Date.now() + 6000 }),
  ]) {
    assert.throws(() => c.payloadCadastro(pedido(), g), erro("gps"));
  }
});

test("sucesso depende de 201 com ids e Karma da resposta", () => {
  assert.deepEqual(
    simples(
      c.confirmarCadastro(
        201,
        {
          registo_id: 123,
          posto_id: 10,
          karma_ganho: 7,
        },
        10,
      ),
    ),
    {
      registoId: 123,
      postoId: 10,
      karmaGanho: 7,
    },
  );
});

test("resposta incompleta ou de outro posto e resultado incerto", () => {
  for (const [status, data] of [
    [200, {}],
    [201, {}],
    [
      201,
      {
        registo_id: 1,
        posto_id: 11,
        karma_ganho: 5,
      },
    ],
    [
      201,
      {
        registo_id: true,
        posto_id: 10,
        karma_ganho: 5,
      },
    ],
    [
      201,
      {
        registo_id: 1,
        posto_id: 10,
        karma_ganho: -1,
      },
    ],
  ]) {
    assert.throws(() => c.confirmarCadastro(status, data, 10), erro("incerto"));
  }
});

test("preco invalido e barrado antes do GPS e do POST", async () => {
  let consultas = 0;

  const envio = c.criarEnvioPreco(
    deps({
      obterGps: async () => {
        consultas++;
        return gps();
      },
    }),
  );

  await assert.rejects(
    envio.enviar(pedido({ textoPreco: "25,01" })),
    erro("validacao"),
  );

  assert.equal(consultas, 0);
});

test("GPS negado nao envia e permite nova leitura em outra tentativa", async () => {
  let posts = 0;
  let leituras = 0;

  const envio = c.criarEnvioPreco(
    deps({
      obterGps: async () => {
        if (++leituras === 1) {
          throw new Error("GPS negado");
        }

        return gps();
      },

      postar: async () => {
        posts++;

        return {
          status: 201,
          data: {
            registo_id: 2,
            posto_id: 10,
            karma_ganho: 5,
          },
        };
      },
    }),
  );

  await assert.rejects(envio.enviar(pedido()), erro("gps"));

  assert.equal(posts, 0);

  await envio.enviar(pedido());

  assert.equal(posts, 1);
  assert.equal(leituras, 2);
});

test("sessao encerrada enquanto GPS responde impede POST", async () => {
  let token = "token-do-teste";
  let posts = 0;

  const envio = c.criarEnvioPreco(
    deps({
      tokenAtual: () => token,

      obterGps: async () => {
        token = null;
        return gps();
      },

      postar: async () => {
        posts++;
      },
    }),
  );

  await assert.rejects(envio.enviar(pedido()), erro("sessao"));

  assert.equal(posts, 0);
});

test("duplo envio concorrente dispara um unico POST", async () => {
  let liberar;
  let posts = 0;

  const aguardar = new Promise((resolve) => {
    liberar = resolve;
  });

  const envio = c.criarEnvioPreco(
    deps({
      obterGps: async () => {
        await aguardar;
        return gps();
      },

      postar: async () => {
        posts++;

        return {
          status: 201,
          data: {
            registo_id: 1,
            posto_id: 10,
            karma_ganho: 5,
          },
        };
      },
    }),
  );

  const primeiro = envio.enviar(pedido());

  await assert.rejects(envio.enviar(pedido()), erro("rejeitado"));

  liberar();
  await primeiro;

  assert.equal(posts, 1);
});

test("POST recebe a sessao capturada e corpo validado", async () => {
  let recebido;

  const envio = c.criarEnvioPreco(
    deps({
      postar: async (payload, token) => {
        recebido = { payload, token };

        return {
          status: 201,
          data: {
            registo_id: 1,
            posto_id: 10,
            karma_ganho: 5,
          },
        };
      },
    }),
  );

  await envio.enviar(pedido({ textoPreco: "22,99" }));

  assert.equal(recebido.token, "token-do-teste");
  assert.equal(recebido.payload.preco, "22.99");
});

test("recusas 4xx como distancia, precisao e intervalo sao explicitas", async () => {
  for (const status of [400, 401, 403, 404, 422, 429]) {
    const envio = c.criarEnvioPreco(
      deps({
        postar: async () => {
          throw {
            response: {
              status,
              data: { error: "Recusa verificada" },
            },
          };
        },
      }),
    );

    await assert.rejects(
      envio.enviar(pedido()),
      (e) => erro("rejeitado")(e) && e.message === "Recusa verificada",
    );
  }
});

test("timeout, rede e 5xx sao incertos sem reenvio automatico", async () => {
  for (const falha of [
    {},
    { code: "ECONNABORTED" },
    { response: { status: 500 } },
    { response: { status: 503 } },
  ]) {
    let posts = 0;

    const envio = c.criarEnvioPreco(
      deps({
        postar: async () => {
          posts++;
          throw falha;
        },
      }),
    );

    await assert.rejects(envio.enviar(pedido()), erro("incerto"));

    assert.equal(posts, 1);
  }
});

test("201 malformado nao libera mensagem de sucesso", async () => {
  const envio = c.criarEnvioPreco(
    deps({
      postar: async () => ({
        status: 201,
        data: { message: "ok" },
      }),
    }),
  );

  await assert.rejects(envio.enviar(pedido()), erro("incerto"));
});
