export type Voto = "positivo" | "negativo";
export interface AvaliacaoPreco {
  registo_id: number;
  confianca_score: number;
  positivos: number;
  negativos: number;
  meu_voto: Voto | null;
  pode_votar: boolean;
}

export function lerAvaliacao(valor: unknown, registoId: number): AvaliacaoPreco {
  const r = valor as AvaliacaoPreco | null;
  if (!r || r.registo_id !== registoId || !Number.isSafeInteger(r.confianca_score) ||
      !Number.isSafeInteger(r.positivos) || r.positivos < 0 ||
      !Number.isSafeInteger(r.negativos) || r.negativos < 0 ||
      ![null, "positivo", "negativo"].includes(r.meu_voto) || typeof r.pode_votar !== "boolean") {
    throw new Error("Resposta de avaliação inválida. Atualize antes de votar novamente.");
  }
  return r;
}
