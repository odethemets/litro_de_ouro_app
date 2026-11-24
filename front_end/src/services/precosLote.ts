import type { PosicaoGps } from "../utils/localizacao";
import {
  FalhaCadastro,
  payloadCadastro,
  payloadCadastroRemoto,
  precoCadastro,
  produtosCadastro,
} from "./cadastroPreco";
import {
  produto,
  type Combustivel,
  type PostoCatalogo,
} from "./catalogoPostos";

export interface ItemPrecoLote {
  codigo: Combustivel;
  textoPreco: string;
  fotoUrl?: string | null;
}

export interface PedidoPrecosLote {
  posto: PostoCatalogo;
  itens: ItemPrecoLote[];
  token: string;
}

export interface PayloadPrecosLote {
  posto_id: number;
  itens: {
    tipo_combustivel: string;
    preco: string;
    foto_url?: string;
  }[];
  latitude: number;
  longitude: number;
  precisao_m: number;
  simulada: false;
}

export type PayloadPrecosLoteRemoto = Pick<
  PayloadPrecosLote,
  "posto_id" | "itens"
>;

export interface ConfirmacaoPrecosLote {
  postoId: number;
  karmaGanho: number;
  registros: {
    codigo: Combustivel;
    registoId: number;
    preco: string;
    karmaGanho: number;
  }[];
}

function nomeApi(codigo: Combustivel) {
  return codigo === "recarga_eletrica"
    ? "Recarga Elétrica (kWh)"
    : produto(codigo).nome;
}

export function validarPedidoLote(pedido: PedidoPrecosLote): PedidoPrecosLote {
  if (!pedido.token?.trim()) {
    throw new FalhaCadastro(
      "sessao",
      "Entre na sua conta para registrar preços.",
    );
  }

  if (
    !Number.isSafeInteger(pedido.posto?.id) ||
    pedido.posto.id <= 0 ||
    pedido.posto.id > 2147483647
  ) {
    throw new FalhaCadastro("validacao", "Selecione um posto válido.");
  }

  if (
    !Array.isArray(pedido.itens) ||
    !pedido.itens.length ||
    pedido.itens.length > 6
  ) {
    throw new FalhaCadastro(
      "validacao",
      "Selecione os combustíveis que deseja registrar.",
    );
  }

  const permitidos = produtosCadastro(pedido.posto);
  const vistos = new Set<Combustivel>();

  const itens = pedido.itens.map((item) => {
    if (
      !item ||
      !permitidos.some((p) => p.codigo === item.codigo) ||
      vistos.has(item.codigo)
    ) {
      throw new FalhaCadastro(
        "validacao",
        "Revise os produtos selecionados, sem repetições.",
      );
    }

    vistos.add(item.codigo);

    const preco =
      typeof item.textoPreco === "string"
        ? precoCadastro(item.textoPreco)
        : null;

    if (preco === null) {
      throw new FalhaCadastro(
        "validacao",
        "Confira o preço de " + produto(item.codigo).nome + ".",
      );
    }

    if (item.fotoUrl != null && typeof item.fotoUrl !== "string") {
      throw new FalhaCadastro("validacao", "Comprovante inválido.");
    }

    return {
      codigo: item.codigo,
      textoPreco: preco,
      fotoUrl: item.fotoUrl ?? null,
    };
  });

  return {
    token: pedido.token,
    itens,
    posto: {
      ...pedido.posto,
      combustiveis: pedido.posto.combustiveis.map((o) => ({ ...o })),
    },
  };
}

export function payloadPrecosLote(
  pedido: PedidoPrecosLote,
  gps: PosicaoGps,
  agora = Date.now(),
): PayloadPrecosLote {
  const atual = validarPedidoLote(pedido);

  const valores = atual.itens.map((item) =>
    payloadCadastro(
      {
        posto: atual.posto,
        combustivel: item.codigo,
        textoPreco: item.textoPreco,
        fotoUrl: item.fotoUrl,
        token: atual.token,
      },
      gps,
      agora,
    ),
  );

  const primeiro = valores[0];

  return {
    posto_id: primeiro.posto_id,
    latitude: primeiro.latitude,
    longitude: primeiro.longitude,
    precisao_m: primeiro.precisao_m,
    simulada: false,
    itens: valores.map(({ tipo_combustivel, preco, foto_url }) => ({
      tipo_combustivel,
      preco,
      ...(foto_url ? { foto_url } : {}),
    })),
  };
}

export function payloadPrecosLoteRemoto(
  pedido: PedidoPrecosLote,
): PayloadPrecosLoteRemoto {
  const atual = validarPedidoLote(pedido);

  return {
    posto_id: atual.posto.id,
    itens: atual.itens.map((item) => {
      const { tipo_combustivel, preco, foto_url } = payloadCadastroRemoto({
        posto: atual.posto,
        combustivel: item.codigo,
        textoPreco: item.textoPreco,
        fotoUrl: item.fotoUrl,
        token: atual.token,
      });

      return {
        tipo_combustivel,
        preco,
        ...(foto_url ? { foto_url } : {}),
      };
    }),
  };
}

function objeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === "object" && valor !== null && !Array.isArray(valor);
}

export function confirmarPrecosLote(
  status: number,
  bruto: unknown,
  pedido: PedidoPrecosLote,
  administrativo = false,
): ConfirmacaoPrecosLote {
  const incerto = () =>
    new FalhaCadastro(
      "incerto",
      "Não recebemos uma confirmação válida do lote. Confira sua atividade antes de tentar novamente.",
    );

  if (
    status !== 201 ||
    !objeto(bruto) ||
    bruto.posto_id !== pedido.posto.id ||
    bruto.total !== pedido.itens.length ||
    !Array.isArray(bruto.registros) ||
    bruto.registros.length !== pedido.itens.length ||
    !Number.isSafeInteger(bruto.karma_ganho) ||
    Number(bruto.karma_ganho) < 0 ||
    (administrativo &&
      (bruto.administrativo !== true || bruto.karma_ganho !== 0))
  ) {
    throw incerto();
  }

  const vistos = new Set<Combustivel>();
  const ids = new Set<number>();

  const registros = bruto.registros.map((r: unknown) => {
    if (!objeto(r)) throw incerto();

    const item = pedido.itens.find(
      (i) => nomeApi(i.codigo) === r.tipo_combustivel,
    );

    if (
      !item ||
      vistos.has(item.codigo) ||
      !Number.isSafeInteger(r.registo_id) ||
      Number(r.registo_id) <= 0 ||
      ids.has(Number(r.registo_id)) ||
      typeof r.preco !== "string" ||
      precoCadastro(r.preco) !== precoCadastro(item.textoPreco) ||
      !Number.isSafeInteger(r.karma_ganho) ||
      Number(r.karma_ganho) < 0 ||
      (administrativo && r.karma_ganho !== 0)
    ) {
      throw incerto();
    }

    vistos.add(item.codigo);
    ids.add(Number(r.registo_id));

    return {
      codigo: item.codigo,
      registoId: Number(r.registo_id),
      preco: r.preco,
      karmaGanho: Number(r.karma_ganho),
    };
  });

  const karmaGanho = registros.reduce((soma, r) => soma + r.karmaGanho, 0);

  if (karmaGanho !== bruto.karma_ganho) {
    throw incerto();
  }

  return {
    postoId: pedido.posto.id,
    registros,
    karmaGanho,
  };
}

function recusa(status: number, data: unknown): FalhaCadastro {
  const mensagem =
    objeto(data) && typeof data.error === "string" ? data.error : null;

  if (status === 401) {
    return new FalhaCadastro(
      "sessao",
      mensagem ?? "Entre novamente para registrar preços.",
    );
  }

  if (status >= 400 && status < 500 && status !== 408) {
    return new FalhaCadastro(
      "rejeitado",
      mensagem ?? "O servidor recusou o lote. Revise os preços selecionados.",
    );
  }

  return new FalhaCadastro(
    "incerto",
    "A confirmação não chegou. Os preços podem ter sido registrados. Confira sua atividade antes de tentar novamente.",
  );
}

export function criarEnvioPrecosLote(deps: {
  tokenAtual(): string | null;
  obterGps(): Promise<PosicaoGps>;
  administrativo?: boolean;
  postar(
    payload: PayloadPrecosLote | PayloadPrecosLoteRemoto,
    token: string,
  ): Promise<{ status: number; data: unknown }>;
}) {
  let ocupado = false;

  return {
    async enviar(pedido: PedidoPrecosLote): Promise<ConfirmacaoPrecosLote> {
      if (ocupado) {
        throw new FalhaCadastro(
          "rejeitado",
          "Um envio já está em andamento. Aguarde a confirmação.",
        );
      }

      const atual = validarPedidoLote(pedido);

      const conferirSessao = () => {
        if (deps.tokenAtual() !== atual.token) {
          throw new FalhaCadastro(
            "sessao",
            "A sessão mudou. Entre novamente antes de registrar.",
          );
        }
      };

      conferirSessao();
      ocupado = true;

      try {
        let payload: PayloadPrecosLote | PayloadPrecosLoteRemoto;

        if (deps.administrativo === true) {
          payload = payloadPrecosLoteRemoto(atual);
        } else {
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

          conferirSessao();
          payload = payloadPrecosLote(atual, gps);
        }

        let resposta: {
          status: number;
          data: unknown;
        };

        try {
          resposta = await deps.postar(payload, atual.token);
        } catch (erro) {
          const r =
            objeto(erro) && objeto(erro.response) ? erro.response : null;

          throw recusa(typeof r?.status === "number" ? r.status : 0, r?.data);
        }

        if (resposta.status !== 201) {
          throw recusa(resposta.status, resposta.data);
        }

        conferirSessao();

        return confirmarPrecosLote(
          resposta.status,
          resposta.data,
          atual,
          deps.administrativo === true,
        );
      } finally {
        ocupado = false;
      }
    },
  };
}
