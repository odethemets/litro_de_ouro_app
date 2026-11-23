const test = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

function carregar(arquivo, dependencias = {}, globais = {}) {
  const caminho = path.join(__dirname, "../src/services/", arquivo);

  const { outputText } = ts.transpileModule(readFileSync(caminho, "utf8"), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
  });

  const modulo = { exports: {} };

  vm.runInNewContext(
    outputText,
    {
      module: modulo,
      exports: modulo.exports,
      AbortController,
      ...globais,
      require(id) {
        if (Object.hasOwn(dependencias, id)) {
          return dependencias[id];
        }
        throw Error("Dependência inesperada: " + id);
      },
    },
    { filename: caminho },
  );

  return modulo.exports;
}

const { criarCicloBuscaVoz } = carregar("cicloBuscaVoz.ts");

function preparar(extras = {}) {
  const estados = [],
    textos = [],
    erros = [],
    tempos = [];
  let descartes = 0,
    consultas = 0;

  const gravacao = {
    parar: async () => ({ uri: "audio-teste" }),
    descartar: async () => {
      descartes++;
    },
  };

  const fluxo = criarCicloBuscaVoz({
    capturar: async () => gravacao,
    transcrever: async () => {
      consultas++;
      return "etanol Shell";
    },
    onEstado: (e) => estados.push(e),
    onTexto: (t) => textos.push(t),
    onErro: (e) => erros.push(e),
    agendar: (acao) => {
      tempos.push(acao);
      return () => {};
    },
    ...extras,
  });

  return {
    fluxo,
    gravacao,
    estados,
    textos,
    erros,
    tempos,
    descartes: () => descartes,
    consultas: () => consultas,
  };
}

test("fala concluída entrega texto e libera a gravação", async () => {
  const t = preparar();
  await t.fluxo.iniciar();
  await t.fluxo.parar();

  assert.deepEqual(t.textos, ["etanol Shell"]);
  assert.equal(t.descartes(), 1);
  assert.equal(t.fluxo.emAndamento(), false);
});

test("início duplicado não abre outra gravação", async () => {
  const t = preparar();
  await t.fluxo.iniciar();

  assert.equal(await t.fluxo.iniciar(), false);

  await t.fluxo.cancelar();
  assert.equal(t.descartes(), 1);
  assert.equal(t.consultas(), 0);
});

test("cancelamento durante a permissão descarta o gravador tardio", async () => {
  let liberar;

  const t = preparar({
    capturar: () =>
      new Promise((r) => {
        liberar = r;
      }),
  });

  const inicio = t.fluxo.iniciar();
  await t.fluxo.cancelar();

  liberar(t.gravacao);
  await inicio;

  assert.equal(t.descartes(), 1);
  assert.equal(t.consultas(), 0);
  assert.equal(t.fluxo.emAndamento(), false);
});

test(
  "resposta cancelada não altera uma nova sessão",
  { timeout: 5000 },
  async () => {
    let liberar;
    let avisarInicio;
    let sinalAnterior;
    let chamadas = 0;

    const transcricaoIniciada = new Promise((resolve) => {
      avisarInicio = resolve;
    });

    const t = preparar({
      transcrever: (_audio, signal) => {
        chamadas++;

        if (chamadas > 1) {
          return Promise.resolve("busca atual");
        }

        sinalAnterior = signal;

        return new Promise((resolve) => {
          liberar = resolve;
          avisarInicio();
        });
      },
    });

    try {
      assert.equal(await t.fluxo.iniciar(), true);

      const parada = t.fluxo.parar();

      // Aguarda o início real da transcrição antes de cancelar.
      await transcricaoIniciada;

      assert.equal(typeof liberar, "function");
      assert.equal(sinalAnterior.aborted, false);

      await t.fluxo.cancelar();

      assert.equal(sinalAnterior.aborted, true);
      assert.equal(await t.fluxo.iniciar(), true);

      const quantidadeEstados = t.estados.length;

      liberar("resposta atrasada");

      assert.equal(await parada, false);
      assert.deepEqual(t.textos, []);
      assert.deepEqual(t.erros, []);
      assert.equal(t.estados.length, quantidadeEstados);
      assert.equal(t.estados.at(-1), "ouvindo");
      assert.equal(t.fluxo.emAndamento(), true);

      // Confere também que a nova sessão consegue concluir.
      assert.equal(await t.fluxo.parar(), true);
      assert.deepEqual(t.textos, ["busca atual"]);
      assert.equal(chamadas, 2);
      assert.equal(t.descartes(), 2);
      assert.equal(t.fluxo.emAndamento(), false);
    } finally {
      await t.fluxo.cancelar();
    }
  },
);

test("falha na transcrição libera a gravação", async () => {
  const t = preparar({
    transcrever: async () => {
      throw Error("rede");
    },
  });

  await t.fluxo.iniciar();
  await t.fluxo.parar();

  assert.equal(t.erros.length, 1);
  assert.equal(t.descartes(), 1);
  assert.equal(await t.fluxo.iniciar(), true);

  await t.fluxo.cancelar();
});

