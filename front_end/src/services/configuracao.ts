const valor = process.env.EXPO_PUBLIC_API_URL?.trim();

if (!valor) {
  throw new Error("Configure EXPO_PUBLIC_API_URL em front_end/.env.local.");
}

const url = new URL(valor);

if (
  url.username ||
  url.password ||
  url.search ||
  url.hash ||
  (url.protocol !== "https:" && !(__DEV__ && url.protocol === "http:"))
) {
  throw new Error(
    "A URL da API deve usar HTTPS, sem credenciais ou parâmetros. HTTP somente em desenvolvimento.",
  );
}

export const API_URL = url.toString().replace(/\/+$/, "");

export function chaveDaSessao(apiUrl: string): string {
  return (
    "ldo.token.v2." +
    Array.from(apiUrl)
      .map((c) => c.charCodeAt(0).toString(16).padStart(2, "0"))
      .join("")
  );
}
