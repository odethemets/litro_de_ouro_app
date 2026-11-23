import type { PosicaoGps } from "../utils/localizacao";
import {
  COMBUSTIVEIS,
  type Combustivel,
  type PostoCatalogo,
} from "./catalogoPostos";

export interface PedidoCadastro {
  posto: PostoCatalogo;
  combustivel: Combustivel;
  textoPreco: string;
  fotoUrl?: string | null;
  token: string;
}

export interface PayloadPreco {
  foto_url?: string;
  posto_id: number;
  tipo_combustivel: string;
  preco: string;
  latitude: number;
  longitude: number;
  precisao_m: number;
  simulada: false;
}

export interface ConfirmacaoPreco {
  registoId: number;
  postoId: number;
  karmaGanho: number;
}

export class FalhaCadastro extends Error {
  constructor(
    readonly tipo: "validacao" | "gps" | "sessao" | "rejeitado" | "incerto",
    mensagem: string,
  ) {
    super(mensagem);
    this.name = "FalhaCadastro";
  }
}

export function precoCadastro(texto: string): string | null {
  const limpo = texto.trim();

  if (!/^\d+(?:[.,]\d{1,2})?$/.test(limpo)) {
    return null;
  }

  const valor = Number(limpo.replace(",", "."));

  return Number.isFinite(valor) && valor >= 0.01 && valor <= 25
    ? valor.toFixed(2)
    : null;
}

export function produtosCadastro(posto: PostoCatalogo) {
  const eletrico = posto.tipo_posto === "Eletroposto";

  return COMBUSTIVEIS.filter((produto) => {
    const oferta = posto.combustiveis.find((o) => o.codigo === produto.codigo);

    if (oferta?.disponivel === false) {
      return false;
    }

    if (eletrico) {
      return produto.codigo === "recarga_eletrica";
    }

    return produto.codigo !== "recarga_eletrica" || oferta?.disponivel === true;
  });
}

export function produtoInicialCadastro(
  posto: PostoCatalogo,
  preferido: Combustivel,
): Combustivel | null {
  const opcoes = produtosCadastro(posto);

  return (
    opcoes.find((p) => p.codigo === preferido)?.codigo ??
    opcoes[0]?.codigo ??
    null
  );
}

function validarPedido(pedido: PedidoCadastro) {
  if (!pedido.token) {
    throw new FalhaCadastro(
      "sessao",
      "Entre na sua conta para registrar um preço.",
    );
  }

  if (!Number.isSafeInteger(pedido.posto.id) || pedido.posto.id <= 0) {
    throw new FalhaCadastro("validacao", "Selecione um posto válido.");
  }

  if (
    !produtosCadastro(pedido.posto).some((p) => p.codigo === pedido.combustivel)
  ) {
    throw new FalhaCadastro(
      "validacao",
      "Selecione um combustível disponível para este cadastro.",
    );
  }

  const preco = precoCadastro(pedido.textoPreco);

  if (preco === null) {
    throw new FalhaCadastro(
      "validacao",
      "Informe um preço entre R$ 0,01 e R$ 25,00, com até duas casas decimais.",
    );
  }

  return preco;
}

export function payloadCadastro(
  pedido: PedidoCadastro,
  gps: PosicaoGps,
  agora = Date.now(),
): PayloadPreco {
  const preco = validarPedido(pedido);

  if (
    !Number.isFinite(gps.latitude) ||
    Math.abs(gps.latitude) > 90 ||
    !Number.isFinite(gps.longitude) ||
    Math.abs(gps.longitude) > 180 ||
    (gps.latitude === 0 && gps.longitude === 0) ||
    !Number.isFinite(gps.precisaoM) ||
    gps.precisaoM < 0 ||
    gps.precisaoM > 150 ||
    !Number.isFinite(gps.obtidaEm) ||
    gps.obtidaEm > agora + 5000 ||
    agora - gps.obtidaEm > 15000 ||
    gps.simulada
  ) {
    throw new FalhaCadastro(
      "gps",
      "Precisamos de uma localização atual e precisa do aparelho. Atualize a localização e tente novamente.",
    );
  }

  const info = COMBUSTIVEIS.find((p) => p.codigo === pedido.combustivel)!;

  return {
    // Encaminha apenas o comprovante escolhido; o backend valida a URL.
    ...(pedido.fotoUrl ? { foto_url: pedido.fotoUrl } : {}),
    posto_id: pedido.posto.id,
    tipo_combustivel:
      info.codigo === "recarga_eletrica" ? "Recarga Elétrica (kWh)" : info.nome,
    preco,
    latitude: gps.latitude,
    longitude: gps.longitude,
    precisao_m: gps.precisaoM,
    simulada: false,
  };
}

