const test = require("node:test");
const assert = require("node:assert/strict");

const {
  ambiente,
  montar,
  todos,
  botao,
  clicar,
  pendente,
  turno,
  foto,
  item,
} = require("./apoio-servicos.cjs");

async function abrirFormulario(e) {
  const d = montar(e.formulario.FormularioServico, {
    postoId: 1,
    codigo: "recarga_eletrica",
    token: e.token,
  });

  await clicar(d, "Sugerir presença por foto");

  return d;
}

async function prepararEnvio(e) {
  const d = await abrirFormulario(e);

  await clicar(d, "Escolher foto do serviço");

  await clicar(d, "Confirme que observou o serviço neste posto");

  await clicar(d, "Autorizar envio e armazenamento da foto para revisão");

  return d;
}

test("a interface só libera envio com foto e as duas confirmações", async () => {
  const e = ambiente();
  const d = await abrirFormulario(e);

  assert.ok(botao(d, "Enviar para revisão").props.disabled);

  await clicar(d, "Escolher foto do serviço");

  assert.ok(botao(d, "Enviar para revisão").props.disabled);

  await clicar(d, "Confirme que observou o serviço neste posto");

  assert.ok(botao(d, "Enviar para revisão").props.disabled);

  await clicar(d, "Autorizar envio e armazenamento da foto para revisão");

  assert.equal(botao(d, "Enviar para revisão").props.disabled, false);
});

test("sucesso exibe pendência sem atualizar oferta ou registrar preço", async () => {
  const e = ambiente();
  const d = await prepararEnvio(e);

  await clicar(d, "Enviar para revisão");

  assert.equal(e.chamadas.filter((c) => c[0] === "POST").length, 1);

  assert.equal(e.recargas, 0);

  assert.ok(
    todos(d.arvore, "Notice").some((n) =>
      String(n.props.children).includes("aguardando revisão"),
    ),
  );

  assert.equal(
    todos(d.arvore, "AppButton").some(
      (b) => b.props.label === "Enviar para revisão",
    ),
    false,
  );
});

test("seleção que termina após desmontagem não publica foto", async () => {
  const e = ambiente();
  const d = await abrirFormulario(e);
  const espera = pendente();

  e.pick = () => espera.promise;

  botao(d, "Escolher foto do serviço").props.onPress();

  d.sair();

  espera.resolve({
    canceled: false,
    assets: [foto()],
  });

  await turno();

  assert.equal(d.atualizacoesAposSaida, 0);

  assert.equal(e.chamadas.length, 0);
});

test("troca de conta durante GPS impede envio e respostas tardias não publicam estado", async () => {
  const e = ambiente();
  const d = await prepararEnvio(e);
  const espera = pendente();

  e.gps = () => espera.promise;

  botao(d, "Enviar para revisão").props.onPress();

  await turno();

  d.sair();
  e.token = "outra-conta";

  espera.resolve({
    latitude: -7.11,
    longitude: -34.86,
    precisaoM: 10,
    obtidaEm: Date.now(),
    simulada: false,
  });

  await turno();

  assert.equal(e.chamadas.length, 0);

  assert.equal(d.atualizacoesAposSaida, 0);
});

test("duplo toque faz um upload e falha incerta bloqueia nova tentativa", async () => {
  const e = ambiente();
  const d = await prepararEnvio(e);
  const espera = pendente();

  e.post = () => espera.promise;

  botao(d, "Enviar para revisão").props.onPress();
  botao(d, "Enviar para revisão").props.onPress();

  await turno();

  assert.equal(e.chamadas.length, 1);

  espera.resolve({
    status: 503,
    data: {},
  });

  await turno();
  d.render();

  assert.ok(botao(d, "Enviar para revisão").props.disabled);

  assert.ok(botao(d, "Conferir minhas solicitações"));
});

test("cancelamento local de envio iniciado não publica a resposta em outra tela", async () => {
  const e = ambiente();
  const d = await prepararEnvio(e);
  const espera = pendente();

  e.post = () => espera.promise;

  botao(d, "Enviar para revisão").props.onPress();

  await turno();
  d.sair();

  espera.resolve({
    status: 201,
    data: item(),
  });

  await turno();

  assert.equal(d.atualizacoesAposSaida, 0);
});

test("painel não aceita lista que termina após desmontagem", async () => {
  const e = ambiente();
  const espera = pendente();

  e.get = () => espera.promise;

  const d = montar(e.painel.ConteudoPainel, {
    admin: true,
    fechar() {},
    token: e.token,
  });

  d.sair();

  espera.resolve({
    data: {
      itens: [item()],
      antes_de: null,
    },
  });

  await turno();

  assert.equal(d.atualizacoesAposSaida, 0);
});

