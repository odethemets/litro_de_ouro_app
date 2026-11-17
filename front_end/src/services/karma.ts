import { api } from "./API";
import type { DadosKarma, EventoKarma } from "./participacao";

export interface ParticipanteRanking {
  nome: string;
  karma: number;
}

function objeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === "object" && valor !== null && !Array.isArray(valor);
}

function inteiro(valor: unknown): valor is number {
  return typeof valor === "number" && Number.isSafeInteger(valor);
}

function idValido(valor: unknown): valor is number {
  return inteiro(valor) && valor > 0;
}

function eventoValido(valor: unknown): valor is EventoKarma {
  return (
    objeto(valor) &&
    idValido(valor.id) &&
    typeof valor.motivo === "string" &&
    Boolean(valor.motivo.trim()) &&
    inteiro(valor.pontos) &&
    inteiro(valor.saldo_apos) &&
    (valor.registo_id === null || idValido(valor.registo_id)) &&
    typeof valor.criado_em === "string" &&
    Number.isFinite(Date.parse(valor.criado_em))
  );
}

export function validarKarma(valor: unknown): DadosKarma {
  if (
    !objeto(valor) ||
    !inteiro(valor.saldo) ||
    !Array.isArray(valor.itens) ||
    valor.itens.length > 100 ||
    !valor.itens.every(eventoValido) ||
    new Set(valor.itens.map((item) => item.id)).size !== valor.itens.length
  ) {
    throw new Error("A API não retornou um histórico de Karma válido.");
  }

  return { saldo: valor.saldo, itens: valor.itens };
}

function participanteValido(valor: unknown): valor is ParticipanteRanking {
  return (
    objeto(valor) &&
    typeof valor.nome === "string" &&
    Boolean(valor.nome.trim()) &&
    inteiro(valor.karma)
  );
}

export function validarRanking(valor: unknown): ParticipanteRanking[] {
  if (
    !Array.isArray(valor) ||
    valor.length > 50 ||
    !valor.every(participanteValido)
  ) {
    throw new Error("A API não retornou um ranking válido.");
  }

  for (let indice = 1; indice < valor.length; indice++) {
    if (valor[indice].karma > valor[indice - 1].karma) {
      throw new Error("A API retornou o ranking fora de ordem.");
    }
  }

  return valor;
}

export async function carregarKarma(signal: AbortSignal) {
  return validarKarma((await api.get("/atividade/karma", { signal })).data);
}

export async function carregarRanking(signal: AbortSignal) {
  return validarRanking((await api.get("/ranking", { signal })).data);
}

export function pontosFormatados(pontos: number) {
  return (pontos > 0 ? "+" : "") + pontos.toLocaleString("pt-BR");
}
