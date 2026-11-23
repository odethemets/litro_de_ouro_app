import type { ImagePickerAsset } from "expo-image-picker";
import type { PosicaoGps } from "../utils/localizacao";
import { api } from "./API";
import { COMBUSTIVEIS, type Combustivel } from "./catalogoPostos";
import { validarFoto } from "./leituraTotem";
import { payloadOferta } from "./ofertas";

export type EstadoSolicitacao = "pendente" | "aprovada" | "rejeitada";

export interface SolicitacaoServico {
  id: number;
  posto_id: number;
  posto_nome: string;
  posto_endereco: string;
  codigo: Combustivel;
  observacao: string;
  estado: EstadoSolicitacao;
  motivo: string | null;
  criado_em: string;
  revisado_em: string | null;
  distancia_m: number;
  precisao_m: number;
  pode_revisar: boolean;
}

export interface PaginaServicos {
  itens: SolicitacaoServico[];
  antes_de: number | null;
}

const codigos = new Set<string>(COMBUSTIVEIS.map((p) => p.codigo));

const idValido = (n: unknown): n is number =>
  typeof n === "number" && Number.isSafeInteger(n) && n > 0 && n <= 2147483647;

const objeto = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

const dataValida = (v: unknown): v is string =>
  typeof v === "string" && /Z$/.test(v) && Number.isFinite(Date.parse(v));

const textoValido = (v: unknown, limite: number): v is string =>
  typeof v === "string" && v.length <= limite;

export function lerSolicitacao(v: unknown): SolicitacaoServico {
  if (
    !objeto(v) ||
    !idValido(v.id) ||
    !idValido(v.posto_id) ||
    !textoValido(v.posto_nome, 150) ||
    !v.posto_nome.trim() ||
    !textoValido(v.posto_endereco, 255) ||
    !textoValido(v.observacao, 500) ||
    typeof v.codigo !== "string" ||
    !codigos.has(v.codigo) ||
    typeof v.estado !== "string" ||
    !["pendente", "aprovada", "rejeitada"].includes(v.estado) ||
    !(v.motivo === null || textoValido(v.motivo, 500)) ||
    !dataValida(v.criado_em) ||
    !(v.revisado_em === null || dataValida(v.revisado_em)) ||
    typeof v.distancia_m !== "number" ||
    !Number.isFinite(v.distancia_m) ||
    v.distancia_m < 0 ||
    typeof v.precisao_m !== "number" ||
    !Number.isFinite(v.precisao_m) ||
    v.precisao_m < 0 ||
    typeof v.pode_revisar !== "boolean" ||
    (v.estado === "pendente"
      ? v.revisado_em !== null
      : v.revisado_em === null) ||
    (v.estado === "rejeitada" &&
      (typeof v.motivo !== "string" || !v.motivo.trim())) ||
    (v.estado !== "pendente" && v.pode_revisar)
  ) {
    throw new Error(
      "A API retornou uma solicitação inválida. Atualize a lista.",
    );
  }

  // Não propaga campos extras, caminhos privados ou dados de outra conta.
  return {
    id: v.id,
    posto_id: v.posto_id,
    posto_nome: v.posto_nome,
    posto_endereco: v.posto_endereco,
    codigo: v.codigo as Combustivel,
    observacao: v.observacao,
    estado: v.estado as EstadoSolicitacao,
    motivo: v.motivo as string | null,
    criado_em: v.criado_em,
    revisado_em: v.revisado_em as string | null,
    distancia_m: v.distancia_m,
    precisao_m: v.precisao_m,
    pode_revisar: v.pode_revisar,
  };
}

export function lerPaginaServicos(v: unknown): PaginaServicos {
  if (
    !objeto(v) ||
    !Array.isArray(v.itens) ||
    v.itens.length > 20 ||
    !(v.antes_de === null || idValido(v.antes_de))
  ) {
    throw new Error("Página de solicitações inválida.");
  }

  const itens = v.itens.map(lerSolicitacao);

  if (
    itens.some((p, i) => i > 0 && p.id >= itens[i - 1].id) ||
    (v.antes_de !== null &&
      (itens.length !== 20 || v.antes_de !== itens.at(-1)?.id))
  ) {
    throw new Error("Página de solicitações inconsistente.");
  }

  return { itens, antes_de: v.antes_de };
}

