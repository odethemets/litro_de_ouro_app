/** Contrato de mensagens entre o app (React Native / Web) e a página Leaflet. */

export interface PostoNoMapa {
  id: number;
  lat: number;
  lon: number;
  /** Cor do pino em hex "#RRGGBB" (ex.: a que calcularCorDoPosto devolve). O mapa só desenha. */
  cor: string;
  /** Texto curto dentro do pino, ex.: "6,29" (máx. 8 caracteres). Sem rótulo, o pino é uma bolinha. */
  rotulo?: string;
}

export interface PosicaoUsuario {
  lat: number;
  lon: number;
  precisaoM?: number | null;
}

export interface RegiaoMapa {
  lat: number;
  lon: number;
  zoom: number;
  /** [sul, oeste, norte, leste] */
  bbox: [number, number, number, number];
}

export type ComandoParaMapa =
  | { tipo: "postos"; postos: PostoNoMapa[] }
  | { tipo: "usuario"; usuario: PosicaoUsuario | null }
  | { tipo: "centralizar"; lat: number; lon: number; zoom?: number };

export type MensagemDoMapa =
  | { tipo: "pronto" }
  | { tipo: "erro"; motivo: string }
  | { tipo: "posto_selecionado"; id: number }
  | ({ tipo: "regiao" } & RegiaoMapa)
  | { tipo: "abrir_link"; url: string };

export type EstadoMapa = "carregando" | "pronto" | "erro";

export interface MapaLeafletHandle {
  centralizar(lat: number, lon: number, zoom?: number): void;
}

export interface MapaLeafletProps {
  postos: PostoNoMapa[];
  usuario?: PosicaoUsuario | null;
  onSelecionarPosto?: (id: number) => void;
  /** Disparada (com debounce) quando o utilizador termina de mover/zoomar OU quando o app chama centralizar(). */
  onRegiaoMudou?: (regiao: RegiaoMapa) => void;
}