export function confirmarCadastro(
  status: number,
  bruto: unknown,
  postoId: number,
): ConfirmacaoPreco {
  const r =
    bruto && typeof bruto === "object"
      ? (bruto as Record<string, unknown>)
      : {};

  if (
    status !== 201 ||
    !Number.isSafeInteger(r.registo_id) ||
    Number(r.registo_id) <= 0 ||
    r.posto_id !== postoId ||
    !Number.isSafeInteger(r.karma_ganho) ||
    Number(r.karma_ganho) < 0
  ) {
    throw new FalhaCadastro(
      "incerto",
      "Não recebemos uma confirmação válida. Confira sua atividade antes de tentar registrar novamente.",
    );
  }

  return {
    registoId: Number(r.registo_id),
    postoId,
    karmaGanho: Number(r.karma_ganho),
  };
}

function falhaRespostaCadastro(
  status: number | undefined,
  bruto: unknown,
): FalhaCadastro {
  const dados =
    bruto && typeof bruto === "object"
      ? (bruto as Record<string, unknown>)
      : {};

  const mensagem =
    typeof dados.error === "string" && dados.error.trim() ? dados.error : null;

  if (status === 401) {
    return new FalhaCadastro(
      "sessao",
      mensagem ?? "Sua sessão expirou. Entre novamente antes de registrar.",
    );
  }

  if (status !== undefined && status >= 400 && status < 500 && status !== 408) {
    return new FalhaCadastro(
      "rejeitado",
      mensagem ??
        "O servidor recusou o registro. Confira os dados e tente novamente.",
    );
  }

  return new FalhaCadastro(
    "incerto",
    "A confirmação não chegou. O preço pode ter sido registrado. Confira sua atividade antes de tentar novamente.",
  );
}

export function criarEnvioPreco(deps: {
  tokenAtual(): string | null;
  obterGps(): Promise<PosicaoGps>;
  postar(
    payload: PayloadPreco,
    token: string,
  ): Promise<{ status: number; data: unknown }>;
}) {
  let ocupado = false;

  return {
    async enviar(original: PedidoCadastro): Promise<ConfirmacaoPreco> {
      if (ocupado) {
        throw new FalhaCadastro(
          "rejeitado",
          "Um envio já está em andamento. Aguarde a confirmação.",
        );
      }

      // Captura o contexto antes de aguardar o GPS.
      const pedido: PedidoCadastro = {
        ...original,
        posto: {
          ...original.posto,
          combustiveis: original.posto.combustiveis.map((oferta) => ({
            ...oferta,
          })),
        },
      };

      validarPedido(pedido);
      ocupado = true;

      try {
        let gps: PosicaoGps;

        try {
          gps = await deps.obterGps();
        } catch (erro) {
          throw new FalhaCadastro(
            "gps",
            erro instanceof Error
              ? erro.message
              : "Não foi possível obter sua localização.",
          );
        }

        if (deps.tokenAtual() !== pedido.token) {
          throw new FalhaCadastro(
            "sessao",
            "A sessão mudou. Entre novamente antes de registrar.",
          );
        }

        const payload = payloadCadastro(pedido, gps);

        let resposta: {
          status: number;
          data: unknown;
        };

        try {
          resposta = await deps.postar(payload, pedido.token);
        } catch (erro) {
          const r = (
            erro as {
              response?: {
                status?: number;
                data?: unknown;
              };
            } | null
          )?.response;

          throw falhaRespostaCadastro(r?.status, r?.data);
        }

        if (resposta.status !== 201) {
          throw falhaRespostaCadastro(resposta.status, resposta.data);
        }

        return confirmarCadastro(
          resposta.status,
          resposta.data,
          pedido.posto.id,
        );
      } finally {
        ocupado = false;
      }
    },
  };
}
