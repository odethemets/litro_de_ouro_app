import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";

import { api } from "../services/API";
import { validarPerfil } from "../services/contratoAuth";
import {
  criarControleSessao,
  type DestinoAuth,
  type EstadoSessao,
} from "../services/controleSessao";
import {
  aoRejeitarToken,
  armazenamentoSessao,
  definirTokenAtivo,
} from "../services/sessao";

interface AuthContextData extends EstadoSessao {
  token: string | null;
  isGuest: boolean;
  isLoadingAuth: boolean;
  signIn(token: string): Promise<void>;
  signOut(): Promise<void>;
  enterGuest(): void;
  openAuth(destino?: DestinoAuth): void;
  retryInitialization(): Promise<void>;
}

export const AuthContext = createContext<AuthContextData>(
  {} as AuthContextData,
);

export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [controle] = useState(() =>
    criarControleSessao({
      armazenamento: armazenamentoSessao,
      publicarToken: definirTokenAtivo,

      validar: async (token) => {
        const resposta = await api.get("/auth/perfil", {
          headers: {
            Authorization: "Bearer " + token,
          },
          timeout: 10000,
        });

        return validarPerfil(resposta.data);
      },
    }),
  );

  const estado = useSyncExternalStore(
    controle.subscribe,
    controle.getSnapshot,
    controle.getSnapshot,
  );

  useEffect(() => {
    const cancelar = aoRejeitarToken(controle.rejeitar);
    void controle.inicializar();

    return () => {
      cancelar();
      controle.cancelar();
    };
  }, [controle]);

  const valor = useMemo(
    () => ({
      ...estado,
      token: estado.userToken,
      isGuest: estado.status === "GUEST",
      isLoadingAuth: estado.status === "INITIALIZING",
      signIn: controle.entrar,
      signOut: controle.sair,
      enterGuest: controle.visitante,
      openAuth: controle.abrirEntrada,
      retryInitialization: controle.inicializar,
    }),
    [controle, estado],
  );

  return <AuthContext.Provider value={valor}>{children}</AuthContext.Provider>;
}
