import AsyncStorage from "@react-native-async-storage/async-storage";
import { validarVistos, type VistoPessoal } from "./atividadeConta";
import { API_URL } from "./configuracao";

export type PostoVisto = VistoPessoal;

export function chaveHistorico(usuarioId: number, apiUrl = API_URL) {
  if (!Number.isSafeInteger(usuarioId) || usuarioId <= 0) {
    throw new Error("Conta necessária para o histórico.");
  }

  return "ldo.vistos.v2." + encodeURIComponent(apiUrl) + ":" + usuarioId;
}

let fila: Promise<unknown> = Promise.resolve();

function serializar<T>(acao: () => Promise<T>): Promise<T> {
  const pedido = fila.then(acao);
  fila = pedido.catch(() => undefined);
  return pedido;
}

export async function registrarPostoVisto(
  posto: { id: number; nome: string; endereco: string },
  usuarioId?: number,
) {
  if (!usuarioId) return;

  const chave = chaveHistorico(usuarioId);

  return serializar(async () => {
    try {
      const atuais = validarVistos(await AsyncStorage.getItem(chave));

      const item = {
        ...posto,
        dataVisualizacao: new Date().toISOString(),
      };

      const atualizados = [
        item,
        ...atuais.filter((p) => p.id !== posto.id),
      ].slice(0, 20);

      await AsyncStorage.setItem(chave, JSON.stringify(atualizados));
    } catch {
      // Histórico opcional não bloqueia a consulta ao posto.
    }
  });
}

export function obterPostosVistos(usuarioId?: number): Promise<PostoVisto[]> {
  if (!usuarioId) return Promise.resolve([]);

  return serializar(async () =>
    validarVistos(await AsyncStorage.getItem(chaveHistorico(usuarioId))),
  );
}

export function limparPostosVistos(usuarioId: number) {
  return serializar(() => AsyncStorage.removeItem(chaveHistorico(usuarioId)));
}
