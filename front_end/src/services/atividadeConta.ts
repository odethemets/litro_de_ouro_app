import { combustiveis } from "../theme/design";

export interface RegistoPessoal {
  id: number;
  posto_nome: string;
  posto_endereco: string;
  tipo_combustivel: string;
  preco: number;
  data_formatada: string;
}

export interface VistoPessoal {
  id: number;
  nome: string;
  endereco: string;
  dataVisualizacao: string;
}

const objeto = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null;

const idValido = (id: unknown) =>
  typeof id === "number" && Number.isSafeInteger(id) && id > 0;

export function validarRegistos(value: unknown): RegistoPessoal[] {
  if (!Array.isArray(value)) {
    throw new Error("Histórico inválido.");
  }

  const ids = new Set<number>();

  return value.map((r) => {
    if (!objeto(r)) {
      throw new Error("Registro inválido.");
    }

    const preco =
      typeof r.preco === "number"
        ? r.preco
        : typeof r.preco === "string" && /^\d+(\.\d+)?$/.test(r.preco)
          ? Number(r.preco)
          : NaN;

    if (
      !idValido(r.id) ||
      ids.has(r.id as number) ||
      !Number.isFinite(preco) ||
      preco <= 0 ||
      typeof r.posto_nome !== "string" ||
      typeof r.posto_endereco !== "string" ||
      typeof r.tipo_combustivel !== "string" ||
      typeof r.data_formatada !== "string"
    ) {
      throw new Error("Registro inválido.");
    }

    ids.add(r.id as number);

    return {
      id: r.id as number,
      posto_nome: r.posto_nome,
      posto_endereco: r.posto_endereco,
      tipo_combustivel: r.tipo_combustivel,
      preco,
      data_formatada: r.data_formatada,
    };
  });
}

export function validarVistos(raw: string | null): VistoPessoal[] {
  if (raw === null) return [];

  const value: unknown = JSON.parse(raw);

  if (
    !Array.isArray(value) ||
    value.some(
      (p) =>
        !objeto(p) ||
        !idValido(p.id) ||
        typeof p.nome !== "string" ||
        typeof p.endereco !== "string" ||
        typeof p.dataVisualizacao !== "string",
    )
  ) {
    throw new Error("Histórico local inválido.");
  }

  return value as VistoPessoal[];
}

export function produtoHistorico(tipo: string) {
  const codigo = tipo
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/\s*\(kwh\)\s*$/, "")
    .trim()
    .replace(/\s+/g, "_");

  return Object.hasOwn(combustiveis, codigo)
    ? combustiveis[codigo as keyof typeof combustiveis]
    : null;
}

export const formatarPreco = (preco: number) =>
  preco.toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

export const iniciaisNome = (nome: string) =>
  nome
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((parte) => Array.from(parte)[0] ?? "")
    .join("")
    .toUpperCase() || "U";
