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
import { PRECISAO_MAPA_MAX_M } from "../../utils/precisaoGps";

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
  precisaoMaxM: PRECISAO_MAPA_MAX_M,
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
  .pino { box-sizing:border-box; border-radius:24px; padding:3px; box-shadow:0 2px 8px #0003; display:flex; align-items:center; justify-content:center; }
  .pino-interior { box-sizing:border-box; width:100%; height:100%; border-radius:22px; background:#fff; color:#171923; display:flex; align-items:center; justify-content:center; gap:4px; font:700 13px -apple-system,"Segoe UI",sans-serif; white-space:nowrap; }
  .pino-selecionado { box-shadow:0 0 0 3px #FFC400,0 3px 10px #0004; }
  .grupo { box-sizing:border-box; width:52px; height:52px; border:3px solid #fff; border-radius:50%; background:#252B35; color:#fff; display:flex; flex-direction:column; align-items:center; justify-content:center; box-shadow:0 2px 8px #0004; font:700 16px -apple-system,"Segoe UI",sans-serif; }
  .grupo small { font-size:9px; font-weight:400; }
  .leaflet-control-attribution { font-size: 10px; }
  .leaflet-control-zoom a { width:48px; height:48px; line-height:48px; }
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
    if (window.ReactNativeWebView) {
      window.ReactNativeWebView.postMessage(s);
    } else if (window.parent && window.parent !== window) {
      window.parent.postMessage(s, '*');
    }
  }

  window.onerror = function (m) {
    enviar({ tipo: 'erro', motivo: String(m).slice(0, 200) });
  };

  if (typeof L === 'undefined') {
    enviar({ tipo: 'erro', motivo: 'leaflet_indisponivel' });
    return;
  }

  // Number(null) === 0: impede coordenadas inválidas convertidas em zero.
  function num(v) {
    return (typeof v === 'number' && isFinite(v)) ? v : NaN;
  }

  var COR_PADRAO = '#9CA3AF';
  var RE_COR = /^#[0-9a-fA-F]{6}$/;

  function corValida(c) {
    return (typeof c === 'string' && RE_COR.test(c)) ? c : COR_PADRAO;
  }

  function corDoTexto(c) {
    var r = parseInt(c.slice(1, 3), 16);
    var g = parseInt(c.slice(3, 5), 16);
    var b = parseInt(c.slice(5, 7), 16);
    return (0.299 * r + 0.587 * g + 0.114 * b) > 160
      ? '#1b1b1b'
      : '#ffffff';
  }

  var mapa = L.map('mapa', {
    zoomControl: false,
    attributionControl: false
  }).setView([CFG.centro[0], CFG.centro[1]], CFG.zoom);

  L.control.attribution({ prefix: false }).addTo(mapa);
  L.control.zoom({ position: 'bottomright' }).addTo(mapa);

  L.tileLayer(CFG.tileUrl, {
    maxZoom: 19,
    attribution: CFG.atribuicao
  }).addTo(mapa);

  /* ---------- postos ---------- */

  var marcadores = {};
  var postosRecebidos = [];

  function criarIcone(p, mostrarRotulo) {
    var el = document.createElement('div');
    var cores = Array.isArray(p.segmentos)
      ? p.segmentos.filter(function(c) { return RE_COR.test(c); })
      : [];

    el.className = 'pino' + (p.selecionado ? ' pino-selecionado' : '');

    var tamanho = mostrarRotulo ? [118, 48] : [48, 48];
    el.style.width = tamanho[0] + 'px';
    el.style.height = tamanho[1] + 'px';

    el.style.background = cores.length
      ? 'conic-gradient(' + cores.map(function(c, i) {
          return c + ' ' + (i * 360 / cores.length) + 'deg '
            + ((i + 1) * 360 / cores.length) + 'deg';
        }).join(',') + ')'
      : '#929AA5';

    var dentro = document.createElement('div');
    dentro.className = 'pino-interior';
    dentro.style.color = corValida(p.cor);
    dentro.textContent = mostrarRotulo
      ? (p.eletrico ? '⚡ ' : '') + p.rotulo
      : (p.eletrico ? '⚡' : '•');

    el.appendChild(dentro);

    return L.divIcon({
      className: 'pino-wrap',
      html: el,
      iconSize: tamanho,
      iconAnchor: [tamanho[0] / 2, tamanho[1] / 2]
    });
  }

  function iconeGrupo(n) {
    var el = document.createElement('div');
    el.className = 'grupo';
    el.textContent = String(n);

    var pequeno = document.createElement('small');
    pequeno.textContent = 'postos';
    el.appendChild(pequeno);

    return L.divIcon({
      className: 'pino-wrap',
      html: el,
      iconSize: [52, 52],
      iconAnchor: [26, 26]
    });
  }

  function renderizarPostos() {
    var zoom = mapa.getZoom();
    var grupos = {};
    var individuais = [];
    var exibidos = {};
    var etiquetas = [];

    postosRecebidos.forEach(function(p) {
      if (p.selecionado || zoom >= 17) {
        individuais.push(p);
        return;
      }

      var ponto = mapa.project([p.lat, p.lon], zoom);
      var chave = Math.floor(ponto.x / 100) + '.'
        + Math.floor(ponto.y / 72);

      (grupos[chave] || (grupos[chave] = [])).push(p);
    });

    function atualizar(
      chave, lat, lon, assinatura, icone, titulo, aoClicar, selecionado
    ) {
      exibidos[chave] = true;
      var atual = marcadores[chave];

      if (atual && atual.sig === assinatura) return;

      if (atual) mapa.removeLayer(atual.marker);

      var m = L.marker([lat, lon], {
        icon: icone,
        keyboard: true,
        title: titulo,
        alt: titulo,
        zIndexOffset: selecionado ? 1000 : 0
      });

      m.on('click', aoClicar).addTo(mapa);
      marcadores[chave] = { marker: m, sig: assinatura };
    }

    Object.keys(grupos).forEach(function(chave) {
      var itens = grupos[chave];

      if (itens.length === 1) {
        individuais.push(itens[0]);
        return;
      }

      var lat = 0;
      var lon = 0;

      itens.forEach(function(p) {
        lat += p.lat;
        lon += p.lon;
      });

      lat /= itens.length;
      lon /= itens.length;

      atualizar(
        'grupo.' + chave,
        lat,
        lon,
        JSON.stringify(itens),
        iconeGrupo(itens.length),
        itens.length + ' postos; aproximar mapa',
        function() {
          mapa.fitBounds(
            itens.map(function(p) { return [p.lat, p.lon]; }),
            {
              padding: [40, 40],
              maxZoom: Math.min(17, zoom + 2)
            }
          );
        }
      );
    });

    individuais.sort(function(a, b) {
      return Number(!!b.selecionado) - Number(!!a.selecionado)
        || a.id - b.id;
    });

    individuais.forEach(function(p) {
      var ponto = mapa.project([p.lat, p.lon], zoom);

      var mostrar = !!p.rotulo && (
        !!p.selecionado || !etiquetas.some(function(q) {
          return Math.abs(ponto.x - q.x) < 126
            && Math.abs(ponto.y - q.y) < 56;
        })
      );

      if (mostrar) etiquetas.push(ponto);

      atualizar(
        'posto.' + p.id,
        p.lat,
        p.lon,
        JSON.stringify(p) + '|' + mostrar,
        criarIcone(p, mostrar),
        (p.nome || 'Posto') + (p.rotulo ? ': ' + p.rotulo : ''),
        function() {
          enviar({ tipo: 'posto_selecionado', id: p.id });
        },
        p.selecionado
      );
    });

    Object.keys(marcadores).forEach(function(id) {
      if (!exibidos[id]) {
        mapa.removeLayer(marcadores[id].marker);
        delete marcadores[id];
      }
    });
  }

  function definirPostos(lista) {
    if (!Array.isArray(lista)) return;

    postosRecebidos = lista.filter(function(p) {
      return p
        && Number.isSafeInteger(p.id)
        && p.id > 0
        && isFinite(num(p.lat))
        && Math.abs(p.lat) <= 90
        && isFinite(num(p.lon))
        && Math.abs(p.lon) <= 180;
    }).map(function(p) {
      return {
        id: p.id,
        lat: p.lat,
        lon: p.lon,
        cor: corValida(p.cor),
        rotulo: typeof p.rotulo === 'string' ? p.rotulo.slice(0, 24) : '',
        segmentos: Array.isArray(p.segmentos)
          ? p.segmentos.filter(function(c) {
              return typeof c === 'string' && RE_COR.test(c);
            })
          : [],
        eletrico: p.eletrico === true,
        selecionado: p.selecionado === true,
        nome: typeof p.nome === 'string' ? p.nome.slice(0, 180) : ''
      };
    });

    renderizarPostos();
  }

  mapa.on('zoomend', renderizarPostos);

  /* ---------- posição do utilizador ---------- */

  var ptUsuario = null;
  var circUsuario = null;

  function definirUsuario(u) {
    if (!u) {
      if (ptUsuario) {
        mapa.removeLayer(ptUsuario);
        mapa.removeLayer(circUsuario);
        ptUsuario = circUsuario = null;
      }
      return;
    }

    var lat = num(u.lat);
    var lon = num(u.lon);
    if (!isFinite(lat) || !isFinite(lon)) return;

    var prec = num(u.precisaoM);
    if (!isFinite(prec) || prec < 0) prec = 0;
    prec = Math.min(prec, CFG.precisaoMaxM);

    if (!ptUsuario) {
      circUsuario = L.circle([lat, lon], {
        radius: prec,
        color: '#1a73e8',
        weight: 1,
        fillOpacity: 0.12,
        interactive: false
      }).addTo(mapa);

      ptUsuario = L.circleMarker([lat, lon], {
        radius: 8,
        color: '#fff',
        weight: 3,
        fillColor: '#1a73e8',
        fillOpacity: 1,
        interactive: false
      }).addTo(mapa);
    } else {
      ptUsuario.setLatLng([lat, lon]);
      circUsuario.setLatLng([lat, lon]);
      circUsuario.setRadius(prec);
    }
  }

  function centralizar(c) {
    var lat = num(c.lat);
    var lon = num(c.lon);
    if (!isFinite(lat) || !isFinite(lon)) return;

    var zoom = num(c.zoom);
    mapa.setView(
      [lat, lon],
      isFinite(zoom) ? zoom : mapa.getZoom(),
      { animate: true }
    );
  }

  /* ---------- entrada de comandos ---------- */

  function receber(bruto) {
    var msg;
    try {
      msg = typeof bruto === 'string' ? JSON.parse(bruto) : bruto;
    } catch (e) {
      return;
    }

    if (!msg || typeof msg.tipo !== 'string') return;

    if (msg.tipo === 'postos') definirPostos(msg.postos);
    else if (msg.tipo === 'usuario') definirUsuario(msg.usuario);
    else if (msg.tipo === 'centralizar') centralizar(msg);
  }

  window.__litro = { receber: receber };

  window.addEventListener('message', function(e) {
    if (window.parent !== window && e.source === window.parent) {
      receber(e.data);
    }
  });

  /* ---------- saída de eventos ---------- */

  var tRegiao = null;

  mapa.on('moveend', function() {
    clearTimeout(tRegiao);
    tRegiao = setTimeout(function() {
      var c = mapa.getCenter();
      var b = mapa.getBounds();

      enviar({
        tipo: 'regiao',
        lat: c.lat,
        lon: c.lng,
        zoom: mapa.getZoom(),
        bbox: [
          b.getSouth(),
          b.getWest(),
          b.getNorth(),
          b.getEast()
        ]
      });
    }, 600);
  });

  // O zoom do Leaflet usa href="#": deixe esses controles com o Leaflet.
  // Consulte o atributo original; el.href resolve "#" para a URL do app.
  document.addEventListener('click', function(e) {
    var el = e.target;

    while (el && el.tagName !== 'A') {
      el = el.parentElement;
    }

    if (!el) return;

    var href = el.getAttribute('href');
    if (typeof href !== 'string') return;

    href = href.trim();

    if (!href || href.charAt(0) === '#') return;

    e.preventDefault();

    if (/^https:\/\//i.test(href)) {
      enviar({ tipo: 'abrir_link', url: href });
    }
  }, true);

  window.addEventListener('resize', function() {
    mapa.invalidateSize();
  });

  enviar({ tipo: 'pronto' });
})();
</script>
</body>
</html>`;
