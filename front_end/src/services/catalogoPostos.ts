export const COMBUSTIVEIS = [
  {
    codigo: "gasolina_comum",
    nome: "Gasolina Comum",
    unidade: "L",
    cor: "#1D4ED8",
  },
  {
    codigo: "gasolina_aditivada",
    nome: "Gasolina Aditivada",
    unidade: "L",
    cor: "#0891B2",
  },
  { codigo: "etanol", nome: "Etanol", unidade: "L", cor: "#7C3AED" },
  { codigo: "diesel", nome: "Diesel", unidade: "L", cor: "#374151" },
  { codigo: "gnv", nome: "GNV", unidade: "m³", cor: "#8B5E3C" },
  {
    codigo: "recarga_eletrica",
    nome: "Recarga Elétrica",
    unidade: "kWh",
    cor: "#C026D3",
  },
] as const;
export type Combustivel = (typeof COMBUSTIVEIS)[number]["codigo"];
export interface FiltrosPostos {
  combustiveis: Combustivel[];
  referencia: Combustivel;
  marca: string;
  ordenar: "distancia" | "preco";
}
export const FILTROS_INICIAIS: FiltrosPostos = {
  combustiveis: [],
  referencia: "gasolina_comum",
  marca: "",
  ordenar: "distancia",
};
export interface OfertaPosto {
  codigo: Combustivel;
  disponivel: boolean | null;
  origem: "manual" | "osm" | null;
  preco: number | null;
  atualizado_em: string | null;
  autor_nome: string | null;
  registo_id?: number | null;
}
export interface PostoCatalogo {
  id: number;
  nome: string;
  endereco: string;
  bairro: string | null;
  latitude: number;
  longitude: number;
  marca: string | null;
  tipo_posto: string;
  distancia_m?: number;
  combustiveis: OfertaPosto[];
  combustivel_referencia: Combustivel;
  preco_referencia: number | null;
}
// Localiza nome, unidade e cor do código conhecido no catálogo fixo de combustíveis.
export const produto = (codigo: Combustivel) =>
  COMBUSTIVEIS.find((p) => p.codigo === codigo)!;
// Formata o valor em reais; a unidade do produto é acrescentada pela interface.
export const precoFormatado = (valor: number) =>
  "R$ " + valor.toFixed(2).replace(".", ",");

