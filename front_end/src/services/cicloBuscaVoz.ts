export type EstadoBuscaVoz =
  | "parado"
  | "preparando"
  | "ouvindo"
  | "transcrevendo"
  | "cancelando";

export interface AudioBuscaVoz {
  uri: string;
}

export interface GravacaoVoz {
  parar(): Promise<AudioBuscaVoz>;
  descartar(): Promise<void>;
}

interface DependenciasVoz {
  capturar(signal: AbortSignal): Promise<GravacaoVoz>;
  transcrever(audio: AudioBuscaVoz, signal: AbortSignal): Promise<string>;
  onEstado(estado: EstadoBuscaVoz): void;
  onTexto(texto: string): void;
  onErro(mensagem: string): void;
  mensagemErro?(erro: unknown): string;
  agendar?(acao: () => void, ms: number): () => void;
}

interface Sessao {
  cancelado: boolean;
  parando: boolean;
  gravacao: GravacaoVoz | null;
  limparTempo: (() => void) | null;
  liberacao: Promise<void> | null;
  abort: AbortController;
}

export function criarCicloBuscaVoz(deps: DependenciasVoz) {
  let atual: Sessao | null = null;
  let descartado = false;

  const agendar =
    deps.agendar ||
    ((acao: () => void, ms: number) => {
      const id = setTimeout(acao, ms);
      return () => clearTimeout(id);
    });

  const vigente = (s: Sessao) => atual === s && !s.cancelado && !descartado;

  function estado(valor: EstadoBuscaVoz) {
    if (!descartado) deps.onEstado(valor);
  }

  function erro(s: Sessao, falha: unknown, padrao: string) {
    if (!vigente(s)) return;

    const mensagem =
      falha == null ? padrao : deps.mensagemErro?.(falha) || padrao;

    deps.onErro(mensagem);
  }

  async function liberar(s: Sessao) {
    s.limparTempo?.();
    s.limparTempo = null;

    const gravacao = s.gravacao;
    if (!gravacao) return;

    if (!s.liberacao) {
      s.liberacao = Promise.resolve()
        .then(() => gravacao.descartar())
        .catch(() => undefined);
    }

    await s.liberacao;
  }

  function finalizar(s: Sessao) {
    if (atual !== s) return;

    s.limparTempo?.();
    atual = null;
    estado("parado");
  }

  async function iniciar() {
    if (descartado || atual) return false;

    const s: Sessao = {
      cancelado: false,
      parando: false,
      gravacao: null,
      limparTempo: null,
      liberacao: null,
      abort: new AbortController(),
    };

    atual = s;
    estado("preparando");

    try {
      s.gravacao = await deps.capturar(s.abort.signal);

      if (!vigente(s)) {
        await liberar(s);
        finalizar(s);
        return false;
      }

      s.limparTempo = agendar(() => {
        if (vigente(s)) void parar();
      }, 30000);

      estado("ouvindo");
      return true;
    } catch (falha) {
      erro(
        s,
        falha,
        "Não foi possível iniciar o microfone. Confira a permissão ou digite.",
      );
      await liberar(s);
      finalizar(s);
      return false;
    }
  }

  async function parar() {
    const s = atual;
    const gravacao = s?.gravacao;

    if (!s || !vigente(s) || !gravacao || s.parando) {
      return false;
    }

    s.parando = true;
    s.limparTempo?.();
    s.limparTempo = null;
    estado("transcrevendo");

    try {
      const audio = await gravacao.parar();
      if (!vigente(s)) return false;

      const bruto = await deps.transcrever(audio, s.abort.signal);
      if (!vigente(s)) return false;

      const texto = typeof bruto === "string" ? bruto.trim() : "";

      if (!texto || texto.length > 500) {
        erro(s, null, "Não recebemos uma fala válida de até 500 caracteres.");
        return false;
      }

      deps.onTexto(texto);
      return true;
    } catch (falha) {
      erro(
        s,
        falha,
        "Não foi possível transcrever a fala. Tente novamente ou digite.",
      );
      return false;
    } finally {
      await liberar(s);
      finalizar(s);
    }
  }

  async function cancelar() {
    const s = atual;
    if (!s) return;

    s.cancelado = true;
    s.abort.abort();
    estado("cancelando");

    await liberar(s);

    // Se a permissão ainda estiver pendente, iniciar() fará a limpeza.
    if (s.gravacao) finalizar(s);
  }

  async function descartar() {
    descartado = true;
    await cancelar();
  }

  return {
    iniciar,
    parar,
    cancelar,
    descartar,
    emAndamento: () => atual !== null,
  };
}
