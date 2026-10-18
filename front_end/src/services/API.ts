import axios from "axios";

// Agora o aplicativo aponta para o servidor de produção na nuvem!
const API_URL = "https://litro-de-ouro-app.onrender.com";

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Interceptor para adicionar automaticamente o token JWT a todas as requisições futuras
api.interceptors.request.use(
  async (config) => {
    // Em breve, vamos buscar o token guardado no telemóvel aqui
    // const token = await SecureStore.getItemAsync('jwt_token');
    // if (token) {
    //   config.headers.Authorization = `Bearer ${token}`;
    // }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  },
);