// Alterna a seleção e mantém a referência entre os combustíveis selecionados.
export function alternarCombustivel(
  filtros: FiltrosPostos,
  codigo: Combustivel,
): FiltrosPostos {
  const combustiveis = filtros.combustiveis.includes(codigo)
    ? filtros.combustiveis.filter((c) => c !== codigo)
    : [...filtros.combustiveis, codigo];
  const referencia = combustiveis.includes(filtros.referencia)
    ? filtros.referencia
    : (combustiveis[0] ?? filtros.referencia);
  return { ...filtros, combustiveis, referencia };
}
// Monta a consulta da API sem enviar coordenadas fictícias quando não há GPS.
export function parametrosPostos(
  filtros: FiltrosPostos,
  local?: { lat: number; lon: number } | null,
) {
  return {
    ...(local ? { lat: local.lat, lng: local.lon } : {}),
    ...(filtros.combustiveis.length
      ? { combustiveis: filtros.combustiveis.join(",") }
      : {}),
    referencia: filtros.referencia,
    ...(filtros.marca ? { marca: filtros.marca } : {}),
    ordenar: filtros.ordenar,
  };
}
// Define as barrinhas pela interseção dos filtros com as ofertas confirmadas.
export function segmentosPosto(
  posto: PostoCatalogo,
  selecionados: Combustivel[],
) {
  return COMBUSTIVEIS.filter(
    (p) =>
      (!selecionados.length || selecionados.includes(p.codigo)) &&
      posto.combustiveis.some(
        (o) => o.codigo === p.codigo && o.disponivel === true,
      ),
  );
}
// Obtém a oferta usada como referência única do preço central e da comparação.
export function ofertaReferencia(posto: PostoCatalogo) {
  return posto.combustiveis.find(
    (p) => p.codigo === posto.combustivel_referencia,
  )!;
}
// Escolhe entre valor, ausência de preço e oferta não confirmada no cartão.
export function rotuloPreco(posto: PostoCatalogo) {
  if (posto.preco_referencia !== null)
    return precoFormatado(posto.preco_referencia);
  return ofertaReferencia(posto).disponivel === true
    ? "Sem preço informado"
    : "Ver preços";
}
// Exibe data em Fortaleza, respeitando o fuso explícito ou o legado -03:00.
export function dataPublicacao(valor: string | null) {
  if (!valor) return "Atualização não informada";
  // DATETIME legado do backend é horário de Fortaleza, não UTC.
  const iso = /(?:Z|[+-]\d{2}:\d{2})$/.test(valor) ? valor : valor + "-03:00";
  const data = new Date(iso);
  return Number.isFinite(data.getTime())
    ? data.toLocaleString("pt-BR", { timeZone: "America/Fortaleza" })
    : "Atualização não informada";
}
// Define a cor pela faixa de preços recentes da mesma referência; não mede confiança.
export function classificarPreco(
  posto: PostoCatalogo,
  lista: PostoCatalogo[],
  agora = Date.now(),
) {
  const ref = ofertaReferencia(posto);
  // Exclui da comparação registros sem data/preço, futuros ou com mais de 72 horas.
  const recente = (p: PostoCatalogo) => {
    const data = ofertaReferencia(p).atualizado_em;
    if (!data || p.preco_referencia === null) return false;
    const instante = new Date(
      /(?:Z|[+-]\d{2}:\d{2})$/.test(data) ? data : data + "-03:00",
    ).getTime();
    return (
      Number.isFinite(instante) &&
      instante <= agora + 5000 &&
      agora - instante <= 3 * 86400000
    );
  };
  if (posto.preco_referencia === null)
    return { cor: "#596273", texto: "Preço não informado" };
  if (!recente(posto))
    return {
      cor: "#596273",
      texto: ref.atualizado_em
        ? "Preço fora da comparação recente"
        : "Atualização não informada",
    };
  const precos = lista
    .filter(
      (p) =>
        p.combustivel_referencia === posto.combustivel_referencia && recente(p),
    )
    .map((p) => p.preco_referencia!);
  const menor = Math.min(...precos),
    maior = Math.max(...precos);
  if (precos.length < 2 || menor === maior)
    return { cor: "#171923", texto: "Sem diferença de preço para comparar" };
  const proporcao = (posto.preco_referencia - menor) / (maior - menor);
  return proporcao <= 0.33
    ? { cor: "#166534", texto: "Faixa menor nesta consulta" }
    : proporcao <= 0.66
      ? { cor: "#8A6500", texto: "Faixa intermediária nesta consulta" }
      : { cor: "#B42318", texto: "Faixa maior nesta consulta" };
}
// Valida a resposta da API e preserva oferta desconhecida, autoria e ID exato do preço.
export function lerCatalogo(
  valor: unknown,
  referencia: Combustivel,
  selecionados: Combustivel[] = [],
): PostoCatalogo[] {
  if (!Array.isArray(valor)) throw new Error("Resposta de postos inválida.");
  return valor.map((bruto: unknown) => {
    if (!bruto || typeof bruto !== "object") throw new Error("Posto inválido.");
    const p = bruto as Record<string, unknown>;
    if (
      !Number.isSafeInteger(p.id) ||
      Number(p.id) <= 0 ||
      typeof p.nome !== "string" ||
      typeof p.latitude !== "number" ||
      !Number.isFinite(p.latitude) ||
      Math.abs(p.latitude) > 90 ||
      typeof p.longitude !== "number" ||
      !Number.isFinite(p.longitude) ||
      Math.abs(p.longitude) > 180 ||
      p.combustivel_referencia !== referencia ||
      !Array.isArray(p.combustiveis)
    ) {
      throw new Error(
        "Contrato de postos incompatível. Atualize o backend e tente novamente.",
      );
    }
    const ofertas = COMBUSTIVEIS.map<OfertaPosto>(({ codigo }) => {
      const item = (p.combustiveis as unknown[]).find(
        (o) =>
          !!o &&
          typeof o === "object" &&
          (o as Record<string, unknown>).codigo === codigo,
      );
      if (!item || typeof item !== "object")
        throw new Error("Catálogo incompleto.");
      const o = item as Record<string, unknown>;
      if (
        ![true, false, null].includes(o.disponivel as boolean | null) ||
        (o.preco !== null &&
          (typeof o.preco !== "number" ||
            !Number.isFinite(o.preco) ||
            o.preco <= 0))
      ) {
        throw new Error("Oferta inválida.");
      }
      return {
        codigo,
        disponivel: o.disponivel as boolean | null,
        origem: o.origem === "manual" || o.origem === "osm" ? o.origem : null,
        preco: o.preco as number | null,
        atualizado_em:
          typeof o.atualizado_em === "string" ? o.atualizado_em : null,
        autor_nome: typeof o.autor_nome === "string" ? o.autor_nome : null,
        registo_id: Number.isSafeInteger(o.registo_id) && Number(o.registo_id) > 0
          ? Number(o.registo_id) : null,
      };
    });
    const ref = ofertas.find((o) => o.codigo === referencia)!;
    const preco =
      ref.disponivel === false ||
      (selecionados.length > 0 && ref.disponivel !== true)
        ? null
        : ref.preco;
    if (p.preco_referencia !== preco)
      throw new Error("Preço de referência inconsistente.");
    return {
      id: Number(p.id),
      nome: p.nome,
      endereco:
        typeof p.endereco === "string" ? p.endereco : "Endereço não informado",
      bairro: typeof p.bairro === "string" ? p.bairro : null,
      latitude: p.latitude,
      longitude: p.longitude,
      marca: typeof p.marca === "string" ? p.marca : null,
      tipo_posto: typeof p.tipo_posto === "string" ? p.tipo_posto : "",
      ...(typeof p.distancia_m === "number" &&
      Number.isFinite(p.distancia_m) &&
      p.distancia_m >= 0
        ? { distancia_m: p.distancia_m }
        : {}),
      combustiveis: ofertas,
      combustivel_referencia: referencia,
      preco_referencia: preco,
    };
  });
}
