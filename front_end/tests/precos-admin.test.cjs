/* global __dirname */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");
const { ambiente, montar, turno, pendente } = require("./apoio-servicos.cjs");

const cache = new Map();

function carregar(nome) {
  if (cache.has(nome)) return cache.get(nome);

  const arquivo = path.join(__dirname, "../src/services", nome + ".ts");
  const modulo = { exports: {} };
  cache.set(nome, modulo.exports);

  const js = ts.transpileModule(fs.readFileSync(arquivo, "utf8"), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;

  vm.runInNewContext("(function(require,module,exports){" + js + "\n})", {
    Date,
    Error,
    Set,
  })((alvo) => carregar(alvo.replace("./", "")), modulo, modulo.exports);

  return modulo.exports;
}

const c = carregar("cadastroPreco");
const l = carregar("precosLote");
const { lerPoliticaPrecos } = carregar("politicaPrecos");

const admin = {
  administrativo: true,
  exigeGps: false,
  karmaPorPreco: 0,
};
const comum = {
  administrativo: false,
  exigeGps: true,
  karmaPorPreco: 5,
};

const posto = () => ({
  id: 11,
  tipo_posto: "Posto",
  nome: "Posto de teste",
  combustiveis: [
    { codigo: "gasolina_comum", disponivel: true },
    { codigo: "etanol", disponivel: true },
  ],
});

const pedido = () => ({
  posto: posto(),
  combustivel: "gasolina_comum",
  textoPreco: "6,19",
  token: "sessao-teste",
});

const lote = () => ({
  posto: posto(),
  token: "sessao-teste",
  itens: [
    { codigo: "gasolina_comum", textoPreco: "6,19" },
    { codigo: "etanol", textoPreco: "4,29" },
  ],
});

function resposta(payload, administrativo = true, pontos = 0) {
  return {
    status: 201,
    data: payload.itens
      ? {
          posto_id: payload.posto_id,
          administrativo,
          karma_ganho: pontos * payload.itens.length,
          total: payload.itens.length,
          registros: payload.itens.map((i, n) => ({
            tipo_combustivel: i.tipo_combustivel,
            preco: i.preco,
            registo_id: n + 100,
            karma_ganho: pontos,
          })),
        }
      : {
          posto_id: payload.posto_id,
          administrativo,
          karma_ganho: pontos,
          registo_id: 100,
        },
  };
}

const tipo = (t) => (erro) => erro.tipo === t;

const fabricas = [
  ["individual", c.criarEnvioPreco, pedido],
  ["lote", l.criarEnvioPrecosLote, lote],
];

test("permissão só aceita contratos coerentes de usuário comum ou administrador", () => {
  for (const valor of [
    null,
    [],
    {},
    { administrativo: "true" },
    { administrativo: true, exige_gps: true, karma_por_preco: 0 },
    { administrativo: false, exige_gps: false, karma_por_preco: 0 },
    { administrativo: true, exige_gps: false, karma_por_preco: 5 },
  ]) {
    assert.throws(() => lerPoliticaPrecos(valor));
  }

  assert.equal(
    lerPoliticaPrecos({
      administrativo: true,
      exige_gps: false,
      karma_por_preco: 0,
    }).exigeGps,
    false,
  );

  assert.equal(
    lerPoliticaPrecos({
      administrativo: false,
      exige_gps: true,
      karma_por_preco: 5,
    }).karmaPorPreco,
    5,
  );
});

for (const [nome, criar, obterPedido] of fabricas) {
  test(
    nome +
      ": administrador envia sem consultar GPS e sem campos de localização",
    async () => {
      let chamadas = 0;

      const fluxo = criar({
        administrativo: true,
        tokenAtual: () => "sessao-teste",

        obterGps: async () => {
          throw new Error("GPS não autorizado no teste");
        },

        postar: async (payload) => {
          chamadas++;

          for (const campo of [
            "latitude",
            "longitude",
            "precisao_m",
            "simulada",
            "administrativo",
            "karma_ganho",
          ]) {
            assert.equal(Object.hasOwn(payload, campo), false);
          }

          return resposta(payload);
        },
      });

      assert.equal((await fluxo.enviar(obterPedido())).karmaGanho, 0);
      assert.equal(chamadas, 1);
    },
  );

  test(nome + ": preço inválido é bloqueado antes da API", async () => {
    const p = obterPedido();

    if (p.itens) p.itens[0].textoPreco = "6,199";
    else p.textoPreco = "6,199";

    const fluxo = criar({
      administrativo: true,
      tokenAtual: () => "sessao-teste",
      obterGps: async () => {
        throw new Error("GPS indevido");
      },
      postar: async () => {
        assert.fail("Preço inválido não deve ser enviado");
      },
    });

    await assert.rejects(fluxo.enviar(p), tipo("validacao"));
  });

  test(
    nome +
      ": resposta com Karma ou sem confirmação administrativa fica incerta",
    async () => {
      for (const [administrativo, pontos] of [
        [true, 5],
        [false, 0],
      ]) {
        const fluxo = criar({
          administrativo: true,
          tokenAtual: () => "sessao-teste",
          obterGps: async () => {
            throw new Error("GPS indevido");
          },
          postar: async (payload) => resposta(payload, administrativo, pontos),
        });

        await assert.rejects(fluxo.enviar(obterPedido()), tipo("incerto"));
      }
    },
  );

  test(
    nome + ": sessão alterada antes do envio não chama API nem GPS",
    async () => {
      const fluxo = criar({
        administrativo: true,
        tokenAtual: () => "outra-conta",
        obterGps: async () => assert.fail("GPS indevido"),
        postar: async () => assert.fail("Envio indevido"),
      });

      await assert.rejects(fluxo.enviar(obterPedido()), tipo("sessao"));
    },
  );

  test(nome + ": resposta antiga não é entregue à nova sessão", async () => {
    let token = "sessao-teste";

    const fluxo = criar({
      administrativo: true,
      tokenAtual: () => token,
      obterGps: async () => assert.fail("GPS indevido"),

      postar: async (payload) => {
        token = "outra-conta";
        return resposta(payload);
      },
    });

    await assert.rejects(fluxo.enviar(obterPedido()), tipo("sessao"));
  });

  test(nome + ": falha de rede não repete o envio", async () => {
    let chamadas = 0;

    const fluxo = criar({
      administrativo: true,
      tokenAtual: () => "sessao-teste",
      obterGps: async () => assert.fail("GPS indevido"),

      postar: async () => {
        chamadas++;
        throw new Error("rede");
      },
    });

    await assert.rejects(fluxo.enviar(obterPedido()), tipo("incerto"));
    assert.equal(chamadas, 1);
  });
}

function formulario(politica = admin) {
  const e = ambiente();
  let leituras = 0;
  let recargas = 0;

  e.gps = async () => {
    leituras++;
    throw new Error("Permissão de GPS negada");
  };

  e.post = async (_url, payload) => resposta(payload);

  const d = montar(
    (props) =>
      e.cadastro.useCadastroLote(
        posto(),
        "gasolina_comum",
        e.token,
        () => {
          recargas++;
        },
        props.politica,
      ),
    { politica },
  );

  d.render();

  return {
    e,
    d,
    leituras: () => leituras,
    recargas: () => recargas,
  };
}

test("formulário sem permissão confirmada bloqueia revisão, GPS e envio", async () => {
  const { e, d, leituras } = formulario(null);

  assert.equal(d.arvore.bloqueado, true);

  d.arvore.revisar();
  await d.arvore.verificarGps();
  await d.arvore.enviar();
  d.render();

  assert.equal(d.arvore.revisao, null);
  assert.equal(leituras(), 0);
  assert.equal(e.chamadas.length, 0);
});

test("formulário administrativo confirma lote com GPS negado e não concede pontos", async () => {
  const { e, d, leituras, recargas } = formulario();

  d.arvore.alterar("gasolina_comum", { textoPreco: "6,19" });
  d.render();
  d.arvore.revisar();
  d.render();

  await d.arvore.verificarGps();
  await d.arvore.enviar();
  d.render();

  assert.equal(leituras(), 0);
  assert.equal(e.chamadas.length, 1);
  assert.equal(d.arvore.confirmacao.karmaGanho, 0);
  assert.equal(recargas(), 1);
});

test("formulário comum mantém a solicitação de GPS e não envia quando negada", async () => {
  const { e, d, leituras } = formulario(comum);

  d.arvore.alterar("gasolina_comum", { textoPreco: "6,19" });
  d.render();
  d.arvore.revisar();
  d.render();

  await d.arvore.enviar();
  d.render();

  assert.equal(leituras(), 1);
  assert.equal(e.chamadas.length, 0);
  assert.equal(d.arvore.falha.tipo, "gps");
});

test("duplo toque administrativo mantém uma chamada e resultado incerto bloqueia repetição", async () => {
  const { e, d } = formulario();
  const espera = pendente();

  e.post = () => espera.promise;

  d.arvore.alterar("gasolina_comum", { textoPreco: "6,19" });
  d.render();
  d.arvore.revisar();
  d.render();

  const envio = d.arvore.enviar();
  await d.arvore.enviar();
  await turno();

  assert.equal(e.chamadas.length, 1);

  espera.resolve({ status: 503, data: {} });
  await envio;
  d.render();

  assert.equal(d.arvore.incerto, true);

  await d.arvore.enviar();
  assert.equal(e.chamadas.length, 1);
});

test("desmontagem durante envio administrativo impede publicação de resposta tardia", async () => {
  const { e, d } = formulario();
  const espera = pendente();

  e.post = () => espera.promise;

  d.arvore.alterar("gasolina_comum", { textoPreco: "6,19" });
  d.render();
  d.arvore.revisar();
  d.render();

  const envio = d.arvore.enviar();
  await turno();

  const payload = e.chamadas[0][2];

  d.sair();
  e.token = "outra-conta";

  espera.resolve(resposta(payload));
  await envio;

  assert.equal(d.atualizacoesAposSaida, 0);
});

test("leitura de foto administrativa não pede GPS nem cadastra preços", async () => {
  const { clicar, todos } = require("./apoio-servicos.cjs");
  const e = ambiente();

  let leituras = 0;
  const sugestoes = [];

  e.gps = async () => {
    leituras++;
    throw new Error("GPS negado");
  };

  e.post = async (url, dados) => {
    assert.equal(url, "/ia/ler-totem");

    for (const campo of [
      "latitude",
      "longitude",
      "precisao_m",
      "simulada",
      "administrativo",
    ]) {
      assert.equal(dados.has(campo), false);
    }

    return {
      data: {
        sucesso: true,
        precos: { "Gasolina Comum": 6.19 },
        foto_url: null,
      },
    };
  };

  const d = montar(e.leitor.ConteudoLeitor, {
    postoId: 11,
    administrativo: true,
    bloqueado: false,
    limparComprovante() {},
    usar: (...valores) => sugestoes.push(valores),
    token: e.token,
  });

  await clicar(d, "Escolher foto do totem");
  await clicar(d, "Ler preços da foto");

  assert.equal(leituras, 0);
  assert.equal(e.chamadas.length, 1);
  assert.equal(sugestoes.length, 0);

  const botao = todos(d.arvore, "AppButton").find((b) =>
    b.props.label.startsWith("Usar Gasolina Comum:"),
  );

  assert.ok(botao);
  botao.props.onPress();

  assert.deepEqual(sugestoes, [["gasolina_comum", "6.19", null]]);
  assert.equal(e.chamadas.length, 1);
});
