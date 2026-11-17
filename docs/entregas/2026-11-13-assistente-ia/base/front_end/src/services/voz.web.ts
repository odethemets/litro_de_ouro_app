interface Reconhecimento {
  lang: string;
  interimResults: boolean;
  continuous: boolean;

  onresult:
    | ((evento: {
        results: ArrayLike<ArrayLike<{ transcript: string }>>;
      }) => void)
    | null;

  onerror: ((evento: { error?: string }) => void) | null;

  onend: (() => void) | null;

  start(): void;
  abort(): void;
}

function construtor() {
  const navegador = globalThis as unknown as {
    SpeechRecognition?: new () => Reconhecimento;
    webkitSpeechRecognition?: new () => Reconhecimento;
    isSecureContext?: boolean;
  };

  return navegador.isSecureContext
    ? (navegador.SpeechRecognition ?? navegador.webkitSpeechRecognition)
    : undefined;
}

export const vozDisponivel = () => Boolean(construtor());

export function iniciarVoz(
  texto: (texto: string) => void,
  fim: () => void,
  erro: (mensagem: string) => void,
): () => void {
  const Criar = construtor();

  if (!Criar) {
    throw new Error(
      "Reconhecimento de voz indisponível. " +
        "Use o ditado do teclado ou digite.",
    );
  }

  const voz = new Criar();

  let encerrado = false;
  let tempo: ReturnType<typeof setTimeout> | null = null;

  const encerrar = () => {
    if (encerrado) return;

    encerrado = true;

    if (tempo !== null) clearTimeout(tempo);

    voz.onresult = null;
    voz.onerror = null;
    voz.onend = null;

    try {
      voz.abort();
    } catch {
      // O navegador pode já ter encerrado.
    }

    fim();
  };

  voz.lang = "pt-BR";
  voz.interimResults = false;
  voz.continuous = false;

  voz.onresult = (evento) => {
    if (encerrado) return;

    const resultado = evento.results[0]?.[0]?.transcript;

    if (typeof resultado === "string" && resultado.trim()) {
      texto(resultado.trim());
    } else {
      erro("Nenhuma fala foi reconhecida. " + "Tente novamente ou digite.");
    }

    encerrar();
  };

  voz.onerror = (evento) => {
    if (encerrado) return;

    erro(
      evento.error === "not-allowed" || evento.error === "service-not-allowed"
        ? "Permita o microfone no navegador ou digite sua busca."
        : "Não foi possível reconhecer a fala. " + "Tente novamente ou digite.",
    );

    encerrar();
  };

  voz.onend = encerrar;

  tempo = setTimeout(() => {
    if (encerrado) return;

    erro("O tempo de escuta terminou. " + "Tente novamente ou digite.");

    encerrar();
  }, 12000);

  try {
    voz.start();
  } catch {
    encerrar();

    throw new Error(
      "Não foi possível iniciar o microfone. " +
        "Confira a permissão ou digite.",
    );
  }

  return encerrar;
}
