import { COMBUSTIVEIS, type Combustivel } from "./catalogoPostos";

export interface FavoritosConta {
  postos: number[];
  combustiveis: Combustivel[];
  alertas: {
    ativo: boolean;
    somente_quedas: boolean;
    intervalo_minutos: number;
  };
}

export interface AvisoPreco {
  id: number;
  posto_id: number;
  posto_nome: string;
  combustivel_codigo: Combustivel;
  preco_anterior: number | null;
  preco_novo: number;
  criado_em: string;
  lida: boolean;
}

export interface CentralAvisos {
  itens: AvisoPreco[];
  nao_lidas: number;
}

export interface EventoKarma {
  id: number;
  motivo: string;
  pontos: number;
  saldo_apos: number;
  registo_id: number | null;
  criado_em: string;
}

export interface DadosKarma {
  saldo: number;
  itens: EventoKarma[];
}

export function favoritosValidos(valor: unknown): FavoritosConta {
  const f = valor as FavoritosConta | null;

  if (
    !f ||
    !Array.isArray(f.postos) ||
    f.postos.some((id) => !Number.isSafeInteger(id) || id <= 0) ||
    !Array.isArray(f.combustiveis) ||
    f.combustiveis.some(
      (codigo) => !COMBUSTIVEIS.some((p) => p.codigo === codigo),
    ) ||
    typeof f.alertas?.ativo !== "boolean" ||
    typeof f.alertas.somente_quedas !== "boolean" ||
    ![0, 15, 30, 60, 120, 1440].includes(f.alertas.intervalo_minutos)
  ) {
    throw new Error("A API não retornou favoritos válidos.");
  }

  return f;
}

export function dataEvento(valor: string) {
  const data = new Date(valor);

  return Number.isFinite(data.getTime())
    ? data.toLocaleString("pt-BR", {
        timeZone: "America/Fortaleza",
      })
    : "Data indisponível";
}
