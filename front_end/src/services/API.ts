import { AxiosHeaders, create, isAxiosError } from "axios";
import { API_URL } from "./configuracao";
import { sessaoRejeitada } from "./contratoAuth";
import { lerTokenAtivo, rejeitarToken } from "./sessao";

export const api = create({
  baseURL: API_URL,
  timeout: 15000,
  headers: {
    "Content-Type": "application/json",
    Accept: "application/json",
  },
});

api.interceptors.request.use((config) => {
  const token = lerTokenAtivo();
  const headers = AxiosHeaders.from(config.headers);

  const caminho = (config.url ?? "").split("?")[0].replace(/\/+$/, "");

  if (
    token &&
    !headers.has("Authorization") &&
    (!caminho.startsWith("/auth/") || caminho === "/auth/perfil")
  ) {
    headers.set("Authorization", "Bearer " + token);
  }

  config.headers = headers;
  return config;
});

api.interceptors.response.use(
  (resposta) => resposta,
  (erro: unknown) => {
    if (isAxiosError(erro)) {
      const caminho = (erro.config?.url ?? "")
        .split("?")[0]
        .replace(/\/+$/, "");

      const auth = AxiosHeaders.from(erro.config?.headers).get("Authorization");

      const rejeitado =
        erro.response?.status === 401 ||
        (caminho === "/auth/perfil" && sessaoRejeitada(erro));

      if (
        rejeitado &&
        caminho !== "/auth/login" &&
        typeof auth === "string" &&
        auth.startsWith("Bearer ")
      ) {
        rejeitarToken(auth.slice(7));
      }
    }

    return Promise.reject(erro);
  },
);
