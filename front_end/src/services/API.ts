import axios from "axios";
import { getToken } from "../utils/token";

export const api = axios.create({
  baseURL: "https://litro-de-ouro-app.onrender.com",
});

// Interceptor: Injeta automaticamente o token em todas as chamadas
api.interceptors.request.use(
  async (config) => {
    const token = await getToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  },
);
