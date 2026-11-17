/** Contrato compartilhado pelo mapa nativo, web, bridge e telas. */

export interface PostoNoMapa {
  id: number;
  lat: number;
  lon: number;
  cor: string;
  rotulo?: string;
  segmentos?: readonly string[];
  eletrico?: boolean;
  selecionado?: boolean;
  nome?: string;
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
  | {
      tipo: "centralizar";
      lat: number;
      lon: number;
      zoom?: number;
    };

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
  onRegiaoMudou?: (regiao: RegiaoMapa) => void;
}
