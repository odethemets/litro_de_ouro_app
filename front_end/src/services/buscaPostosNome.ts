export function normalizarBuscaNome(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-BR")
    .trim()
    .replace(/\s+/g, " ");
}

export function filtrarPostosPorNome<T extends { nome: string }>(
  postos: T[],
  busca: string,
): T[] {
  const termo = normalizarBuscaNome(busca);

  if (!termo) return postos;

  const palavras = termo.split(" ");

  return postos.filter((posto) => {
    const nome = normalizarBuscaNome(posto.nome);
    return palavras.every((palavra) => nome.includes(palavra));
  });
}

export function postoMaisProximo<T extends { distancia_m?: number }>(
  postos: T[],
): T | null {
  let proximo: T | null = null;

  for (const posto of postos) {
    const distancia = posto.distancia_m;

    if (
      distancia === undefined ||
      !Number.isFinite(distancia) ||
      distancia < 0
    ) {
      continue;
    }

    if (proximo === null || distancia < proximo.distancia_m!) {
      proximo = posto;
    }
  }

  return proximo;
}