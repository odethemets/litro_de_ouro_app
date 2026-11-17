import { sessaoRejeitada, type PerfilUsuario } from "./contratoAuth";

export type EstadoAuth =
  | "INITIALIZING"
  | "GUEST"
  | "AUTHENTICATED"
  | "UNAUTHENTICATED";

export type DestinoAuth = "Entrada" | "Login" | "Registo";

export interface EstadoSessao {
  status: EstadoAuth;
  userToken: string | null;
  perfil: PerfilUsuario | null;
  erroInicializacao: string | null;
  destinoAuth: DestinoAuth;
}

interface Dependencias {
  armazenamento: {
    ler(): Promise<string | null>;
    gravar(token: string): Promise<void>;
    remover(): Promise<void>;
  };
  validar(token: string): Promise<PerfilUsuario>;
  publicarToken(token: string | null): void;
}

export function criarControleSessao(deps: Dependencias) {
  let estado: EstadoSessao = {
    status: "INITIALIZING",
    userToken: null,
    perfil: null,
    erroInicializacao: null,
    destinoAuth: "Entrada",
  };

  let revisao = 0;
  let repetirSaida = false;

  const ouvintes = new Set<() => void>();

  const atualizar = (mudancas: Partial<EstadoSessao>) => {
    estado = { ...estado, ...mudancas };

    deps.publicarToken(
      estado.status === "AUTHENTICATED" ? estado.userToken : null,
    );

    ouvintes.forEach((ouvinte) => ouvinte());
  };

  const semSessao = (
    status: EstadoAuth,
    destinoAuth: DestinoAuth = "Entrada",
  ) =>
    atualizar({
      status,
      userToken: null,
      perfil: null,
      erroInicializacao: null,
      destinoAuth,
    });

  const falhaDeSaida = () => {
    repetirSaida = true;
    semSessao("INITIALIZING");

    atualizar({
      erroInicializacao:
        "Não foi possível remover a sessão. Permita o armazenamento e tente novamente.",
    });
  };

  async function inicializar() {
    if (repetirSaida) return sair();

    const pedido = ++revisao;
    semSessao("INITIALIZING");

    try {
      const token = await deps.armazenamento.ler();

      if (pedido !== revisao) return;

      if (!token) {
        semSessao("UNAUTHENTICATED");
        return;
      }

      let perfil: PerfilUsuario;

      try {
        perfil = await deps.validar(token);
      } catch (erro) {
        if (pedido !== revisao) return;
        if (!sessaoRejeitada(erro)) throw erro;

        try {
          await deps.armazenamento.remover();
        } catch {
          if (pedido === revisao) falhaDeSaida();
          return;
        }

        if (pedido === revisao) {
          semSessao("UNAUTHENTICATED");
        }

        return;
      }

      if (pedido === revisao) {
        atualizar({
          status: "AUTHENTICATED",
          userToken: token,
          perfil,
        });
      }
    } catch {
      if (pedido === revisao) {
        atualizar({
          erroInicializacao:
            "Não foi possível validar sua sessão. Confira a conexão e o armazenamento e tente novamente. A sessão salva foi preservada.",
        });
      }
    }
  }

  async function entrar(token: string) {
    if (typeof token !== "string" || !token.trim()) {
      throw new Error("A API não retornou uma sessão válida.");
    }

    const pedido = ++revisao;
    const perfil = await deps.validar(token);

    if (pedido !== revisao) return;

    await deps.armazenamento.gravar(token);

    if (pedido === revisao) {
      repetirSaida = false;

      atualizar({
        status: "AUTHENTICATED",
        userToken: token,
        perfil,
        erroInicializacao: null,
      });
    }
  }

  async function sair() {
    const pedido = ++revisao;
    semSessao("UNAUTHENTICATED");

    try {
      await deps.armazenamento.remover();

      if (pedido === revisao) {
        repetirSaida = false;
      }
    } catch {
      if (pedido === revisao) falhaDeSaida();
    }
  }

  return {
    getSnapshot: () => estado,

    subscribe: (ouvinte: () => void) => {
      ouvintes.add(ouvinte);

      return () => {
        ouvintes.delete(ouvinte);
      };
    },

    inicializar,
    entrar,
    sair,

    visitante: () => {
      ++revisao;
      semSessao("GUEST");
    },

    abrirEntrada: (destino: DestinoAuth = "Entrada") => {
      ++revisao;
      semSessao("UNAUTHENTICATED", destino);
    },

    cancelar: () => {
      ++revisao;
    },

    rejeitar: (token: string) => {
      if (estado.userToken === token) {
        void sair();
      }
    },
  };
}
