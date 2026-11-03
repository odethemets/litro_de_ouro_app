// src/services/historicoVistos.ts
import AsyncStorage from "@react-native-async-storage/async-storage";

export interface PostoVisto {
  id: number;
  nome: string;
  endereco: string;
  dataVisualizacao: string;
}

const STORAGE_KEY = "@LitroDeOuro:vistos";

export async function registrarPostoVisto(posto: {
  id: number;
  nome: string;
  endereco: string;
}) {
  try {
    const atualRaw = await AsyncStorage.getItem(STORAGE_KEY);
    let lista: PostoVisto[] = atualRaw ? JSON.parse(atualRaw) : [];

    // Remove duplicados anteriores
    lista = lista.filter((item) => item.id !== posto.id);

    // Adiciona o novo no início
    lista.unshift({
      id: posto.id,
      nome: posto.nome,
      endereco: posto.endereco,
      dataVisualizacao: new Date().toLocaleDateString("pt-BR"),
    });

    // Mantém no máximo 20 postos recentemente vistos
    if (lista.length > 20) lista = lista.slice(0, 20);

    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(lista));
  } catch (error) {
    console.error("Erro ao guardar posto visto:", error);
  }
}

export async function obterPostosVistos(): Promise<PostoVisto[]> {
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (error) {
    console.error("Erro ao ler postos vistos:", error);
    return [];
  }
}
