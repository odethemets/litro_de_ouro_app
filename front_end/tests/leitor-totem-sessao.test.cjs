const { test } = require("node:test");
const assert = require("node:assert/strict");
const { ambiente, montar, todos, botao, clicar, pendente, turno, foto } = require("./apoio-leitor-totem.cjs");

test("leitor isola foto por conta/posto e não aparece para visitante", () => {
  const e = ambiente(), inicial = e.leitor.LeitorTotem(e.props).key;
  assert.notEqual(e.leitor.LeitorTotem({ ...e.props, postoId: 11 }).key, inicial);
  e.auth.token = "outra-sessao"; assert.notEqual(e.leitor.LeitorTotem(e.props).key, inicial);
  e.auth.status = "GUEST"; e.auth.token = null;
  assert.equal(e.leitor.LeitorTotem(e.props), null);
});

test("seleção não envia; arquivo é preparado antes do GPS e comprovante começa desativado", async () => {
  const e = ambiente(), d = montar(e.leitor.ConteudoLeitor, e.props);
  await clicar(d, "Escolher foto do totem");
  assert.equal(e.chamadas.length, 0); assert.equal(e.ordem.length, 0);
  await clicar(d, "Ler preços da foto");
  assert.equal(e.ordem.join(","), "arquivo,gps,api");
  assert.equal(e.chamadas[0][1].get("guardar_comprovante"), "false");
  assert.equal(e.usados.length, 0);
  await clicar(d, "Usar Etanol: R$ 4,39 / L");
  assert.equal(e.usados[0][0], "etanol"); assert.equal(e.usados[0][1], "4.39");
  assert.equal(e.chamadas[0][0], "/ia/ler-totem"); assert.equal(e.chamadas.length, 1);
});

test("última seleção web vence sem bloquear se um cancelamento não resolveu", async () => {
  const e = ambiente(), a = pendente(), b = pendente();
  let numero = 0; e.pickImpl = () => (++numero === 1 ? a.promise : b.promise);
  const d = montar(e.leitor.ConteudoLeitor, e.props);
  await clicar(d, "Escolher foto do totem"); await clicar(d, "Escolher foto do totem");
  b.resolve({ canceled: false, assets: [foto("blob:B")] }); await turno(); d.render();
  a.resolve({ canceled: false, assets: [foto("blob:A")] }); await turno(); d.render();
  assert.equal(todos(d.arvore, "Image")[0].props.source.uri, "blob:B");
});

test("nova seleção invalida leitura anterior ainda em andamento", async () => {
  const e = ambiente(), leitura = pendente(), picker = pendente();
  const d = montar(e.leitor.ConteudoLeitor, e.props);
  await clicar(d, "Escolher foto do totem");
  e.pickImpl = () => picker.promise;
  await clicar(d, "Escolher outra foto");
  e.postImpl = () => leitura.promise;
  await clicar(d, "Ler preços da foto");
  picker.resolve({ canceled: false, assets: [foto("blob:nova")] }); await turno(); d.render();
  assert.equal(e.chamadas[0][2].signal.aborted, true);
  leitura.resolve({ data: { sucesso: true, precos: { Etanol: 4.39 } } }); await turno(); d.render();
  assert.equal(todos(d.arvore, "Image")[0].props.source.uri, "blob:nova");
  assert.equal(todos(d.arvore, "AppButton").some((b) => b.props.label.startsWith("Usar ")), false);
});

test("sair durante GPS impede POST e atualizações após desmontagem", async () => {
  const e = ambiente(), espera = pendente(); e.gpsImpl = () => espera.promise;
  const d = montar(e.leitor.ConteudoLeitor, e.props);
  await clicar(d, "Escolher foto do totem"); await clicar(d, "Ler preços da foto"); d.sair();
  espera.resolve({ latitude: -7.11, longitude: -34.86, precisaoM: 10, obtidaEm: Date.now(), simulada: false });
  await turno(); assert.equal(e.chamadas.length, 0); assert.equal(d.atualizacoesAposSaida, 0);
});

test("cancelar leitura ignora retorno tardio sem preencher cadastro", async () => {
  const e = ambiente(), espera = pendente(); e.postImpl = () => espera.promise;
  const d = montar(e.leitor.ConteudoLeitor, e.props);
  await clicar(d, "Escolher foto do totem"); await clicar(d, "Ler preços da foto");
  await clicar(d, "Cancelar leitura");
  espera.resolve({ data: { sucesso: true, precos: { Etanol: 4.39 } } }); await turno(); d.render();
  assert.equal(e.chamadas[0][2].signal.aborted, true); assert.equal(e.usados.length, 0);
  assert.equal(todos(d.arvore, "AppButton").some((b) => b.props.label.startsWith("Usar ")), false);
});

test("cadastro em andamento aborta leitura e impede reaproveitar resposta", async () => {
  const e = ambiente(), espera = pendente(); e.postImpl = () => espera.promise;
  const d = montar(e.leitor.ConteudoLeitor, e.props);
  await clicar(d, "Escolher foto do totem"); await clicar(d, "Ler preços da foto");
  d.render({ bloqueado: true });
  assert.equal(e.chamadas[0][2].signal.aborted, true);
  espera.resolve({ data: { sucesso: true, precos: { Etanol: 4.39 } } }); await turno(); d.render();
  assert.equal(e.usados.length, 0);
});

test("produto não permitido não é levado ao formulário", async () => {
  const e = ambiente(), d = montar(e.leitor.ConteudoLeitor, { ...e.props, permitidos: ["diesel"] });
  await clicar(d, "Escolher foto do totem"); await clicar(d, "Ler preços da foto");
  const usar = botao(d, "Usar Etanol: R$ 4,39 / L"); assert.equal(usar.props.disabled, true);
  usar.props.onPress(); assert.equal(e.usados.length, 0);
});

test("comprovante só é anexado com opção ativa e confirmação Dropbox", async () => {
  const e = ambiente();
  e.postImpl = async () => ({ data: { sucesso: true, precos: { Etanol: 4.39 }, foto_url: "https://www.dropbox.com/s/prova.jpg?raw=1" } });
  const d = montar(e.leitor.ConteudoLeitor, e.props);
  await clicar(d, "Escolher foto do totem"); await clicar(d, "Salvar comprovante: desativado");
  await clicar(d, "Ler preços da foto");
  assert.equal(e.chamadas[0][1].get("guardar_comprovante"), "true");
  await clicar(d, "Usar Etanol: R$ 4,39 / L");
  assert.equal(e.usados[0][2], "https://www.dropbox.com/s/prova.jpg?raw=1");
});
