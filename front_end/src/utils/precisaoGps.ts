export const PRECISAO_REGISTRO_MAX_M = 150;
export const PRECISAO_MAPA_DETALHADA_M = 500;
export const PRECISAO_MAPA_MAX_M = 10000;

type Leitura = { precisaoM?: number | null } | null | undefined;

export function localizacaoAproximada(local: Leitura): boolean {
  const precisao = local?.precisaoM;

  return (
    typeof precisao === "number" &&
    Number.isFinite(precisao) &&
    precisao > PRECISAO_MAPA_DETALHADA_M
  );
}

export function avisoPrecisaoMapa(local: Leitura): string {
  if (!localizacaoAproximada(local) || typeof local?.precisaoM !== "number")
    return "";

  const km = (local.precisaoM / 1000).toFixed(1).replace(".", ",");

  return `Localização aproximada: incerteza estimada de ±${km} km. Distâncias pessoais não são exibidas.`;
}

export function zoomLocalizacao(local: Leitura): number {
  return localizacaoAproximada(local) ? 11 : 14;
}

export function posicaoParaProximidade<T extends { precisaoM?: number | null }>(
  local: T | null,
): T | null {
  return localizacaoAproximada(local) ? null : local;
}

export function prepararPostosParaLocalizacao<
  T extends { distancia_m?: number },
>(postos: T[], local: Leitura): T[] {
  if (!localizacaoAproximada(local)) return postos;

  return postos.map((posto) => {
    const copia = { ...posto };
    delete copia.distancia_m;
    return copia;
  });
}