test("administrador precisa carregar e conferir a foto para aprovar", async () => {
  const e = ambiente();

  e.get = async (url) => ({
    data: url.endsWith("/foto")
      ? {
          mime: "image/jpeg",
          base64: "/9j/2Q==",
        }
      : {
          itens: [item()],
          antes_de: null,
        },
  });

  const d = montar(e.painel.ConteudoPainel, {
    admin: true,
    fechar() {},
    token: e.token,
  });

  await turno();
  d.render();

  await clicar(d, "Abrir foto e revisar");

  assert.ok(botao(d, "Aprovar presença do serviço").props.disabled);

  assert.ok(botao(d, "Rejeitar solicitação").props.disabled);

  assert.ok(
    botao(d, "Confirmar que a foto comprova o serviço neste posto").props
      .disabled,
  );

  todos(d.arvore, "Image")[0].props.onLoad();
  d.render();

  await clicar(d, "Confirmar que a foto comprova o serviço neste posto");

  assert.equal(botao(d, "Aprovar presença do serviço").props.disabled, false);

  e.post = async () => ({
    status: 200,
    data: item({
      estado: "aprovada",
      revisado_em: "2026-11-23T11:00:00Z",
      pode_revisar: false,
    }),
  });

  await clicar(d, "Aprovar presença do serviço");

  assert.equal(e.recargas, 1);

  assert.equal(todos(d.arvore, "Image").length, 0);
});

test("a interface não oferece decisão para pedido do próprio administrador", async () => {
  const e = ambiente();

  e.get = async (url) => ({
    data: url.endsWith("/foto")
      ? {
          mime: "image/jpeg",
          base64: "/9j/2Q==",
        }
      : {
          itens: [
            item({
              pode_revisar: false,
            }),
          ],
          antes_de: null,
        },
  });

  const d = montar(e.painel.ConteudoPainel, {
    admin: true,
    fechar() {},
    token: e.token,
  });

  await turno();
  d.render();

  await clicar(d, "Abrir foto e revisar");

  assert.equal(
    todos(d.arvore, "AppButton").some(
      (b) => b.props.label === "Aprovar presença do serviço",
    ),
    false,
  );
});

test("conta visitante recebe apenas o convite de login", () => {
  const e = ambiente();

  e.auth = {
    token: null,
    status: "GUEST",
    openAuth() {},
  };

  const d = montar(e.formulario.SolicitarServico, {
    postoId: 1,
    codigo: "recarga_eletrica",
  });

  assert.ok(botao(d, "Entrar para sugerir serviço por foto"));

  assert.equal(e.chamadas.length, 0);
});

test("aprovação libera recarga em rascunho já aberto sem apagar preços digitados", () => {
  const e = ambiente();

  const posto = {
    id: 1,
    tipo_posto: "Convencional",
    combustiveis: [
      {
        codigo: "recarga_eletrica",
        disponivel: null,
      },
    ],
  };

  const d = montar(
    (props) =>
      e.cadastro.useCadastroLote(
        props.posto,
        "gasolina_comum",
        e.token,
        () => {},
      ),
    { posto },
  );

  d.render();

  d.arvore.alterar("etanol", {
    textoPreco: "4,29",
    selecionado: true,
  });

  d.render();

  assert.equal(
    d.arvore.itens.some((i) => i.codigo === "recarga_eletrica"),
    false,
  );

  d.render({
    posto: {
      ...posto,
      combustiveis: [
        {
          codigo: "recarga_eletrica",
          disponivel: true,
        },
      ],
    },
  });

  d.render();

  assert.equal(
    d.arvore.itens.find((i) => i.codigo === "recarga_eletrica").selecionado,
    false,
  );

  assert.equal(
    d.arvore.itens.find((i) => i.codigo === "etanol").textoPreco,
    "4,29",
  );
});

test("erro de exibição da foto impede a aprovação", async () => {
  const e = ambiente();

  e.get = async (url) => ({
    data: url.endsWith("/foto")
      ? {
          mime: "image/jpeg",
          base64: "/9j/2Q==",
        }
      : {
          itens: [item()],
          antes_de: null,
        },
  });

  const d = montar(e.painel.ConteudoPainel, {
    admin: true,
    fechar() {},
    token: e.token,
  });

  await turno();
  d.render();

  await clicar(d, "Abrir foto e revisar");

  const imagem = todos(d.arvore, "Image")[0];

  imagem.props.onError();
  imagem.props.onLoad();

  d.render();

  assert.ok(
    botao(d, "Confirmar que a foto comprova o serviço neste posto").props
      .disabled,
  );

  assert.ok(botao(d, "Aprovar presença do serviço").props.disabled);
});