export function lerAcessoServicos(v: unknown): boolean {
  if (!objeto(v) || typeof v.pode_moderar !== "boolean") {
    throw new Error("Acesso de revisão não confirmado.");
  }

  return v.pode_moderar;
}

export function lerFotoServico(v: unknown): string {
  if (
    !objeto(v) ||
    v.mime !== "image/jpeg" ||
    typeof v.base64 !== "string" ||
    !v.base64.startsWith("/9j/") ||
    v.base64.length > Math.ceil(2097152 / 3) * 4 ||
    v.base64.length % 4 !== 0 ||
    !/^[A-Za-z0-9+/]+={0,2}$/.test(v.base64)
  ) {
    throw new Error("Não recebemos uma foto válida para revisão.");
  }

  return "data:image/jpeg;base64," + v.base64;
}

export function novaChaveSolicitacao(): string {
  // Chave de idempotência local, não é credencial nem autorização.
  return Array.from({ length: 4 }, () =>
    Math.floor(Math.random() * 0x100000000)
      .toString(16)
      .padStart(8, "0"),
  ).join("");
}

export class FalhaSolicitacao extends Error {
  constructor(
    mensagem: string,
    readonly incerta: boolean,
  ) {
    super(mensagem);
    this.name = "FalhaSolicitacao";
  }
}

export function falhaSolicitacao(
  erro: unknown,
  enviou: boolean,
): FalhaSolicitacao {
  if (erro instanceof FalhaSolicitacao) return erro;

  const resposta = (
    erro as {
      response?: {
        status?: number;
        data?: { error?: unknown; codigo?: unknown };
      };
    } | null
  )?.response;

  const status = resposta?.status ?? 0;
  const incerta =
    enviou &&
    !(status >= 400 && status < 500 && status !== 408) &&
    resposta?.data?.codigo !== "FOTO_NAO_GUARDADA";

  return new FalhaSolicitacao(
    incerta
      ? "A confirmação não chegou. Confira a lista de solicitações antes de repetir."
      : typeof resposta?.data?.error === "string"
        ? resposta.data.error
        : erro instanceof Error
          ? erro.message
          : "Não foi possível concluir a solicitação.",
    incerta,
  );
}

interface Pedido {
  postoId: number;
  codigo: Combustivel;
  foto: ImagePickerAsset;
  observacao: string;
  consentimento: boolean;
  presencaObservada: boolean;
  chave: string;
  token: string;
  signal: AbortSignal;
}

export function criarEnvioSolicitacao(deps: {
  tokenAtual(): string | null;
  prepararFoto(
    foto: ImagePickerAsset,
    signal: AbortSignal,
  ): Promise<Blob | null>;
  obterGps(): Promise<PosicaoGps>;
  postar(
    postoId: number,
    dados: FormData,
    token: string,
    signal: AbortSignal,
  ): Promise<{ status: number; data: unknown }>;
}) {
  let ocupado = false;

  return {
    async enviar(original: Pedido): Promise<SolicitacaoServico> {
      if (ocupado) {
        throw new FalhaSolicitacao("Há uma solicitação em andamento.", false);
      }

      const p = { ...original, foto: { ...original.foto } };

      if (
        !idValido(p.postoId) ||
        !codigos.has(p.codigo) ||
        !/^[a-f0-9]{32}$/.test(p.chave) ||
        !p.token.trim() ||
        !p.consentimento ||
        !p.presencaObservada ||
        p.observacao.trim().length > 500
      ) {
        throw new FalhaSolicitacao(
          "Confira posto, serviço, observação e as duas confirmações.",
          false,
        );
      }

      validarFoto(p.foto);
      ocupado = true;
      let enviou = false;

      const vigente = () => {
        if (p.signal.aborted || deps.tokenAtual() !== p.token) {
          throw new FalhaSolicitacao(
            "A sessão ou a tela mudou. Confira suas solicitações ao entrar novamente.",
            enviou,
          );
        }
      };

      try {
        vigente();

        const arquivo = await deps.prepararFoto(p.foto, p.signal);
        vigente();

        const posicao = payloadOferta(await deps.obterGps());
        vigente();

        const dados = new FormData();

        if (arquivo) {
          dados.append("foto", arquivo, "servico");
        } else {
          dados.append("foto", {
            uri: p.foto.uri,
            name: "servico",
            type: p.foto.mimeType ?? "image/jpeg",
          } as unknown as Blob);
        }

        dados.append("codigo", p.codigo);
        dados.append("chave_cliente", p.chave);
        dados.append("observacao", p.observacao.trim());
        dados.append("consentimento", "true");
        dados.append("presenca_observada", "true");
        dados.append("simulada", "false");

        for (const campo of ["latitude", "longitude", "precisao_m"] as const) {
          dados.append(campo, String(posicao[campo]));
        }

        vigente();
        enviou = true;

        const resposta = await deps.postar(p.postoId, dados, p.token, p.signal);
        vigente();

        if (resposta.status !== 200 && resposta.status !== 201) {
          throw { response: resposta };
        }

        const item = lerSolicitacao(resposta.data);

        if (item.posto_id !== p.postoId || item.codigo !== p.codigo) {
          throw new FalhaSolicitacao(
            "Recebemos confirmação de outro serviço. Confira suas solicitações.",
            true,
          );
        }

        return item;
      } catch (erro) {
        throw falhaSolicitacao(erro, enviou);
      } finally {
        ocupado = false;
      }
    },
  };
}

