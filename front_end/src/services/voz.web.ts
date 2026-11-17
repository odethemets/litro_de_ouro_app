interface Reconhecimento {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((evento: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: ((evento: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  abort(): void;
}

// A captura direta exige suporte do navegador e contexto seguro (HTTPS ou localhost).
function construtor() {
  const navegador = globalThis as unknown as {
    SpeechRecognition?: new () => Reconhecimento;
    webkitSpeechRecognition?: new () => Reconhecimento;
    isSecureContext?: boolean;
  };
  return navegador.isSecureContext
    ? navegador.SpeechRecognition ?? navegador.webkitSpeechRecognition : undefined;
}

export const vozDisponivel = () => Boolean(construtor());

// Entrega uma transcrição revisável; a função retornada encerra a escuta uma só vez.
export function iniciarVoz(
  texto: (texto: string) => void,
  fim: () => void,
  erro: (mensagem: string) => void,
): () => void {
  const Criar = construtor();
  if (!Criar) throw new Error("Reconhecimento de voz indisponível. Use o ditado do teclado ou digite.");
  const voz = new Criar();
  let encerrado = false;
  let recebeuEvento = false;
  let tempo: ReturnType<typeof setTimeout> | null = null;

  // Remove handlers e temporizador antes de abortar, evitando callbacks duplicados.
  const encerrar = () => {
    if (encerrado) return;
    encerrado = true;
    if (tempo !== null) clearTimeout(tempo);
    voz.onresult = null;
    voz.onerror = null;
    voz.onend = null;
    try { voz.abort(); } catch { /* O navegador pode já ter encerrado. */ }
    fim();
  };

  voz.lang = "pt-BR";
  voz.interimResults = false;
  voz.continuous = false;
  voz.onresult = (evento) => {
    if (encerrado) return;
    recebeuEvento = true;
    try {
      const resultado = evento.results[0]?.[0]?.transcript;
      if (typeof resultado !== "string" || !resultado.trim()) {
        erro("Nenhuma fala foi reconhecida. Tente novamente ou digite.");
      } else if (resultado.trim().length > 500) {
        erro("A fala ficou muito longa. Faça uma busca de até 500 caracteres.");
      } else texto(resultado.trim());
    } finally { encerrar(); }
  };
  voz.onerror = (evento) => {
    if (encerrado) return;
    recebeuEvento = true;
    try {
      erro(evento.error === "not-allowed" || evento.error === "service-not-allowed"
        ? "Permita o microfone no navegador ou digite sua busca."
        : evento.error === "no-speech"
          ? "Nenhuma fala foi reconhecida. Tente novamente ou digite."
          : "Não foi possível reconhecer a fala. Tente novamente ou digite.");
    } finally { encerrar(); }
  };
  voz.onend = () => {
    if (encerrado) return;
    try {
      if (!recebeuEvento) erro("A escuta terminou sem reconhecer uma fala. Tente novamente ou digite.");
    } finally { encerrar(); }
  };
  tempo = setTimeout(() => {
    if (encerrado) return;
    try { erro("O tempo de escuta terminou. Tente novamente ou digite."); }
    finally { encerrar(); }
  }, 12000);
  try { voz.start(); }
  catch {
    encerrar();
    throw new Error("Não foi possível iniciar o microfone. Confira a permissão ou digite.");
  }
  return encerrar;
}
