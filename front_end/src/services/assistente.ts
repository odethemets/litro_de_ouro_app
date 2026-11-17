import { isAxiosError } from "axios";
import type { PosicaoUsuario } from "../components/mapa/tipos";
import { api } from "./API";
import {
  COMBUSTIVEIS, lerCatalogo, type Combustivel,
  type FiltrosPostos, type PostoCatalogo,
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
// Respostas do provedor precisam passar pelo contrato antes de chegar ao estado global.
function objeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === "object" && valor !== null && !Array.isArray(valor);
}
// Aceita somente os seis produtos do catálogo fixo.
function combustivel(valor: unknown): valor is Combustivel {
  return typeof valor === "string" && codigos.has(valor);
}

// Clona a seleção e mantém uma referência única, sem substituir por outro produto.
export function validarFiltrosBusca(valor: unknown): FiltrosPostos {
  if (!objeto(valor) || !Array.isArray(valor.combustiveis)
    || valor.combustiveis.length > 6 || !valor.combustiveis.every(combustivel)
    || new Set(valor.combustiveis).size !== valor.combustiveis.length
    || !combustivel(valor.referencia)
    || (valor.combustiveis.length > 0 && !valor.combustiveis.includes(valor.referencia))
    || typeof valor.marca !== "string" || valor.marca.length > 120
    || /[\u0000-\u001f\u007f]/.test(valor.marca)
    || (valor.ordenar !== "preco" && valor.ordenar !== "distancia")) {
    throw new Error("A API retornou filtros de busca inválidos.");
  }
  return { combustiveis: [...valor.combustiveis], referencia: valor.referencia,
    marca: valor.marca, ordenar: valor.ordenar };
}

// Confere prévia, referência e distâncias; preços continuam vindo do catálogo.
export function validarBusca(valor: unknown): BuscaAssistida {
  if (!objeto(valor) || !Array.isArray(valor.postos) || valor.postos.length > 20
    || typeof valor.total !== "number" || !Number.isSafeInteger(valor.total)
    || valor.total < valor.postos.length || valor.total > 500
    || valor.postos.length !== Math.min(valor.total, 20)
    || typeof valor.localizacao_usada !== "boolean"
    || (valor.interpretacao !== "comando" && valor.interpretacao !== "gemini")
    || typeof valor.mensagem !== "string" || !valor.mensagem.trim()) {
    throw new Error("A API não retornou uma busca válida.");
  }
  const filtros = validarFiltrosBusca(valor.filtros);
  const postos = lerCatalogo(valor.postos, filtros.referencia, filtros.combustiveis);
  if (new Set(postos.map((p) => p.id)).size !== postos.length
    || postos.some((p) => valor.localizacao_usada
      ? p.distancia_m === undefined : p.distancia_m !== undefined)) {
    throw new Error("A API retornou dados inconsistentes para a busca.");
  }
  return { filtros, postos, total: valor.total, mensagem: valor.mensagem,
    interpretacao: valor.interpretacao, localizacao_usada: valor.localizacao_usada };
}

// Envia um retrato da busca com a sessão capturada; nunca cria coordenadas padrão.
export async function consultarAssistente(
  mensagem: string,
  filtros: FiltrosPostos,
  usuario: PosicaoUsuario | null,
  signal: AbortSignal,
  token?: string,
) {
  const texto = mensagem.trim();
  if (!texto || texto.length > 500) throw new Error("Informe uma busca de até 500 caracteres.");
  if (token !== undefined && !token.trim()) throw new Error("Entre novamente para usar o assistente.");
  if (signal.aborted) throw new Error("Busca cancelada.");
  const selecao = validarFiltrosBusca(filtros);
  if (usuario && (!Number.isFinite(usuario.lat) || Math.abs(usuario.lat) > 90
    || !Number.isFinite(usuario.lon) || Math.abs(usuario.lon) > 180
    || (usuario.lat === 0 && usuario.lon === 0))) {
    throw new Error("Atualize sua localização antes de buscar por proximidade.");
  }
  const { data } = await api.post("/ia/consultar", {
    mensagem: texto, filtros: selecao,
    ...(usuario ? { latitude: usuario.lat, longitude: usuario.lon } : {}),
  }, { signal, timeout: 60000,
    ...(token ? { headers: { Authorization: "Bearer " + token } } : {}),
  });
  return validarBusca(data);
}

// Mantém mensagens de rede/recusa legíveis, sem imprimir payloads ou credenciais.
export function mensagemErroBusca(erro: unknown) {
  if (isAxiosError<{ error?: unknown }>(erro)) {
    if (!erro.response) return "A API não respondeu. Confira a conexão e tente novamente.";
    const detalhe = typeof erro.response.data?.error === "string"
      ? erro.response.data.error : "Não foi possível consultar os postos.";
    return "HTTP " + erro.response.status + ": " + detalhe;
  }
  return erro instanceof Error ? erro.message : "Não foi possível consultar os postos.";
}