test("evento tardio de foto anterior não libera aprovação de outra solicitação", async () => {
  const e = ambiente();

  e.get = async (url) => ({
    data: url.endsWith("/foto")
      ? {
          mime: "image/jpeg",
          base64: "/9j/2Q==",
        }
      : {
          itens: [item(), item({ id: 9 })],
          antes_de: null,
        },
  });

  const d = montar(e.painel.ConteudoPainel, {
    admin: true,
    fechar() {},
    token: e.token,
  });

  await turno();
  d.render();

  await clicar(d, "Abrir foto e revisar");

  const antiga = todos(d.arvore, "Image")[0];

  todos(d.arvore, "AppButton")
    .filter((b) => b.props.label === "Abrir foto e revisar")[1]
    .props.onPress();

  await turno();
  d.render();

  antiga.props.onLoad();
  d.render();

  assert.ok(
    botao(d, "Confirmar que a foto comprova o serviço neste posto").props
      .disabled,
  );

  todos(d.arvore, "Image")[0].props.onLoad();
  d.render();

  assert.equal(
    botao(d, "Confirmar que a foto comprova o serviço neste posto").props
      .disabled,
    false,
  );
});

test("decisão incerta exige conferir a lista antes de abrir nova revisão", async () => {
  const e = ambiente();

  e.get = async (url) => ({
    data: url.endsWith("/foto")
      ? {
          mime: "image/jpeg",
          base64: "/9j/2Q==",
        }
      : {
          itens: [item()],
          antes_de: null,
        },
  });

  const d = montar(e.painel.ConteudoPainel, {
    admin: true,
    fechar() {},
    token: e.token,
  });

  await turno();
  d.render();

  await clicar(d, "Abrir foto e revisar");

  todos(d.arvore, "Image")[0].props.onLoad();
  d.render();

  await clicar(d, "Confirmar que a foto comprova o serviço neste posto");

  e.post = async () => {
    throw {
      response: {
        status: 503,
      },
    };
  };

  await clicar(d, "Aprovar presença do serviço");

  assert.ok(botao(d, "Aprovar presença do serviço").props.disabled);

  assert.ok(botao(d, "Abrir foto e revisar").props.disabled);

  const antes = e.chamadas.length;

  await clicar(d, "Abrir foto e revisar");

  assert.equal(e.chamadas.length, antes);

  e.get = async () => ({
    data: {
      itens: [
        item({
          estado: "aprovada",
          revisado_em: "2026-11-23T11:00:00Z",
          pode_revisar: false,
        }),
      ],
      antes_de: null,
    },
  });

  await clicar(d, "Todas");
  await turno();
  d.render();

  assert.ok(
    todos(d.arvore, "Notice").some((n) =>
      String(n.props.children).includes("aprovada"),
    ),
  );

  assert.equal(
    todos(d.arvore, "AppButton").some(
      (b) => b.props.label === "Aprovar presença do serviço",
    ),
    false,
  );
});

test("picker web cancelado sem resposta pode ser aberto novamente e seleção antiga é ignorada", async () => {
  const e = ambiente();
  e.plataforma = "web";

  const d = await abrirFormulario(e);
  const antiga = pendente();

  e.pick = () => antiga.promise;

  await clicar(d, "Escolher foto do serviço");

  assert.equal(botao(d, "Escolher foto do serviço").props.disabled, false);

  e.pick = async () => ({
    canceled: false,
    assets: [
      {
        ...foto(),
        uri: "blob:nova-foto",
      },
    ],
  });

  await clicar(d, "Escolher foto do serviço");

  antiga.resolve({
    canceled: false,
    assets: [
      {
        ...foto(),
        uri: "blob:foto-antiga",
      },
    ],
  });

  await turno();
  d.render();

  assert.equal(todos(d.arvore, "Image")[0].props.source.uri, "blob:nova-foto");
});

test("duplo toque não abre dois pickers nativos", async () => {
  const e = ambiente();
  const d = await abrirFormulario(e);
  const espera = pendente();

  let chamadas = 0;

  e.pick = () => {
    chamadas++;
    return espera.promise;
  };

  botao(d, "Escolher foto do serviço").props.onPress();

  botao(d, "Escolher foto do serviço").props.onPress();

  assert.equal(chamadas, 1);

  espera.resolve({
    canceled: true,
  });

  await turno();
  d.render();

  assert.equal(botao(d, "Escolher foto do serviço").props.disabled, false);
});
