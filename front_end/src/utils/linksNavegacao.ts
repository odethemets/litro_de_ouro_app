export type AplicativoNavegacao = "google_maps" | "waze" | "sistema";

export type SistemaNavegacao = "android" | "ios" | "web";

export interface DestinoNavegacao {
  latitude: unknown;
  longitude: unknown;
}

export interface DadosNavegador {
  userAgent?: string;
  platform?: string;
  maxTouchPoints?: number;
}

interface OpcaoNavegacao {
  id: AplicativoNavegacao;
  label: string;
}

export function identificarSistemaNavegacao(
  plataforma: string,
  navegador: DadosNavegador = {},
): SistemaNavegacao {
  if (plataforma === "android" || plataforma === "ios") {
    return plataforma;
  }

  const agente = navegador.userAgent ?? "";

  if (/Android/i.test(agente)) {
    return "android";
  }

  const ipadComAgenteDesktop =
    navegador.platform === "MacIntel" && (navegador.maxTouchPoints ?? 0) > 1;

  if (/iPhone|iPad|iPod/i.test(agente) || ipadComAgenteDesktop) {
    return "ios";
  }

  return "web";
}

export function opcoesNavegacao(sistema: SistemaNavegacao): OpcaoNavegacao[] {
  const opcoes: OpcaoNavegacao[] = [
    { id: "google_maps", label: "Google Maps" },
    { id: "waze", label: "Waze" },
  ];

  if (sistema === "android") {
    opcoes.push({
      id: "sistema",
      label: "Aplicativo de mapas do aparelho",
    });
  }

  if (sistema === "ios") {
    opcoes.push({
      id: "sistema",
      label: "Apple Maps",
    });
  }

  return opcoes;
}

function coordenada(valor: unknown, limite: number): number {
  const decimal = /^[-+]?(?:\d+(?:\.\d*)?|\.\d+)$/;

  const numero =
    typeof valor === "number"
      ? valor
      : typeof valor === "string" && decimal.test(valor.trim())
        ? Number(valor.trim())
        : NaN;

  if (!Number.isFinite(numero) || Math.abs(numero) > limite) {
    throw new Error("As coordenadas deste posto estão indisponíveis.");
  }

  return numero;
}

// A posição de origem fica a cargo do aplicativo de navegação.
export function montarLinksNavegacao(
  aplicativo: AplicativoNavegacao,
  destino: DestinoNavegacao,
  sistema: SistemaNavegacao,
  nativo = false,
): string[] {
  const latitude = coordenada(destino.latitude, 90);
  const longitude = coordenada(destino.longitude, 180);

  const ponto = `${latitude},${longitude}`;
  const codificado = encodeURIComponent(ponto);

  if (aplicativo === "google_maps") {
    const web =
      "https://www.google.com/maps/dir/?api=1" +
      `&destination=${codificado}&travelmode=driving`;

    if (nativo && sistema === "android") {
      return [`google.navigation:q=${codificado}&mode=d`, web];
    }

    if (nativo && sistema === "ios") {
      return [
        `comgooglemaps://?daddr=${codificado}&directionsmode=driving`,
        web,
      ];
    }

    return [web];
  }

  if (aplicativo === "waze") {
    const web =
      `https://waze.com/ul?ll=${codificado}` +
      "&navigate=yes&utm_source=litro_de_ouro";

    return nativo ? [`waze://?ll=${codificado}&navigate=yes`, web] : [web];
  }

  if (aplicativo === "sistema") {
    if (sistema === "android") {
      return [`geo:${ponto}?q=${codificado}`];
    }

    if (sistema === "ios") {
      const web = `https://maps.apple.com/?daddr=${codificado}&dirflg=d`;

      return nativo ? [`maps://?daddr=${codificado}&dirflg=d`, web] : [web];
    }

    throw new Error("O mapa do sistema não está disponível nesta tela.");
  }

  throw new Error("Aplicativo de navegação inválido.");
}
