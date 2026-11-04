// front_end/src/services/API.ts

import AsyncStorage from "@react-native-async-storage/async-storage";
import axios, { AxiosHeaders } from "axios";

// O Expo incorpora esta variável ao iniciar ou gerar o aplicativo.
// Ela deve conter apenas a URL do backend.
const backendUrl = process.env.EXPO_PUBLIC_API_URL?.trim();

if (!backendUrl) {
  throw new Error(
    "Configure EXPO_PUBLIC_API_URL no arquivo front_end/.env.local.",
  );
}

// Confere o endereço antes de criar o cliente HTTP.
const endereco = new URL(backendUrl);

const protocoloPermitido =
  endereco.protocol === "https:" || (__DEV__ && endereco.protocol === "http:");

if (
  !protocoloPermitido ||
  endereco.username ||
  endereco.password ||
  endereco.search ||
  endereco.hash
) {
  throw new Error(
    "EXPO_PUBLIC_API_URL deve usar HTTPS, sem credenciais, parâmetros ou fragmentos. HTTP é permitido somente em desenvolvimento.",
  );
}

export const api = axios.create({
  // Agora utiliza efetivamente o endereço definido no ambiente.
  baseURL: backendUrl.replace(/\/+$/, ""),

  timeout: 15000,

  headers: {
    "Content-Type": "application/json",
    Accept: "application/json",
  },
});

// =========================================================
// INCLUI O TOKEN NAS REQUISIÇÕES
// =========================================================

api.interceptors.request.use(
  async (config) => {
    try {
      // Mantém a chave utilizada pelo AuthContext existente.
      const token = await AsyncStorage.getItem("@LitroDeOuro:token");

      const headers = AxiosHeaders.from(config.headers);

      // Preserva um cabeçalho informado explicitamente pela chamada.
      if (token && !headers.has("Authorization")) {
        headers.set("Authorization", `Bearer ${token}`);
      }

      config.headers = headers;

      return config;
    } catch (erro: unknown) {
      // Evita imprimir objetos que possam conter dados sensíveis.
      console.warn("[API] Não foi possível recuperar a sessão salva.");

      return Promise.reject(erro);
    }
  },
  (erro: unknown) => Promise.reject(erro),
);

// =========================================================
// TRATAMENTO DAS RESPOSTAS
// =========================================================

api.interceptors.response.use(
  (response) => response,

  (erro: unknown) => {
    if (axios.isAxiosError(erro)) {
      const caminho = (erro.config?.url ?? "")
        .split("?")[0]
        .replace(/\/+$/, "");

      const requisicaoDeLogin = caminho.endsWith("/auth/login");

      if (erro.response?.status === 401 && !requisicaoDeLogin) {
        console.warn("[API] Sessão expirada ou token rejeitado.");
      }

      if (erro.code === "ECONNABORTED" || erro.code === "ETIMEDOUT") {
        console.warn("[API] O backend não respondeu dentro do tempo limite.");
      } else if (!erro.response) {
        console.warn("[API] Não foi possível obter uma resposta do backend.");
      }
    }

    // A tela continua recebendo o erro para mostrar sua mensagem.
    return Promise.reject(erro);
  },
);
