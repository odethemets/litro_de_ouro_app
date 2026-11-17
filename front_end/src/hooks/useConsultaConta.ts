import { useFocusEffect } from "@react-navigation/native";
import { useCallback, useRef, useState } from "react";
import { useAuth } from "../contexts/AuthContext";

export function useConsultaConta<T>(
  carregar: (signal: AbortSignal) => Promise<T>,
  ativo = true,
) {
  const { userToken } = useAuth();

  const [estado, setEstado] = useState<{
    token: string | null;
    dados: T | null;
    loading: boolean;
    erro: boolean;
    revisao: number;
  }>({
    token: null,
    dados: null,
    loading: true,
    erro: false,
    revisao: -1,
  });

  const [revisao, setRevisao] = useState(0);
  const sequencia = useRef(0);

  useFocusEffect(
    useCallback(() => {
      if (!ativo || !userToken) return;

      const controller = new AbortController();
      const numero = ++sequencia.current;

      setEstado((atual) => ({
        token: userToken,
        dados: atual.token === userToken ? atual.dados : null,
        loading: true,
        erro: false,
        revisao,
      }));

      void carregar(controller.signal)
        .then((dados) => {
          if (!controller.signal.aborted && numero === sequencia.current) {
            setEstado({
              token: userToken,
              dados,
              loading: false,
              erro: false,
              revisao,
            });
          }
        })
        .catch(() => {
          if (!controller.signal.aborted && numero === sequencia.current) {
            setEstado((atual) => ({
              ...atual,
              loading: false,
              erro: true,
            }));
          }
        });

      return () => {
        controller.abort();
      };
    }, [ativo, userToken, carregar, revisao]),
  );

  const atual = estado.token === userToken && Boolean(userToken);

  return {
    dados: atual ? estado.dados : null,
    loading: !atual || estado.loading || estado.revisao !== revisao,
    erro: atual && estado.revisao === revisao && estado.erro,
    atualizar: () => setRevisao((value) => value + 1),
  };
}
