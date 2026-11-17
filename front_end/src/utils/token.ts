import { armazenamentoSessao, lerTokenAtivo } from "../services/sessao";

// Compatibilidade com imports antigos, usando o armazenamento centralizado.
export const saveToken = armazenamentoSessao.gravar;
export const getToken = async () => lerTokenAtivo();
export const removeToken = armazenamentoSessao.remover;
