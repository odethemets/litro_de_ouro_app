const test = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

const caminho = path.join(__dirname, "../src/services/cadastroPreco.ts");

const compilado = ts.transpileModule(readFileSync(caminho, "utf8"), {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
  },
});

const modulo = { exports: {} };

vm.runInNewContext(
  compilado.outputText,
  {
    module: modulo,
    exports: modulo.exports,
    require(id) {
      if (id === "./catalogoPostos") {
        return {
          COMBUSTIVEIS: [
            { codigo: "gasolina_comum", nome: "Gasolina Comum" },
            { codigo: "etanol", nome: "Etanol" },
            { codigo: "recarga_eletrica", nome: "Recarga Elétrica" },
          ],
        };
      }

      throw new Error("Dependência inesperada no teste: " + id);
    },
  },
  { filename: caminho },
);

const { criarEnvioPreco } = modulo.exports;

function pedido() {
  return {
    posto: {
      id: 10,
      tipo_posto: "Posto",
      combustiveis: [{ codigo: "gasolina_comum", disponivel: true }],
    },
    combustivel: "gasolina_comum",
    textoPreco: "6,19",
    token: "token-de-teste",
  };
}

function gpsAtual() {
  return {
    latitude: -7.1,
    longitude: -34.8,
    precisaoM: 10,
    obtidaEm: Date.now(),
    simulada: false,
  };
}

function sucesso() {
  return {
    status: 201,
    data: {
      registo_id: 123,
      posto_id: 10,
      karma_ganho: 5,
    },
  };
}

function fluxo(postar, extras = {}) {
  return criarEnvioPreco({
    tokenAtual: () => "token-de-teste",
    obterGps: async () => gpsAtual(),
    postar,
    ...extras,
  });
}

function falhaEsperada(tipo, mensagem) {
  return (erro) => {
    assert.equal(erro.name, "FalhaCadastro");
    assert.equal(erro.tipo, tipo);

    if (mensagem) {
      assert.match(erro.message, mensagem);
    }

    return true;
  };
}

test("confirma HTTP 201 e envia o preço normalizado", async () => {
  let chamadas = 0;

  const envio = fluxo(async (payload, token) => {
    chamadas++;

    assert.equal(payload.posto_id, 10);
    assert.equal(payload.preco, "6.19");
    assert.equal(payload.tipo_combustivel, "Gasolina Comum");
    assert.equal(token, "token-de-teste");

    return sucesso();
  });

  const resultado = await envio.enviar(pedido());

  assert.equal(resultado.registoId, 123);
  assert.equal(resultado.postoId, 10);
  assert.equal(resultado.karmaGanho, 5);
  assert.equal(chamadas, 1);
});

const casosHttp = [
  {
    status: 429,
    tipo: "rejeitado",
    erro: "Aguarde 15 minutos.",
    mensagem: /Aguarde 15 minutos/,
  },
  {
    status: 401,
    tipo: "sessao",
    erro: "Entre novamente.",
    mensagem: /Entre novamente/,
  },
  {
    status: 408,
    tipo: "incerto",
    erro: "Tempo esgotado.",
    mensagem: /Confira sua atividade/,
  },
  {
    status: 503,
    tipo: "incerto",
    erro: "Serviço indisponível.",
    mensagem: /Confira sua atividade/,
  },
];

for (const modo of ["retorno", "excecao"]) {
  for (const caso of casosHttp) {
    test(`HTTP ${caso.status} por ${modo}: ${caso.tipo}`, async () => {
      let chamadas = 0;

      const envio = fluxo(async () => {
        chamadas++;

        const resposta = {
          status: caso.status,
          data: { error: caso.erro },
        };

        if (modo === "excecao") {
          throw { response: resposta };
        }

        return resposta;
      });

      await assert.rejects(
        envio.enviar(pedido()),
        falhaEsperada(caso.tipo, caso.mensagem),
      );

      assert.equal(chamadas, 1);
    });
  }
}

test("demais recusas 4xx preservam a mensagem do servidor", async () => {
  for (const status of [400, 403, 409, 422]) {
    const envio = fluxo(async () => ({
      status,
      data: { error: "Cadastro recusado para este produto." },
    }));

    await assert.rejects(
      envio.enviar(pedido()),
      falhaEsperada("rejeitado", /Cadastro recusado/),
    );
  }
});

test("falha de rede fica incerta e não repete a chamada", async () => {
  let chamadas = 0;

  const envio = fluxo(async () => {
    chamadas++;
    throw new Error("Falha de rede simulada.");
  });

  await assert.rejects(
    envio.enviar(pedido()),
    falhaEsperada("incerto", /Confira sua atividade/),
  );

  assert.equal(chamadas, 1);
});

test("HTTP 201 sem confirmação válida fica incerto", async () => {
  const envio = fluxo(async () => ({
    status: 201,
    data: {
      registo_id: 123,
      posto_id: 999,
      karma_ganho: 5,
    },
  }));

  await assert.rejects(
    envio.enviar(pedido()),
    falhaEsperada("incerto", /confirmação válida/),
  );
});

test("mudança de sessão durante o GPS impede o envio", async () => {
  let token = "token-de-teste";
  let chamadas = 0;

  const envio = fluxo(
    async () => {
      chamadas++;
      return sucesso();
    },
    {
      tokenAtual: () => token,
      obterGps: async () => {
        token = "outra-sessao";
        return gpsAtual();
      },
    },
  );

  await assert.rejects(
    envio.enviar(pedido()),
    falhaEsperada("sessao", /sessão mudou/),
  );

  assert.equal(chamadas, 0);
});

test("dois envios simultâneos pela mesma instância fazem uma chamada", async () => {
  let liberarGps;
  let chamadas = 0;

  const gpsPendente = new Promise((resolve) => {
    liberarGps = resolve;
  });

  const envio = fluxo(
    async () => {
      chamadas++;
      return sucesso();
    },
    { obterGps: () => gpsPendente },
  );

  const primeiro = envio.enviar(pedido());

  try {
    await assert.rejects(
      envio.enviar(pedido()),
      falhaEsperada("rejeitado", /já está em andamento/),
    );
  } finally {
    liberarGps(gpsAtual());
  }

  await primeiro;
  assert.equal(chamadas, 1);
});

test("recusa libera a instância para uma nova tentativa do usuário", async () => {
  let chamadas = 0;

  const envio = fluxo(async () => {
    chamadas++;

    return chamadas === 1
      ? { status: 429, data: { error: "Aguarde o intervalo." } }
      : sucesso();
  });

  await assert.rejects(
    envio.enviar(pedido()),
    falhaEsperada("rejeitado", /Aguarde o intervalo/),
  );

  const resultado = await envio.enviar(pedido());

  assert.equal(resultado.registoId, 123);
  assert.equal(chamadas, 2);
});

test("GPS impreciso impede a chamada ao servidor", async () => {
  let chamadas = 0;

  const envio = fluxo(
    async () => {
      chamadas++;
      return sucesso();
    },
    {
      obterGps: async () => ({
        ...gpsAtual(),
        precisaoM: 5000,
      }),
    },
  );

  await assert.rejects(envio.enviar(pedido()), falhaEsperada("gps"));

  assert.equal(chamadas, 0);
});
