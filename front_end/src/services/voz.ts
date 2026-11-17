export const vozDisponivel = () => false;

export function iniciarVoz(
  _texto: (texto: string) => void,
  _fim: () => void,
  _erro: (mensagem: string) => void,
): () => void {
  throw new Error(
    "Use o ditado do teclado para falar sua busca neste aplicativo.",
  );
}
