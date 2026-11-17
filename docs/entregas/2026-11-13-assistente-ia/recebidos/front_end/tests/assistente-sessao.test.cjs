const { test } = require("node:test");
const assert = require("node:assert/strict");
const { ambiente, montar, todos, botao, buscar, pendente, turno } = require("./apoio-assistente.cjs");

test("assistente separa rascunho e resultado por sessão", () => {
  const e = ambiente(), primeira = e.tela.default().key;
  e.auth.token = "sessao-sintetica-b";
  assert.notEqual(e.tela.default().key, primeira);
  e.auth.status = "GUEST"; e.auth.token = null;
  const pagina = montar(e.tela.default);
  botao(pagina, "Entrar para usar o assistente");
  assert.equal(e.chamadas.length, 0);
});

test("busca não aplica filtros ou navega antes da confirmação", async () => {
  const e = ambiente(), d = montar(e.tela.ConteudoAssistente, { token: e.auth.token });
  await buscar(d);
  assert.equal(e.aplicacoes.length, 0); assert.equal(e.navegacoes.length, 0);
  assert.equal(e.chamadas[0][2].headers.Authorization, "Bearer sessao-sintetica-a");
  botao(d, "Aplicar esta busca no mapa").props.onPress();
  assert.equal(e.aplicacoes[0].referencia, "etanol");
  assert.equal(e.aplicacoes[0].combustiveis.join(","), "etanol");
  assert.equal(e.navegacoes[0], "Mapa");
});

test("cancelar ignora retorno tardio e permite outra busca", async () => {
  const e = ambiente(), espera = pendente(); e.postImpl = () => espera.promise;
  const d = montar(e.tela.ConteudoAssistente, { token: e.auth.token });
  await buscar(d);
  botao(d, "Cancelar busca").props.onPress(); d.render();
  assert.equal(e.chamadas[0][2].signal.aborted, true);
  e.postImpl = async () => ({ data: e.resposta() });
  await buscar(d, "etanol");
  espera.resolve({ data: { ...e.resposta(), mensagem: "RESULTADO ANTIGO" } });
  await turno(); d.render();
  assert.equal(JSON.stringify(d.arvore).includes("RESULTADO ANTIGO"), false);
  assert.equal(e.chamadas.length, 2);
});

test("duplo clique inicia uma única busca", async () => {
  const e = ambiente(), espera = pendente(); e.postImpl = () => espera.promise;
  const d = montar(e.tela.ConteudoAssistente, { token: e.auth.token });
  await buscar(d);
  botao(d, "Buscar postos").props.onPress(); await turno();
  assert.equal(e.chamadas.length, 1);
  d.sair(); espera.resolve({ data: e.resposta() }); await turno();
  assert.equal(d.atualizacoesAposSaida, 0);
});

test("desfocar aborta pedido e não deixa a tela ocupada ao voltar", async () => {
  const e = ambiente(), espera = pendente(); e.postImpl = () => espera.promise;
  const d = montar(e.tela.ConteudoAssistente, { token: e.auth.token });
  await buscar(d); e.desfocar();
  assert.equal(e.chamadas[0][2].signal.aborted, true);
  espera.resolve({ data: e.resposta() }); await turno();
  e.refocar(); d.render();
  assert.equal(botao(d, "Buscar postos").props.busy, false);
});

test("mudança dos filtros ou GPS impede aplicar uma prévia anterior", async () => {
  for (const alteracao of [
    (e) => { e.contexto.filtros = { ...e.contexto.filtros, marca: "Ipiranga" }; },
    (e) => { e.contexto.usuario = { lat: -7.12, lon: -34.87 }; },
  ]) {
    const e = ambiente(), d = montar(e.tela.ConteudoAssistente, { token: e.auth.token });
    await buscar(d); alteracao(e); d.render();
    const aplicar = botao(d, "Aplicar esta busca no mapa");
    assert.equal(aplicar.props.disabled, true);
    aplicar.props.onPress(); assert.equal(e.aplicacoes.length, 0);
  }
});

test("fala preenche texto sem consultar nem aplicar automaticamente", () => {
  const e = ambiente(); e.vozAtiva = true;
  const d = montar(e.tela.ConteudoAssistente, { token: e.auth.token });
  botao(d, "Falar busca").props.onPress(); e.transcrever("diesel e etanol"); e.fimVoz(); d.render();
  assert.equal(todos(d.arvore, (n) => n.type === "AppField")[0].props.value, "diesel e etanol");
  assert.equal(e.chamadas.length, 0); assert.equal(e.aplicacoes.length, 0);
});

test("sair durante escuta ignora transcrição tardia", () => {
  const e = ambiente(); e.vozAtiva = true;
  const d = montar(e.tela.ConteudoAssistente, { token: e.auth.token });
  botao(d, "Falar busca").props.onPress(); d.sair();
  e.transcrever("resposta antiga");
  assert.equal(e.abortouVoz, true); assert.equal(d.atualizacoesAposSaida, 0);
});

test("serviço recusa mensagem inválida, GPS fictício e sessão vazia antes do POST", async () => {
  const e = ambiente(), signal = new AbortController().signal;
  for (const mensagem of ["", "x".repeat(501)]) {
    await assert.rejects(e.servico.consultarAssistente(mensagem, e.contexto.filtros, null, signal));
  }
  await assert.rejects(e.servico.consultarAssistente("etanol", e.contexto.filtros, { lat: 0, lon: 0 }, signal));
  await assert.rejects(e.servico.consultarAssistente("etanol", e.contexto.filtros, null, signal, ""));
  assert.equal(e.chamadas.length, 0);
});

test("busca já cancelada não envia e filtros são copiados", async () => {
  const e = ambiente(), controller = new AbortController(); controller.abort();
  await assert.rejects(e.servico.consultarAssistente("etanol", e.contexto.filtros, null, controller.signal));
  assert.equal(e.chamadas.length, 0);
  const filtros = e.servico.validarFiltrosBusca(e.contexto.filtros);
  filtros.combustiveis.push("etanol");
  assert.equal(e.contexto.filtros.combustiveis.length, 0);
});
