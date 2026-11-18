import * as Linking from "expo-linking";

// Aceita somente links públicos de resposta do Google Forms.
function lerUrlFormulario(valor?: string): string | null {
  if (!valor?.trim()) return null;

  try {
    const url = new URL(valor.trim());

    if (
      url.protocol !== "https:" ||
      url.username ||
      url.password ||
      url.port ||
      url.hash
    ) {
      return null;
    }

    const curto =
      url.hostname === "forms.gle" &&
      /^\/[A-Za-z0-9_-]+\/?$/.test(url.pathname);

    const completo =
      url.hostname === "docs.google.com" &&
      /^\/forms\/(?:u\/\d+\/)?d\/(?:e\/)?[A-Za-z0-9_-]+\/viewform\/?$/.test(
        url.pathname,
      );

    return curto || completo ? url.href : null;
  } catch {
    return null;
  }
}

export const FORMULARIO_AVALIACAO_URL = lerUrlFormulario(
  process.env.EXPO_PUBLIC_AVALIACAO_URL,
);

export async function abrirFormularioAvaliacao(): Promise<void> {
  if (!FORMULARIO_AVALIACAO_URL) {
    throw new Error("O formulário ainda não está disponível.");
  }

  await Linking.openURL(FORMULARIO_AVALIACAO_URL);
}
