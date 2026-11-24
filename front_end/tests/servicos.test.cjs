/* global __dirname */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

function item(extra = {}) {
  return {
    id: 10,
    posto_id: 1,
    posto_nome: "Posto sintético",
    posto_endereco: "Endereço de teste",
    codigo: "recarga_eletrica",
    observacao: "Carregador no posto",
    estado: "pendente",
    motivo: null,
    criado_em: "2026-11-23T10:00:00Z",
    revisado_em: null,
    distancia_m: 5,
    precisao_m: 10,
    pode_revisar: false,
    ...extra,
  };
}

function ambiente() {
  const e = {
    chamadas: [],
  };

  e.get = async () => ({
    data: {
      itens: [],
      antes_de: null,
    },
  });

  e.post = async () => ({
    status: 201,
    data: item(),
  });

  class Formulario {
    constructor() {
      this.itens = new Map();
    }

    append(nome, valor) {
      this.itens.set(nome, valor);
    }
  }

  const cache = new Map();

  function carregar(nome) {
    const arquivo = path.resolve(__dirname, "../src/services", nome + ".ts");

    if (cache.has(arquivo)) {
      return cache.get(arquivo);
    }

    const js = ts.transpileModule(fs.readFileSync(arquivo, "utf8"), {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
      },
    }).outputText;

    const modulo = {
      exports: {},
    };

    vm.runInNewContext("(function(require,module,exports){" + js + "\n})", {
      Date,
      Error,
      Set,
      Map,
      Number,
      FormData: Formulario,
      URL,
    })(
      (id) => {
        if (id === "./API") {
          return {
            api: {
              get: (...args) => {
                e.chamadas.push(["GET", ...args]);
                return e.get(...args);
              },

              post: (...args) => {
                e.chamadas.push(["POST", ...args]);
                return e.post(...args);
              },
            },
          };
        }

        return carregar(id.replace("./", ""));
      },
      modulo,
      modulo.exports,
    );

    cache.set(arquivo, modulo.exports);

    return modulo.exports;
  }

  e.s = carregar("solicitacoesServicos");
  e.catalogo = carregar("cadastroPreco");

  return e;
}

function pendente() {
  let resolve;

  const promise = new Promise((r) => {
    resolve = r;
  });

  return {
    promise,
    resolve,
  };
}

function preparar(extras = {}) {
  const e = ambiente();
  let token = "sessao-sintetica";

  const gps = {
    latitude: -7.11,
    longitude: -34.86,
    precisaoM: 10,
    simulada: false,
    obtidaEm: Date.now(),
  };

  const chamadas = [];
  const ordem = [];

  const deps = {
    tokenAtual: () => token,

    prepararFoto: async () => {
      ordem.push("foto");
      return null;
    },

    obterGps: async () => {
      ordem.push("gps");
      return gps;
    },

    postar: async (...args) => {
      chamadas.push(args);

      return {
        status: 201,
        data: item(),
      };
    },

    ...extras,
  };

  const pedido = {
    postoId: 1,
    codigo: "recarga_eletrica",

    foto: {
      uri: "file:///foto.jpg",
      type: "image",
      mimeType: "image/jpeg",
      width: 100,
      height: 100,
      fileSize: 500,
    },

    observacao: "Carregador no posto",
    consentimento: true,
    presencaObservada: true,
    chave: "a".repeat(32),
    token,
    signal: new AbortController().signal,
  };

  return {
    ...e,
    fluxo: e.s.criarEnvioSolicitacao(deps),
    pedido,
    chamadas,
    ordem,
    gps,

    trocar: (v) => {
      token = v;
    },
  };
}

test("envia evidência e GPS uma vez; a resposta permanece pendente", async () => {
  const t = preparar();
  const r = await t.fluxo.enviar(t.pedido);

  assert.equal(r.estado, "pendente");
  assert.equal(t.chamadas.length, 1);

  assert.deepEqual(t.ordem, ["foto", "gps"]);

  const form = t.chamadas[0][1].itens;

  assert.equal(form.get("codigo"), "recarga_eletrica");

  assert.equal(form.get("consentimento"), "true");

  assert.equal(form.get("chave_cliente"), t.pedido.chave);

  assert.equal(form.has("preco"), false);
  assert.equal(form.has("karma"), false);
});

test("sem consentimento, presença ou serviço válido não consulta GPS/API", async () => {
  for (const mudar of [
    { consentimento: false },
    { presencaObservada: false },
    { codigo: "glp" },
    { chave: "inválida" },
    { postoId: -1 },
  ]) {
    const t = preparar();

    await assert.rejects(
      t.fluxo.enviar({
        ...t.pedido,
        ...mudar,
      }),
    );

    assert.equal(t.chamadas.length, 0);
    assert.equal(t.ordem.length, 0);
  }
});

