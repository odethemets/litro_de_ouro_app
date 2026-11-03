/**
 * Página do mapa. É uma CONSTANTE de módulo: construída uma única vez, nunca recriada por
 * render. O WebView recebe sempre o mesmo `source`, portanto não recarrega. Tudo o que muda
 * (postos, posição do utilizador, centro) entra por mensagens e atualiza só os marcadores
 * afetados.
 *
 * Config por variáveis EXPO_PUBLIC_* (embutidas no build):
 *   EXPO_PUBLIC_TILE_URL        template de tiles (padrão: OpenStreetMap, só para desenvolvimento)
 *   EXPO_PUBLIC_TILE_ATTR       HTML de atribuição do provedor de tiles
 *   EXPO_PUBLIC_MAPA_BASE_URL   origem usada pelo WebView (envia Referer aos provedores de tiles)
 */
const TILE_URL =
  process.env.EXPO_PUBLIC_TILE_URL ??
  "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATRIBUICAO =
  process.env.EXPO_PUBLIC_TILE_ATTR ??
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';

export const MAPA_BASE_URL =
  process.env.EXPO_PUBLIC_MAPA_BASE_URL ?? "https://localhost/";

// Escapa "<" para que o JSON embutido no <script> nunca possa fechar a tag.
const CFG = JSON.stringify({
  centro: [-7.115, -34.861],
  zoom: 13,
  tileUrl: TILE_URL,
  atribuicao: ATRIBUICAO,
}).replace(/</g, "\\u003c");