test("desmontagem impede callbacks tardios", async () => {
  let liberar;

  const t = preparar({
    capturar: () =>
      new Promise((r) => {
        liberar = r;
      }),
  });

  const inicio = t.fluxo.iniciar();
  await t.fluxo.descartar();

  const quantidade = t.estados.length;
  liberar(t.gravacao);
  await inicio;

  assert.equal(t.estados.length, quantidade);
  assert.equal(t.textos.length, 0);
  assert.equal(t.descartes(), 1);
});

test("temporizador antigo não encerra a escuta atual", async () => {
  const t = preparar();

  await t.fluxo.iniciar();
  const antigo = t.tempos[0];

  await t.fluxo.cancelar();
  await t.fluxo.iniciar();

  antigo();

  assert.equal(t.estados.at(-1), "ouvindo");
  assert.equal(t.consultas(), 0);

  await t.fluxo.cancelar();
});

test("transcrição vazia ou longa não chega ao formulário", async () => {
  for (const texto of ["", "a".repeat(501)]) {
    const t = preparar({
      transcrever: async () => texto,
    });

    await t.fluxo.iniciar();
    await t.fluxo.parar();

    assert.equal(t.textos.length, 0);
    assert.equal(t.erros.length, 1);
    assert.equal(t.descartes(), 1);
  }
});

function prepararHttp(opcoes = {}) {
  const signal = new AbortController().signal;
  const chamadas = [],
    formularios = [];

  class Formulario {
    constructor() {
      this.itens = [];
      formularios.push(this);
    }
    append(...valores) {
      this.itens.push(valores);
    }
  }

  const { transcreverVoz } = carregar(
    "transcricaoVoz.ts",
    {
      "react-native": {
        Platform: { OS: opcoes.os ?? "web" },
      },
      "./API": {
        api: {
          post: async (...args) => {
            chamadas.push(args);
            opcoes.aposResposta?.();

            return {
              data: opcoes.dados ?? {
                texto: "  etanol Shell  ",
              },
            };
          },
        },
      },
    },
    {
      FormData: Formulario,
      fetch: async () => ({
        ok: true,
        blob: async () => {
          opcoes.aposLeitura?.();

          return (
            opcoes.audio ?? {
              type: "audio/webm;codecs=opus",
              size: 500,
            }
          );
        },
      }),
    },
  );

  return {
    transcreverVoz,
    signal,
    chamadas,
    formularios,
  };
}

test("upload web normaliza o formato e valida o texto", async () => {
  const t = prepararHttp();

  const texto = await t.transcreverVoz("blob:teste", "sessao-teste", t.signal);

  assert.equal(texto, "etanol Shell");
  assert.equal(t.chamadas[0][0], "/ia/transcrever");
  assert.equal(t.formularios[0].itens[0][2], "busca.webm");
  assert.equal(t.chamadas[0][2].headers.Authorization, "Bearer sessao-teste");
});

test("upload nativo envia o arquivo M4A", async () => {
  const t = prepararHttp({ os: "android" });

  await t.transcreverVoz("file:///busca.m4a", "sessao-teste", t.signal);

  const arquivo = t.formularios[0].itens[0][1];
  assert.equal(arquivo.type, "audio/mp4");
  assert.equal(arquivo.uri, "file:///busca.m4a");
});

test("áudio vazio, grande ou incompatível não chega à API", async () => {
  for (const audio of [
    { type: "audio/webm", size: 0 },
    { type: "audio/webm", size: 2097153 },
    { type: "text/plain", size: 50 },
  ]) {
    const t = prepararHttp({ audio });

    await assert.rejects(
      t.transcreverVoz("blob:teste", "sessao-teste", t.signal),
      /gravação/,
    );

    assert.equal(t.chamadas.length, 0);
  }
});

test("cancelar durante a leitura impede o upload", async () => {
  const abort = new AbortController();

  const t = prepararHttp({
    aposLeitura: () => abort.abort(),
  });

  await assert.rejects(
    t.transcreverVoz("blob:teste", "sessao-teste", abort.signal),
    /cancelada/,
  );

  assert.equal(t.chamadas.length, 0);
});

test("cancelar durante o pedido impede entregar texto", async () => {
  const abort = new AbortController();

  const t = prepararHttp({
    aposResposta: () => abort.abort(),
  });

  await assert.rejects(
    t.transcreverVoz("blob:teste", "sessao-teste", abort.signal),
    /cancelada/,
  );
});

test("resposta inválida não vira uma busca", async () => {
  const t = prepararHttp({
    dados: { texto: "" },
  });

  await assert.rejects(
    t.transcreverVoz("blob:teste", "sessao-teste", t.signal),
    /transcrição válida/,
  );
});
