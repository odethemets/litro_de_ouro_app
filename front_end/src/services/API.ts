import axios from "axios";
import { Platform } from "react-native";
import { getToken } from "../utils/token";

const API_URL =
  Platform.OS === "web"
    ? "https://litro-de-ouro-app.onrender.com"
    : "https://litro-de-ouro-app.onrender.com";

export const api = axios.create({
  baseURL: API_URL,
  timeout: 15000, // Previne que o ecrã fique congelado se o Render estiver a dormir
});

// INTERCEPTOR: Injeta o Token JWT automaticamente em TODAS as requisições
api.interceptors.request.use(async (config) => {
  const token = await getToken();
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});