export const MAPA_HTML = String.raw`<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
  html, body, #mapa { height: 100%; margin: 0; padding: 0; background: #e9edf1; }
  body { -webkit-user-select: none; user-select: none; -webkit-touch-callout: none; }
  .pino-wrap { background: transparent; border: 0; }
  .pino { box-sizing: border-box; border: 2px solid #fff; box-shadow: 0 0 4px rgba(0,0,0,.4); }
  .pino-ponto { width: 20px; height: 20px; border-radius: 50%; }
  .pino-rotulo {
    min-width: 36px; height: 26px; padding: 0 8px; border-radius: 13px;
    font: 700 12px/22px -apple-system, "Segoe UI", Roboto, sans-serif;
    text-align: center; white-space: nowrap;
  }
  .leaflet-control-attribution { font-size: 10px; }
</style>
</head>
<body>
<div id="mapa"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
(function () {
  'use strict';
  var CFG = ${CFG};

  function enviar(msg) {
    var s = JSON.stringify(msg);
    if (window.ReactNativeWebView) { window.ReactNativeWebView.postMessage(s); }
    else if (window.parent && window.parent !== window) { window.parent.postMessage(s, '*'); }
  }

  window.onerror = function (m) { enviar({ tipo: 'erro', motivo: String(m).slice(0, 200) }); };

  if (typeof L === 'undefined') { enviar({ tipo: 'erro', motivo: 'leaflet_indisponivel' }); return; }

  // Number(null) === 0: sem esta checagem, um NaN do app (que o JSON converte em null) viraria lat/lon 0.
  function num(v) { return (typeof v === 'number' && isFinite(v)) ? v : NaN; }

  var COR_PADRAO = '#9CA3AF';
  var RE_COR = /^#[0-9a-fA-F]{6}$/;
  function corValida(c) { return (typeof c === 'string' && RE_COR.test(c)) ? c : COR_PADRAO; }
  function corDoTexto(c) {   // preto sobre cores claras (amarelo, cinza claro), branco sobre as escuras
    var r = parseInt(c.slice(1, 3), 16), g = parseInt(c.slice(3, 5), 16), b = parseInt(c.slice(5, 7), 16);
    return (0.299 * r + 0.587 * g + 0.114 * b) > 160 ? '#1b1b1b' : '#ffffff';
  }

  var mapa = L.map('mapa', { zoomControl: false, attributionControl: false })
    .setView([CFG.centro[0], CFG.centro[1]], CFG.zoom);
  L.control.attribution({ prefix: false }).addTo(mapa);
  L.control.zoom({ position: 'bottomright' }).addTo(mapa);
  L.tileLayer(CFG.tileUrl, { maxZoom: 19, attribution: CFG.atribuicao }).addTo(mapa);

  /* ---------- postos: diff por id, só toca no que mudou ---------- */
  var marcadores = {};

  function criarIcone(cor, rotulo) {
    var el = document.createElement('div');
    el.style.background = cor;
    if (rotulo) {
      el.className = 'pino pino-rotulo';
      el.style.color = corDoTexto(cor);
      el.textContent = rotulo;             // textContent: nunca interpreta HTML
      return L.divIcon({ className: 'pino-wrap', html: el, iconSize: [46, 26], iconAnchor: [23, 13] });
    }
    el.className = 'pino pino-ponto';
    return L.divIcon({ className: 'pino-wrap', html: el, iconSize: [24, 24], iconAnchor: [12, 12] });
  }

  function definirPostos(lista) {
    if (!Array.isArray(lista)) return;
    var vistos = {};
    lista.forEach(function (p) {
      if (!p || typeof p.id !== 'number') return;
      var lat = num(p.lat), lon = num(p.lon);
      if (!isFinite(lat) || !isFinite(lon)) return;
      var cor = corValida(p.cor);
      var rotulo = typeof p.rotulo === 'string' ? p.rotulo.slice(0, 8) : '';
      var sig = lat + '|' + lon + '|' + cor + '|' + rotulo;
      vistos[p.id] = true;

      var atual = marcadores[p.id];
      if (atual) {
        if (atual.sig === sig) return;
        atual.marker.setLatLng([lat, lon]);
        atual.marker.setIcon(criarIcone(cor, rotulo));
        atual.sig = sig;
        return;
      }
      var m = L.marker([lat, lon], { icon: criarIcone(cor, rotulo), keyboard: false });
      m.on('click', function () { enviar({ tipo: 'posto_selecionado', id: p.id }); });
      m.addTo(mapa);
      marcadores[p.id] = { marker: m, sig: sig };
    });
    Object.keys(marcadores).forEach(function (id) {
      if (!vistos[id]) { mapa.removeLayer(marcadores[id].marker); delete marcadores[id]; }
    });
  }

  /* ---------- posição do utilizador ---------- */
  var ptUsuario = null, circUsuario = null;

  function definirUsuario(u) {
    if (!u) {
      if (ptUsuario) { mapa.removeLayer(ptUsuario); mapa.removeLayer(circUsuario); ptUsuario = circUsuario = null; }
      return;
    }
    var lat = num(u.lat), lon = num(u.lon);
    if (!isFinite(lat) || !isFinite(lon)) return;
    var prec = num(u.precisaoM);
    if (!isFinite(prec) || prec < 0) prec = 0;
    prec = Math.min(prec, 500);
    if (!ptUsuario) {
      circUsuario = L.circle([lat, lon], { radius: prec, color: '#1a73e8', weight: 1, fillOpacity: 0.12, interactive: false }).addTo(mapa);
      ptUsuario = L.circleMarker([lat, lon], { radius: 8, color: '#fff', weight: 3, fillColor: '#1a73e8', fillOpacity: 1, interactive: false }).addTo(mapa);
    } else {
      ptUsuario.setLatLng([lat, lon]);
      circUsuario.setLatLng([lat, lon]);
      circUsuario.setRadius(prec);
    }
  }

  function centralizar(c) {
    var lat = num(c.lat), lon = num(c.lon);
    if (!isFinite(lat) || !isFinite(lon)) return;
    var zoom = num(c.zoom);
    mapa.setView([lat, lon], isFinite(zoom) ? zoom : mapa.getZoom(), { animate: true });
  }

  /* ---------- entrada de comandos ---------- */
  function receber(bruto) {
    var msg;
    try { msg = typeof bruto === 'string' ? JSON.parse(bruto) : bruto; } catch (e) { return; }
    if (!msg || typeof msg.tipo !== 'string') return;
    if (msg.tipo === 'postos') definirPostos(msg.postos);
    else if (msg.tipo === 'usuario') definirUsuario(msg.usuario);
    else if (msg.tipo === 'centralizar') centralizar(msg);
  }
  window.__litro = { receber: receber };
  window.addEventListener('message', function (e) {
    if (window.parent !== window && e.source === window.parent) receber(e.data);   // modo iframe (web)
  });

  /* ---------- saída de eventos ---------- */
  var tRegiao = null;
  mapa.on('moveend', function () {
    clearTimeout(tRegiao);
    tRegiao = setTimeout(function () {
      var c = mapa.getCenter(), b = mapa.getBounds();
      enviar({ tipo: 'regiao', lat: c.lat, lon: c.lng, zoom: mapa.getZoom(),
               bbox: [b.getSouth(), b.getWest(), b.getNorth(), b.getEast()] });
    }, 600);
  });

  // Links (atribuição) nunca navegam dentro do WebView: seriam o fim do mapa.
  document.addEventListener('click', function (e) {
    var el = e.target;
    while (el && el.tagName !== 'A') el = el.parentElement;
    if (el && el.href) { e.preventDefault(); enviar({ tipo: 'abrir_link', url: el.href }); }
  }, true);

  window.addEventListener('resize', function () { mapa.invalidateSize(); });

  enviar({ tipo: 'pronto' });
})();
</script>
</body>
</html>`;
