export interface PoliticaPrecos {
  administrativo: boolean;
  exigeGps: boolean;
  karmaPorPreco: number;
}

export const POLITICA_COMUM: PoliticaPrecos = {
  administrativo: false,
  exigeGps: true,
  karmaPorPreco: 5,
};

export function lerPoliticaPrecos(valor: unknown): PoliticaPrecos {
  if (!valor || typeof valor !== "object" || Array.isArray(valor)) {
    throw new Error("Permissão de cadastro não confirmada.");
  }

  const v = valor as Record<string, unknown>;

  if (
    typeof v.administrativo !== "boolean" ||
    v.exige_gps !== !v.administrativo ||
    v.karma_por_preco !== (v.administrativo ? 0 : 5)
  ) {
    throw new Error(
      "Permissão de cadastro inconsistente. Atualize antes de enviar.",
    );
  }

  return {
    administrativo: v.administrativo,
    exigeGps: !v.administrativo,
    karmaPorPreco: v.administrativo ? 0 : 5,
  };
}
