import axios from 'axios';

// DICA CRÍTICA: Se for rodar no navegador (Web) ou no Simulador iOS, "localhost" funciona perfeitamente.
// Porém, se for testar no aplicativo Expo Go num telemóvel físico (Android/iOS) ou Emulador Android, 
// o telemóvel não entenderá "localhost". Terá de trocar pelo IP local da sua máquina (ex: http://192.168.1.15:5000).
const API_URL = 'http://localhost:5000'; 

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
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
  }
);