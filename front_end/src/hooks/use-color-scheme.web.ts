import { useSyncExternalStore } from "react";
import { useColorScheme as useRNColorScheme } from "react-native";

const assinarHidratacao = () => () => {
  // Não há assinatura externa para remover.
};

const obterSnapshotCliente = () => true;
const obterSnapshotServidor = () => false;

export function useColorScheme() {
  const hidratado = useSyncExternalStore(
    assinarHidratacao,
    obterSnapshotCliente,
    obterSnapshotServidor,
  );

  const esquema = useRNColorScheme();

  return hidratado ? esquema : "light";
}
