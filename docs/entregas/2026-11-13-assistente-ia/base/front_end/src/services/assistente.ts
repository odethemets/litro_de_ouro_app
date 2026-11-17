import { isAxiosError } from "axios";
import type { PosicaoUsuario } from "../components/mapa/tipos";
import { api } from "./API";
import {
    COMBUSTIVEIS,
    lerCatalogo,
    type Combustivel,
    type FiltrosPostos,
    type PostoCatalogo,
} from "./catalogoPostos";

export interface BuscaAssistida {
  filtros: FiltrosPostos;
  postos: PostoCatalogo[];
  total: number;
  interpretacao: "comando" | "gemini";
  localizacao_usada: boolean;
  mensagem: string;
}

const codigos = new Set<string>(COMBUSTIVEIS.map((c) => c.codigo));

function objeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === "object" && valor !== null && !Array.isArray(valor);
}

function combustivel(valor: unknown): valor is Combustivel {
  return typeof valor === "string" && codigos.has(valor);
}

export function validarFiltrosBusca(valor: unknown): FiltrosPostos {
  if (
    !objeto(valor) ||
    !Array.isArray(valor.combustiveis) ||
    valor.combustiveis.length > 6 ||
    !valor.combustiveis.every(combustivel) ||
    new Set(valor.combustiveis).size !== valor.combustiveis.length ||
    !combustivel(valor.referencia) ||
    (valor.combustiveis.length > 0 &&
      !valor.combustiveis.includes(valor.referencia)) ||
    typeof valor.marca !== "string" ||
    valor.marca.length > 120 ||
    /[\u0000-\u001f\u007f]/.test(valor.marca) ||
    (valor.ordenar !== "preco" && valor.ordenar !== "distancia")
  ) {
    throw new Error("A API retornou filtros de busca inválidos.");
  }

  return {
    combustiveis: valor.combustiveis,
    referencia: valor.referencia,
    marca: valor.marca,
    ordenar: valor.ordenar,
  };
}

export function validarBusca(valor: unknown): BuscaAssistida {
  if (
    !objeto(valor) ||
    !Array.isArray(valor.postos) ||
    valor.postos.length > 20 ||
    typeof valor.total !== "number" ||
    !Number.isSafeInteger(valor.total) ||
    valor.total < valor.postos.length ||
    valor.total > 500 ||
    valor.postos.length !== Math.min(valor.total, 20) ||
    typeof valor.localizacao_usada !== "boolean" ||
    (valor.interpretacao !== "comando" && valor.interpretacao !== "gemini") ||
    typeof valor.mensagem !== "string" ||
    !valor.mensagem.trim()
  ) {
    throw new Error("A API não retornou uma busca válida.");
  }

  const filtros = validarFiltrosBusca(valor.filtros);

  const postos = lerCatalogo(
    valor.postos,
    filtros.referencia,
    filtros.combustiveis,
  );

  if (
    new Set(postos.map((p) => p.id)).size !== postos.length ||
    postos.some((p) =>
      valor.localizacao_usada
        ? p.distancia_m === undefined
        : p.distancia_m !== undefined,
    )
  ) {
    throw new Error("A API retornou dados inconsistentes para a busca.");
  }

  return {
    filtros,
    postos,
    total: valor.total,
    mensagem: valor.mensagem,
    interpretacao: valor.interpretacao,
    localizacao_usada: valor.localizacao_usada,
  };
}

export async function consultarAssistente(
  mensagem: string,
  filtros: FiltrosPostos,
  usuario: PosicaoUsuario | null,
  signal: AbortSignal,
) {
  const { data } = await api.post(
    "/ia/consultar",
    {
      mensagem: mensagem.trim(),
      filtros,
      ...(usuario
        ? {
            latitude: usuario.lat,
            longitude: usuario.lon,
          }
        : {}),
    },
    {
      signal,
      timeout: 60000,
    },
  );

  return validarBusca(data);
}

export function mensagemErroBusca(erro: unknown) {
  if (isAxiosError<{ error?: unknown }>(erro)) {
    if (!erro.response) {
      return "A API não respondeu. " + "Confira a conexão e tente novamente.";
    }

    const detalhe =
      typeof erro.response.data?.error === "string"
        ? erro.response.data.error
        : "Não foi possível consultar os postos.";

    return "HTTP " + erro.response.status + ": " + detalhe;
  }

  return erro instanceof Error
    ? erro.message
    : "Não foi possível consultar os postos.";
}
