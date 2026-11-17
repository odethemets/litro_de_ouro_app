import { isAxiosError } from "axios";
import { api } from "./API";
import { COMBUSTIVEIS, type Combustivel } from "./catalogoPostos";
import {
  favoritosValidos,
  type AvisoPreco,
  type CentralAvisos,
  type FavoritosConta,
} from "./participacao";
export const INTERVALOS_ALERTAS = [0, 15, 30, 60, 120, 1440] as const;
export interface PreferenciasAlertas {
  combustiveis: Combustivel[];
  ativo: boolean;
  somente_quedas: boolean;
  intervalo_minutos: number;
}

function objeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === "object" && valor !== null && !Array.isArray(valor);
}

function idValido(valor: unknown): valor is number {
  return typeof valor === "number" && Number.isSafeInteger(valor) && valor > 0;
}

function precoValido(valor: unknown): valor is number {
  return typeof valor === "number" && Number.isFinite(valor) && valor > 0;
}

function avisoValido(valor: unknown): valor is AvisoPreco {
  return (
    objeto(valor) &&
    idValido(valor.id) &&
    idValido(valor.posto_id) &&
    typeof valor.posto_nome === "string" &&
    Boolean(valor.posto_nome.trim()) &&
    COMBUSTIVEIS.some((c) => c.codigo === valor.combustivel_codigo) &&
    (valor.preco_anterior === null || precoValido(valor.preco_anterior)) &&
    precoValido(valor.preco_novo) &&
    typeof valor.criado_em === "string" &&
    Number.isFinite(Date.parse(valor.criado_em)) &&
    typeof valor.lida === "boolean"
  );
}

export function validarCentralAvisos(valor: unknown): CentralAvisos {
  if (
    !objeto(valor) ||
    !Array.isArray(valor.itens) ||
    valor.itens.length > 100 ||
    !valor.itens.every(avisoValido) ||
    typeof valor.nao_lidas !== "number" ||
    !Number.isSafeInteger(valor.nao_lidas) ||
    valor.nao_lidas < 0 ||
    new Set(valor.itens.map((item) => item.id)).size !== valor.itens.length
  ) {
    throw new Error("A API não retornou notificações válidas.");
  }

  return { itens: valor.itens, nao_lidas: valor.nao_lidas };
}

export async function carregarAvisos(signal: AbortSignal) {
  return validarCentralAvisos(
    (await api.get("/notificacoes", { signal })).data,
  );
}

export async function carregarPreferencias(signal: AbortSignal) {
  return favoritosValidos(
    (
      await api.get("/favoritos", {
        signal,
        params: { verificacao: Date.now() },
      })
    ).data,
  );
}

export async function salvarPreferencias(
  preferencias: PreferenciasAlertas,
  signal: AbortSignal,
): Promise<FavoritosConta> {
  favoritosValidos(
    (await api.put("/favoritos/preferencias", preferencias, { signal })).data,
  );

  const confirmado = await carregarPreferencias(signal);

  const confere =
    confirmado.alertas.ativo === preferencias.ativo &&
    confirmado.alertas.somente_quedas === preferencias.somente_quedas &&
    confirmado.alertas.intervalo_minutos === preferencias.intervalo_minutos &&
    confirmado.combustiveis.length === preferencias.combustiveis.length &&
    preferencias.combustiveis.every((codigo) =>
      confirmado.combustiveis.includes(codigo),
    );

  if (!confere) {
    throw new Error(
      "A consulta da API retornou preferências diferentes das enviadas. Recarregue para conferir.",
    );
  }

  return confirmado;
}

export function mensagemErroPreferencias(erro: unknown): string {
  if (isAxiosError<{ error?: unknown }>(erro)) {
    if (!erro.response) {
      return (
        "A API não respondeu. A alteração pode ter sido gravada. " +
        "Confira a conexão e recarregue as preferências."
      );
    }

    const detalhe =
      typeof erro.response.data?.error === "string"
        ? erro.response.data.error
        : "A API não confirmou a operação.";

    return (
      "HTTP " +
      erro.response.status +
      ": " +
      detalhe +
      " Recarregue as preferências antes de repetir."
    );
  }

  return erro instanceof Error
    ? erro.message
    : "Não foi possível confirmar as preferências.";
}
