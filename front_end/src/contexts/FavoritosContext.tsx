import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useRef,
    useState,
    type ReactNode,
} from "react";

import { api } from "../services/API";
import {
    favoritosValidos,
    type FavoritosConta,
} from "../services/participacao";
import { useAuth } from "./AuthContext";

interface ContextoFavoritos {
  ids: ReadonlySet<number>;
  confirmado: boolean;
  carregando: boolean;
  salvando: boolean;
  erro: string;
  atualizar(): void;
  alternar(id: number): Promise<void>;
}

const Contexto = createContext<ContextoFavoritos | null>(null);

export function FavoritosProvider({ children }: { children: ReactNode }) {
  const { status, userToken } = useAuth();
  const token = status === "AUTHENTICATED" ? userToken : null;

  return (
    <FavoritosDaSessao key={token ?? "visitante"} token={token}>
      {children}
    </FavoritosDaSessao>
  );
}

function FavoritosDaSessao({
  token,
  children,
}: {
  token: string | null;
  children: ReactNode;
}) {
  const [dados, setDados] = useState<FavoritosConta | null>(null);
  const [confirmado, setConfirmado] = useState(false);
  const [carregando, setCarregando] = useState(Boolean(token));
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");

  const pedido = useRef<{
    controller: AbortController;
    escrita: boolean;
  } | null>(null);

  const atualizar = useCallback(() => {
    if (!token || pedido.current?.escrita) return;

    pedido.current?.controller.abort();

    const atual = {
      controller: new AbortController(),
      escrita: false,
    };

    pedido.current = atual;

    setCarregando(true);
    setConfirmado(false);
    setErro("");

    void api
      .get("/favoritos", {
        signal: atual.controller.signal,
        headers: {
          Authorization: "Bearer " + token,
        },
      })
      .then(({ data }) => {
        const recebidos = favoritosValidos(data);

        if (!atual.controller.signal.aborted) {
          setDados(recebidos);
          setConfirmado(true);
        }
      })
      .catch(() => {
        if (!atual.controller.signal.aborted) {
          setErro(
            "Não foi possível atualizar seus favoritos. Tente novamente.",
          );
        }
      })
      .finally(() => {
        if (!atual.controller.signal.aborted) {
          setCarregando(false);
        }

        if (pedido.current === atual) {
          pedido.current = null;
        }
      });
  }, [token]);

  useEffect(() => {
    atualizar();

    return () => {
      pedido.current?.controller.abort();
    };
  }, [atualizar]);

  const alternar = useCallback(
    async (id: number) => {
      if (
        !token ||
        !confirmado ||
        !dados ||
        pedido.current ||
        !Number.isSafeInteger(id) ||
        id <= 0
      ) {
        return;
      }

      const atual = {
        controller: new AbortController(),
        escrita: true,
      };

      pedido.current = atual;
      setSalvando(true);
      setErro("");

      const config = {
        signal: atual.controller.signal,
        headers: {
          Authorization: "Bearer " + token,
        },
      };

      try {
        const resposta = dados.postos.includes(id)
          ? await api.delete("/favoritos/postos/" + id, config)
          : await api.put("/favoritos/postos/" + id, {}, config);

        const recebidos = favoritosValidos(resposta.data);

        if (!atual.controller.signal.aborted) {
          setDados(recebidos);
        }
      } catch {
        if (!atual.controller.signal.aborted) {
          setConfirmado(false);

          setErro(
            "Não foi possível confirmar a alteração. Atualize os favoritos antes de tentar novamente.",
          );
        }
      } finally {
        if (!atual.controller.signal.aborted) {
          setSalvando(false);
        }

        if (pedido.current === atual) {
          pedido.current = null;
        }
      }
    },
    [token, confirmado, dados],
  );

  const ids = useMemo(() => new Set(dados?.postos ?? []), [dados]);

  const value = useMemo(
    () => ({
      ids,
      confirmado,
      carregando,
      salvando,
      erro,
      atualizar,
      alternar,
    }),
    [ids, confirmado, carregando, salvando, erro, atualizar, alternar],
  );

  return <Contexto.Provider value={value}>{children}</Contexto.Provider>;
}

export function useFavoritos() {
  const contexto = useContext(Contexto);

  if (!contexto) {
    throw new Error("FavoritosProvider ausente na navegação.");
  }

  return contexto;
}
