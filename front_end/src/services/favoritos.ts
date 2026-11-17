import AsyncStorage from "@react-native-async-storage/async-storage";
import { API_URL } from "./configuracao";

export function chaveFavoritos(email: string, apiUrl = API_URL) {
  if (!email.trim()) {
    throw new Error("Conta necessária para acessar favoritos.");
  }

  return (
    "ldo.favoritos.v1." +
    encodeURIComponent(apiUrl) +
    "::" +
    encodeURIComponent(email.trim().toLowerCase())
  );
}

export function decodificarFavoritos(raw: string | null): number[] {
  if (raw === null) return [];

  const value: unknown = JSON.parse(raw);

  if (
    !Array.isArray(value) ||
    value.some((id) => !Number.isSafeInteger(id) || id <= 0)
  ) {
    throw new Error("Favoritos salvos em formato inválido.");
  }

  return [...new Set(value as number[])];
}

export async function lerFavoritos(chave: string) {
  return decodificarFavoritos(await AsyncStorage.getItem(chave));
}

export async function gravarFavoritos(chave: string, ids: number[]) {
  const validos = decodificarFavoritos(JSON.stringify(ids));

  await AsyncStorage.setItem(chave, JSON.stringify(validos));
}