test("GPS simulado, antigo ou impreciso impede envio", async () => {
  for (const mudar of [
    { simulada: true },
    { obtidaEm: Date.now() - 16000 },
    { precisaoM: 151 },
  ]) {
    const t = preparar();

    Object.assign(t.gps, mudar);

    await assert.rejects(t.fluxo.enviar(t.pedido));

    assert.equal(t.chamadas.length, 0);
  }
});

test("mudança de sessão durante GPS impede upload", async () => {
  const espera = pendente();

  const t = preparar({
    obterGps: () => espera.promise,
  });

  const p = t.fluxo.enviar(t.pedido);

  await Promise.resolve();
  await Promise.resolve();

  t.trocar("outra-sessao");
  espera.resolve(t.gps);

  await assert.rejects(p, /sessão|tela/);

  assert.equal(t.chamadas.length, 0);
});

test("cancelar durante preparo impede pedir GPS e fazer upload", async () => {
  const espera = pendente();

  const t = preparar({
    prepararFoto: () => espera.promise,
  });

  const c = new AbortController();

  const p = t.fluxo.enviar({
    ...t.pedido,
    signal: c.signal,
  });

  c.abort();
  espera.resolve(null);

  await assert.rejects(p);

  assert.equal(t.chamadas.length, 0);
  assert.equal(t.ordem.length, 0);
});

test("mudança do objeto original não troca posto, produto ou foto durante GPS", async () => {
  const espera = pendente();

  const t = preparar({
    obterGps: () => espera.promise,
  });

  const p = t.fluxo.enviar(t.pedido);

  await Promise.resolve();
  await Promise.resolve();

  t.pedido.codigo = "gnv";
  t.pedido.postoId = 2;
  t.pedido.foto.uri = "file:///outra.jpg";

  espera.resolve(t.gps);
  await p;

  assert.equal(t.chamadas[0][0], 1);

  const f = t.chamadas[0][1].itens;

  assert.equal(f.get("codigo"), "recarga_eletrica");

  assert.equal(f.get("foto").uri, "file:///foto.jpg");
});

test("duplo envio na mesma instância só faz uma chamada", async () => {
  const espera = pendente();

  const t = preparar({
    obterGps: () => espera.promise,
  });

  const p = t.fluxo.enviar(t.pedido);

  await assert.rejects(t.fluxo.enviar(t.pedido), /andamento/);

  espera.resolve(t.gps);
  await p;

  assert.equal(t.chamadas.length, 1);
});

for (const [status, incerta] of [
  [400, false],
  [401, false],
  [403, false],
  [409, false],
  [429, false],
  [408, true],
  [500, true],
  [503, true],
]) {
  test(`HTTP ${status} mantém resultado incerto=${incerta} sem repetir`, async () => {
    let chamadas = 0;

    const t = preparar({
      postar: async () => {
        chamadas++;

        throw {
          response: {
            status,
            data: {
              error: "Recusa sintética",
            },
          },
        };
      },
    });

    await assert.rejects(
      t.fluxo.enviar(t.pedido),
      (e) => e.incerta === incerta,
    );

    assert.equal(chamadas, 1);
  });
}

test("falha de storage explicitamente sem registro libera correção posterior", () => {
  const s = ambiente().s;

  assert.equal(
    s.falhaSolicitacao(
      {
        response: {
          status: 503,
          data: {
            codigo: "FOTO_NAO_GUARDADA",
          },
        },
      },
      true,
    ).incerta,
    false,
  );
});

test("retorno sem confirmação válida ou de outro serviço é incerto", async () => {
  for (const data of [{}, item({ posto_id: 2 }), item({ codigo: "gnv" })]) {
    const t = preparar({
      postar: async () => ({
        status: 201,
        data,
      }),
    });

    await assert.rejects(t.fluxo.enviar(t.pedido), (e) => e.incerta);
  }
});

test("transporte pode devolver 409 sem lançar e continua sendo recusa", async () => {
  const t = preparar({
    postar: async () => ({
      status: 409,
      data: {
        error: "Pendente",
      },
    }),
  });

  await assert.rejects(t.fluxo.enviar(t.pedido), (e) => !e.incerta);
});

test("contrato rejeita IDs, status, datas e estados de revisão inconsistentes", () => {
  const { s } = ambiente();

  for (const mudar of [
    { id: -1 },
    { id: "10" },
    { estado: "liberada" },
    { codigo: "glp" },
    { criado_em: "ontem" },
    { revisado_em: "2026-11-23T11:00:00Z" },
    { estado: "aprovada" },
    {
      estado: ["aprovada"],
      revisado_em: "2026-11-23T11:00:00Z",
    },
    {
      estado: "rejeitada",
      motivo: "",
      revisado_em: "2026-11-23T11:00:00Z",
    },
    { distancia_m: NaN },
  ]) {
    assert.throws(() => s.lerSolicitacao(item(mudar)));
  }
});

