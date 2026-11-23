const test = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

const caminho = path.join(__dirname, "../src/utils/linksNavegacao.ts");

const compilado = ts.transpileModule(readFileSync(caminho, "utf8"), {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
  },
});

const modulo = { exports: {} };

vm.runInNewContext(
  compilado.outputText,
  { module: modulo, exports: modulo.exports },
  { filename: caminho },
);

const { identificarSistemaNavegacao, montarLinksNavegacao, opcoesNavegacao } =
  modulo.exports;

const destino = { latitude: -7.1, longitude: -34.8 };

test("Google Maps recebe destino e modo de carro, sem origem", () => {
  const [link] = montarLinksNavegacao("google_maps", destino, "web");
  const url = new URL(link);

  assert.equal(url.hostname, "www.google.com");
  assert.equal(url.pathname, "/maps/dir/");
  assert.equal(url.searchParams.get("destination"), "-7.1,-34.8");
  assert.equal(url.searchParams.get("travelmode"), "driving");
  assert.equal(url.searchParams.has("origin"), false);
});

test("Waze recebe coordenadas e pedido de navegação", () => {
  const [link] = montarLinksNavegacao("waze", destino, "web");
  const url = new URL(link);

  assert.equal(url.hostname, "waze.com");
  assert.equal(url.searchParams.get("ll"), "-7.1,-34.8");
  assert.equal(url.searchParams.get("navigate"), "yes");
});

test("mapa do Android recebe o destino no geo e na consulta", () => {
  const links = montarLinksNavegacao("sistema", destino, "android");
  const url = new URL(links[0]);

  assert.equal(links.length, 1);
  assert.ok(links[0].startsWith("geo:-7.1,-34.8?"));
  assert.equal(url.searchParams.get("q"), "-7.1,-34.8");
});

test("Apple Maps usa HTTPS no navegador e alternativa no nativo", () => {
  const web = montarLinksNavegacao("sistema", destino, "ios");
  const nativo = montarLinksNavegacao("sistema", destino, "ios", true);

  assert.equal(web.length, 1);
  assert.equal(new URL(web[0]).hostname, "maps.apple.com");
  assert.equal(new URL(web[0]).searchParams.get("daddr"), "-7.1,-34.8");
  assert.ok(nativo[0].startsWith("maps://"));
  assert.equal(nativo[1], web[0]);
});

test("Google Maps nativo Android tem alternativa HTTPS", () => {
  const links = montarLinksNavegacao("google_maps", destino, "android", true);

  assert.equal(links.length, 2);
  assert.ok(links[0].startsWith("google.navigation:"));
  assert.equal(new URL(links[1]).protocol, "https:");
});

test("Google Maps nativo iOS tem alternativa HTTPS", () => {
  const links = montarLinksNavegacao("google_maps", destino, "ios", true);

  assert.equal(links.length, 2);
  assert.ok(links[0].startsWith("comgooglemaps://"));
  assert.equal(new URL(links[1]).protocol, "https:");
});

test("Waze nativo tem alternativa HTTPS nos dois sistemas", () => {
  for (const sistema of ["android", "ios"]) {
    const links = montarLinksNavegacao("waze", destino, sistema, true);

    assert.equal(links.length, 2);
    assert.ok(links[0].startsWith("waze://"));
    assert.equal(new URL(links[1]).hostname, "waze.com");
  }
});

test("normaliza decimais e aceita os limites geográficos", () => {
  const [link] = montarLinksNavegacao(
    "google_maps",
    { latitude: " -7.100 ", longitude: "-34.800" },
    "web",
  );

  assert.equal(new URL(link).searchParams.get("destination"), "-7.1,-34.8");

  assert.doesNotThrow(() =>
    montarLinksNavegacao(
      "google_maps",
      { latitude: 90, longitude: -180 },
      "web",
    ),
  );
});

test("rejeita coordenadas ausentes, inválidas e fora dos limites", () => {
  const invalidos = [
    null,
    undefined,
    true,
    "",
    " ",
    NaN,
    Infinity,
    "NaN",
    "0x10",
    "1&origin=outro",
  ];

  for (const valor of invalidos) {
    assert.throws(
      () =>
        montarLinksNavegacao("waze", { ...destino, latitude: valor }, "web"),
      /coordenadas/i,
    );
    assert.throws(
      () =>
        montarLinksNavegacao("waze", { ...destino, longitude: valor }, "web"),
      /coordenadas/i,
    );
  }

  for (const latitude of [-90.1, 90.1]) {
    assert.throws(
      () => montarLinksNavegacao("waze", { ...destino, latitude }, "web"),
      /coordenadas/i,
    );
  }

  for (const longitude of [-180.1, 180.1]) {
    assert.throws(
      () => montarLinksNavegacao("waze", { ...destino, longitude }, "web"),
      /coordenadas/i,
    );
  }
});

test("rejeita aplicativo desconhecido e mapa do sistema no desktop", () => {
  assert.throws(
    () => montarLinksNavegacao("desconhecido", destino, "web"),
    /aplicativo/i,
  );
  assert.throws(
    () => montarLinksNavegacao("sistema", destino, "web"),
    /mapa do sistema/i,
  );
});

test("identifica dispositivos nativos e navegadores móveis", () => {
  const casos = [
    ["android", {}, "android"],
    ["ios", {}, "ios"],
    ["web", { userAgent: "Mozilla Android" }, "android"],
    ["web", { userAgent: "Mozilla iPhone" }, "ios"],
    ["web", { userAgent: "Mozilla iPad" }, "ios"],
    ["web", { platform: "MacIntel", maxTouchPoints: 5 }, "ios"],
    ["web", { platform: "MacIntel", maxTouchPoints: 0 }, "web"],
    ["web", { userAgent: "Mozilla Windows NT" }, "web"],
  ];

  for (const [plataforma, navegador, esperado] of casos) {
    assert.equal(identificarSistemaNavegacao(plataforma, navegador), esperado);
  }
});

test("oferece duas opções no desktop e três no celular", () => {
  const ids = (sistema) =>
    Array.from(opcoesNavegacao(sistema), (opcao) => opcao.id);

  assert.deepEqual(ids("web"), ["google_maps", "waze"]);
  assert.deepEqual(ids("android"), ["google_maps", "waze", "sistema"]);
  assert.deepEqual(ids("ios"), ["google_maps", "waze", "sistema"]);

  assert.equal(opcoesNavegacao("ios")[2].label, "Apple Maps");
});
