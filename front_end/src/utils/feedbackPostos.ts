// front_end/src/utils/feedbackPostos.ts

export interface MensagemAcao {
  tipo: "sucesso" | "erro" | "aviso" | "info";
  titulo: string;
  mensagem: string;
}

// Segue o limite do endpoint atual /postos/:id/precos.
// Valida o texto inteiro, evitando aceitar valores como "5,89abc".
export function normalizarPreco(texto: string): number | null {
  const valor = texto.trim();

  if (!/^\d+(?:[.,]\d{1,2})?$/.test(valor)) {
    return null;
  }

  const numero = Number(valor.replace(",", "."));

  return Number.isFinite(numero) && numero > 0 && numero <= 20 ? numero : null;
}

export function falhaCadastroPreco(erro: unknown): MensagemAcao {
  const resposta = (
    erro as {
      response?: {
        status?: number;
        data?: {
          error?: unknown;
        };
      };
    } | null
  )?.response;

  if (resposta && typeof resposta.data?.error === "string") {
    return {
      tipo: "erro",
      titulo: "Não foi possível cadastrar",
      mensagem: resposta.data.error,
    };
  }

  // Sem resposta, a gravação pode ter ocorrido antes da conexão cair.
  return {
    tipo: "aviso",
    titulo: "Cadastro não confirmado",
    mensagem:
      "Não recebemos a confirmação do servidor. Confira os preços deste posto antes de tentar enviar novamente.",
  };
}
