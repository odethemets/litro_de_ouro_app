// src/services/API.ts deixe API em maiúsculas para não confundir com a pasta services
import AsyncStorage from "@react-native-async-storage/async-storage";
import axios from "axios";

/**
 * CRÍTICO PARA AMBIENTE DE DESENVOLVIMENTO:
 * O emulador Android ou o telemóvel físico não compreendem "localhost" ou "127.0.0.1"
 * como sendo o seu computador. Eles assumem que "localhost" é o próprio aparelho mobile.
 * Substitua pelo Endereço IPv4 local da sua máquina (verifique no terminal com 'ipconfig').
 * Exemplo: '192.168.1.15'
 */
const IP_LOCAL_BACKEND = "192.168.1.8"; // <- ALTERE AQUI PARA O SEU IP
const PORTA_BACKEND = "5000"; // Porta padrão do Flask

export const api = axios.create({
  baseURL: `http://${IP_LOCAL_BACKEND}:${PORTA_BACKEND}`,
  timeout: 15000, // Timeout estendido para 15s para garantir leitura OCR do Gemini sem timeout prematuro
  headers: {
    "Content-Type": "application/json",
    Accept: "application/json",
  },
});

// ----------------------------------------------------------------------
// REQUEST INTERCEPTOR: Injeta o JWT antes da requisição sair do aparelho
// ----------------------------------------------------------------------
api.interceptors.request.use(
  async (config) => {
    try {
      // Busca o token de autenticação armazenado após o login
      const token = await AsyncStorage.getItem("@LitroDeOuro:token");

      if (token) {
        // Garante que o objeto headers existe antes de injetar
        config.headers = config.headers ?? {};
        config.headers.Authorization = `Bearer ${token}`;
      }

      return config;
    } catch (error) {
      console.error("[API] Erro ao recuperar o token do armazenamento:", error);
      return Promise.reject(error);
    }
  },
  (error) => {
    return Promise.reject(error);
  },
);

// ----------------------------------------------------------------------
// RESPONSE INTERCEPTOR: Analisa a resposta do backend antes de chegar ao Ecrã
// ----------------------------------------------------------------------
api.interceptors.response.use(
  (response) => {
    // Se a resposta for sucesso (2xx), passa os dados diretamente
    return response;
  },
  async (error) => {
    const requestUrl = error.config?.url || "";

    // Tratamento de perda de sessão (ignora a rota de login para permitir tratamento local de credenciais inválidas)
    if (
      error.response &&
      error.response.status === 401 &&
      !requestUrl.includes("/auth/login")
    ) {
      console.warn("[API] Sessão expirada ou token inválido (Erro 401).");

      // Futuramente: Implementar lógica de Refresh Token
      // ou limpar o AsyncStorage e disparar evento para a raiz forçar o ecrã de Login.
      // await AsyncStorage.removeItem('@LitroDeOuro:token');
    }

    // Tratamento de falhas de rede (Backend desligado ou IP errado)
    if (error.message === "Network Error") {
      console.error(
        "[API] Falha de comunicação. Verifique se o Flask está a correr e o IP está correto.",
      );
    }

    return Promise.reject(error);
  },
);
