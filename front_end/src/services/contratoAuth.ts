export interface PerfilUsuario {
  id?: number;
  nome: string;
  email: string;
  plano: string;
  karma: number;
  membro_desde: string;
}

type FalhaHttp = {
  response?: {
    status?: number;
    data?: {
      code?: string;
      error?: string;
    };
  };
};

export function sessaoRejeitada(erro: unknown): boolean {
  const resposta = (erro as FalhaHttp | null)?.response;

  if (resposta?.status === 401) return true;
  if (resposta?.status !== 404) return false;

  // Apenas respostas específicas indicam conta removida.
  return (
    resposta.data?.code === "USER_NOT_FOUND" ||
    resposta.data?.code === "ACCOUNT_DELETED" ||
    resposta.data?.error === "Utilizador não encontrado."
  );
}

export function validarPerfil(dados: unknown): PerfilUsuario {
  const p = dados as Partial<PerfilUsuario> | null;

  if (
    !p ||
    (p.id !== undefined && (!Number.isSafeInteger(p.id) || p.id <= 0)) ||
    typeof p.nome !== "string" ||
    typeof p.email !== "string" ||
    typeof p.plano !== "string" ||
    typeof p.karma !== "number" ||
    !Number.isFinite(p.karma) ||
    typeof p.membro_desde !== "string"
  ) {
    throw new Error("A API não retornou um perfil válido.");
  }

  return p as PerfilUsuario;
}