const headers = (token: string) => ({
  Authorization: "Bearer " + token,
});

export async function consultarSolicitacoes(
  token: string,
  signal: AbortSignal,
  admin: boolean,
  estado: EstadoSolicitacao | "todos",
  antes?: number,
) {
  const { data } = await api.get(
    admin ? "/admin/servicos/solicitacoes" : "/servicos/solicitacoes/minhas",
    {
      headers: headers(token),
      signal,
      params: {
        estado,
        ...(antes ? { antes_de: antes } : {}),
      },
    },
  );

  if (signal.aborted) throw new Error("Consulta cancelada.");

  const pagina = lerPaginaServicos(data);

  if (
    pagina.itens.some(
      (i) =>
        (estado !== "todos" && i.estado !== estado) ||
        (antes !== undefined && i.id >= antes),
    )
  ) {
    throw new Error("A lista retornou solicitações de outro filtro ou página.");
  }

  return pagina;
}

export async function consultarFotoServico(
  id: number,
  token: string,
  signal: AbortSignal,
) {
  if (!idValido(id)) throw new Error("Solicitação inválida.");

  const { data } = await api.get(`/admin/servicos/solicitacoes/${id}/foto`, {
    signal,
    headers: headers(token),
    timeout: 30000,
  });

  if (signal.aborted) throw new Error("Consulta cancelada.");

  return lerFotoServico(data);
}

export async function decidirServico(
  item: SolicitacaoServico,
  decisao: "aprovar" | "rejeitar",
  motivo: string,
  fotoRevisada: boolean,
  token: string,
  signal: AbortSignal,
) {
  if (
    !item.pode_revisar ||
    item.estado !== "pendente" ||
    (decisao === "aprovar" && !fotoRevisada) ||
    (decisao === "rejeitar" && !motivo.trim()) ||
    motivo.trim().length > 500
  ) {
    throw new FalhaSolicitacao(
      "Revise a foto ou informe o motivo antes de decidir.",
      false,
    );
  }

  try {
    const { data } = await api.post(
      `/admin/servicos/solicitacoes/${item.id}/decidir`,
      {
        decisao,
        motivo: motivo.trim(),
        foto_revisada: fotoRevisada,
      },
      {
        headers: headers(token),
        signal,
        timeout: 30000,
      },
    );

    if (signal.aborted) {
      throw new FalhaSolicitacao(
        "Confira a lista antes de repetir a decisão.",
        true,
      );
    }

    const resultado = lerSolicitacao(data);

    if (
      resultado.id !== item.id ||
      resultado.posto_id !== item.posto_id ||
      resultado.codigo !== item.codigo ||
      resultado.estado !== (decisao === "aprovar" ? "aprovada" : "rejeitada")
    ) {
      throw new FalhaSolicitacao(
        "A confirmação da decisão é inconsistente. Atualize a lista.",
        true,
      );
    }

    return resultado;
  } catch (erro) {
    throw falhaSolicitacao(erro, true);
  }
}