test("contrato não propaga foto privada, identidade ou campos de autorização", () => {
  const { s } = ambiente();

  const r = s.lerSolicitacao(
    item({
      foto_arquivo: "arquivo-privado",
      usuario_id: 99,
      admin: true,
    }),
  );

  assert.equal(r.foto_arquivo, undefined);
  assert.equal(r.usuario_id, undefined);
  assert.equal(r.admin, undefined);

  assert.throws(() =>
    s.lerAcessoServicos({
      pode_moderar: "true",
    }),
  );

  assert.equal(
    s.lerAcessoServicos({
      pode_moderar: false,
    }),
    false,
  );
});

test("pagina rejeita duplicações, inversões e cursor que não corresponde ao último item", () => {
  const { s } = ambiente();

  assert.throws(() =>
    s.lerPaginaServicos({
      itens: [item(), item()],
      antes_de: null,
    }),
  );

  assert.throws(() =>
    s.lerPaginaServicos({
      itens: [item({ id: 9 }), item({ id: 10 })],
      antes_de: null,
    }),
  );

  assert.throws(() =>
    s.lerPaginaServicos({
      itens: [item()],
      antes_de: 10,
    }),
  );

  const itens = Array.from({ length: 20 }, (_, i) => item({ id: 30 - i }));

  assert.equal(
    s.lerPaginaServicos({
      itens,
      antes_de: 11,
    }).antes_de,
    11,
  );
});

test("foto da revisão aceita somente JPEG inline limitado", () => {
  const { s } = ambiente();

  assert.match(
    s.lerFotoServico({
      mime: "image/jpeg",
      base64: "/9j/2Q==",
    }),
    /^data:image\/jpeg;base64,/,
  );

  for (const v of [
    {
      mime: "image/svg+xml",
      base64: "abcd",
    },
    {
      mime: "image/jpeg",
      base64: "https://externo/foto.jpg",
    },
    {
      mime: "image/jpeg",
      base64: "/9j/" + "a".repeat(2800000),
    },
  ]) {
    assert.throws(() => s.lerFotoServico(v));
  }
});

test("resposta de consulta cancelada ou de outro filtro não é publicada", async () => {
  const t = ambiente();
  const c = new AbortController();

  t.get = async () => {
    c.abort();

    return {
      data: {
        itens: [item()],
        antes_de: null,
      },
    };
  };

  await assert.rejects(
    t.s.consultarSolicitacoes("sessao", c.signal, false, "todos"),
    /cancelada/,
  );

  t.get = async () => ({
    data: {
      itens: [item()],
      antes_de: null,
    },
  });

  await assert.rejects(
    t.s.consultarSolicitacoes(
      "sessao",
      new AbortController().signal,
      false,
      "aprovada",
    ),
  );
});

test("revisão não envia aprovação sem foto conferida nem rejeição sem motivo", async () => {
  const t = ambiente();
  const i = item({ pode_revisar: true });
  const signal = new AbortController().signal;

  await assert.rejects(
    t.s.decidirServico(i, "aprovar", "", false, "sessao", signal),
  );

  await assert.rejects(
    t.s.decidirServico(i, "rejeitar", "", true, "sessao", signal),
  );

  await assert.rejects(
    t.s.decidirServico(item(), "aprovar", "", true, "sessao", signal),
  );

  assert.equal(t.chamadas.length, 0);
});

test("confirmação administrativa precisa pertencer ao pedido e decisão exatos", async () => {
  const t = ambiente();
  const i = item({ pode_revisar: true });

  t.post = async () => ({
    status: 200,
    data: item({
      id: 11,
      estado: "aprovada",
      revisado_em: "2026-11-23T11:00:00Z",
    }),
  });

  await assert.rejects(
    t.s.decidirServico(
      i,
      "aprovar",
      "Conferida",
      true,
      "sessao",
      new AbortController().signal,
    ),
    (e) => e.incerta,
  );
});

test("recarga em posto convencional depende da oferta confirmada e mantém kWh", () => {
  const { catalogo } = ambiente();

  const posto = {
    tipo_posto: "Convencional",
    combustiveis: [
      {
        codigo: "recarga_eletrica",
        disponivel: null,
      },
    ],
  };

  assert.equal(
    catalogo
      .produtosCadastro(posto)
      .some((p) => p.codigo === "recarga_eletrica"),
    false,
  );

  posto.combustiveis[0].disponivel = true;

  const recarga = catalogo
    .produtosCadastro(posto)
    .find((p) => p.codigo === "recarga_eletrica");

  assert.equal(recarga.unidade, "kWh");

  assert.equal(
    catalogo.produtosCadastro(posto).some((p) => p.codigo === "etanol"),
    true,
  );

  posto.combustiveis[0].disponivel = false;

  assert.equal(
    catalogo
      .produtosCadastro(posto)
      .some((p) => p.codigo === "recarga_eletrica"),
    false,
  );
});

test("chaves locais são estáveis como formato, sem serem tratadas como autorização", () => {
  const { s } = ambiente();

  for (let i = 0; i < 10; i++) {
    assert.match(s.novaChaveSolicitacao(), /^[a-f0-9]{32}$/);
  }
});
