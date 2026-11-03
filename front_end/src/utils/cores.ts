export const calcularCorDoPosto = (
  precoAtual: number,
  menorPrecoDaLista: number,
  maiorPrecoDaLista: number,
  dataRegistroUtc?: string | null,
): string => {
  // 1. Sem dados
  if (!precoAtual || precoAtual === 0) return "#D1D5DB"; // Cinza claro

  // 2. Validade do Dado (Mais de 3 dias = Desatualizado)
  if (dataRegistroUtc) {
    const dataRegistro = new Date(dataRegistroUtc);
    const hoje = new Date();
    const diasPassados =
      (hoje.getTime() - dataRegistro.getTime()) / (1000 * 3600 * 24);

    if (diasPassados > 3) return "#9CA3AF"; // Cinza Escuro (Atenção)
  }

  // 3. Sem concorrência (Único posto ou todos iguais)
  if (menorPrecoDaLista === maiorPrecoDaLista) return "#10B981"; // Verde

  // 4. Algoritmo dos Terços Competitivos
  const diferencaTotal = maiorPrecoDaLista - menorPrecoDaLista;
  const limiteVerde = menorPrecoDaLista + diferencaTotal * 0.33;
  const limiteAmarelo = menorPrecoDaLista + diferencaTotal * 0.66;

  if (precoAtual <= limiteVerde) return "#10B981"; // VERDE (Top 33% mais baratos)
  if (precoAtual <= limiteAmarelo) return "#FACC15"; // AMARELO (Preço Médio)

  return "#EF4444"; // VERMELHO (Caro demais)
};
