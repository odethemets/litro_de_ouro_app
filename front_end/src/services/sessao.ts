import AsyncStorage from "@react-native-async-storage/async-storage";
import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";
import { API_URL, chaveDaSessao } from "./configuracao";

export const TOKEN_KEY = chaveDaSessao(API_URL);

let fila: Promise<unknown> = Promise.resolve();

function serializar<T>(acao: () => Promise<T>): Promise<T> {
  const resultado = fila.then(acao);
  fila = resultado.catch(() => undefined);
  return resultado;
}

export const armazenamentoSessao = {
  ler: () =>
    serializar(() =>
      Platform.OS === "web"
        ? AsyncStorage.getItem(TOKEN_KEY)
        : SecureStore.getItemAsync(TOKEN_KEY),
    ),

  gravar: (token: string) =>
    serializar(() =>
      Platform.OS === "web"
        ? AsyncStorage.setItem(TOKEN_KEY, token)
        : SecureStore.setItemAsync(TOKEN_KEY, token),
    ),

  remover: () =>
    serializar(() =>
      Platform.OS === "web"
        ? AsyncStorage.removeItem(TOKEN_KEY)
        : SecureStore.deleteItemAsync(TOKEN_KEY),
    ),
};

// Apenas o controlador publica uma sessão validada. Visitantes usam null.
let tokenAtivo: string | null = null;

const ouvintes = new Set<(token: string) => void>();

export function lerTokenAtivo() {
  return tokenAtivo;
}

export function definirTokenAtivo(token: string | null) {
  tokenAtivo = token;
}

export function aoRejeitarToken(ouvinte: (token: string) => void) {
  ouvintes.add(ouvinte);

  return () => {
    ouvintes.delete(ouvinte);
  };
}

export function rejeitarToken(token: string) {
  if (tokenAtivo !== token) return;

  tokenAtivo = null;
  ouvintes.forEach((ouvinte) => ouvinte(token));
}
