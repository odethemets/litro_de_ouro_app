import {
    RecordingPresets,
    requestRecordingPermissionsAsync,
    setAudioModeAsync,
    useAudioRecorder,
} from "expo-audio";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { AppState, Platform } from "react-native";

import { mensagemErroBusca } from "../services/assistente";
import {
    criarCicloBuscaVoz,
    type EstadoBuscaVoz,
    type GravacaoVoz,
} from "../services/cicloBuscaVoz";
import { transcreverVoz } from "../services/transcricaoVoz";

interface Opcoes {
  token: string;
  aoTexto(texto: string): void;
  aoErro(mensagem: string): void;
}

interface NavegadorAudio {
  isSecureContext?: boolean;
  MediaRecorder?: {
    isTypeSupported?(tipo: string): boolean;
  };
  navigator?: {
    mediaDevices?: {
      getUserMedia?: unknown;
    };
  };
}

let capturaAtual: symbol | null = null;

const semAssinatura = () => () => {};

function microfoneDisponivelNoCliente(): boolean {
  if (Platform.OS !== "web") return true;

  const ambiente = globalThis as unknown as NavegadorAudio;

  return Boolean(
    ambiente.isSecureContext &&
      ambiente.MediaRecorder &&
      typeof ambiente.navigator?.mediaDevices?.getUserMedia === "function",
  );
}

class FalhaMicrofone extends Error {}

export function useBuscaVoz({ token, aoTexto, aoErro }: Opcoes) {
  const opcoes = useMemo(() => {
    if (Platform.OS !== "web") {
      return RecordingPresets.HIGH_QUALITY;
    }

    const ambiente = globalThis as unknown as NavegadorAudio;

    const mimeType =
      [
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/mp4",
        "audio/ogg;codecs=opus",
        "audio/ogg",
      ].find((tipo) => ambiente.MediaRecorder?.isTypeSupported?.(tipo)) ??
      "audio/webm";

    return {
      ...RecordingPresets.HIGH_QUALITY,
      web: {
        ...RecordingPresets.HIGH_QUALITY.web,
        mimeType,
      },
    };
  }, []);

  const gravador = useAudioRecorder(opcoes);

  const [registroEstado, definirRegistroEstado] = useState<{
    gravador: typeof gravador;
    token: string;
    valor: EstadoBuscaVoz;
  }>({ gravador, token, valor: "parado" });

  const estado: EstadoBuscaVoz =
    registroEstado.gravador === gravador && registroEstado.token === token
      ? registroEstado.valor
      : "parado";
  const disponivel = useSyncExternalStore(
    semAssinatura,
    microfoneDisponivelNoCliente,
    () => Platform.OS !== "web",
  );

  const callbacks = useRef({ aoTexto, aoErro });
  useEffect(() => {
    callbacks.current = { aoTexto, aoErro };
  }, [aoTexto, aoErro]);

  const fase = useRef<EstadoBuscaVoz>("parado");
  const controle = useRef<ReturnType<typeof criarCicloBuscaVoz> | null>(null);

  useEffect(() => {

    async function capturar(signal: AbortSignal): Promise<GravacaoVoz> {
      if (capturaAtual) {
        throw new FalhaMicrofone(
          "O microfone está em uso. Aguarde a gravação terminar.",
        );
      }

      const dono = Symbol("busca-voz");
      capturaAtual = dono;

      let iniciou = false;
      let preparou = false;
      let modo = false;
      let uri = "";
      let parada: Promise<void> | null = null;
      let descarte: Promise<void> | null = null;

      function conferir() {
        if (signal.aborted) {
          throw new FalhaMicrofone("Gravação cancelada.");
        }
      }

      async function restaurar() {
        if (capturaAtual !== dono) return;

        try {
          if (modo && Platform.OS !== "web") {
            await setAudioModeAsync({
              allowsRecording: false,
            });
          }
        } finally {
          modo = false;

          if (capturaAtual === dono) {
            capturaAtual = null;
          }
        }
      }

      function pararHardware() {
        if (!parada) {
          parada = (async () => {
            try {
              if (iniciou || preparou) {
                try {
                  await gravador.stop();
                } catch (falha) {
                  // O limite nativo pode já ter finalizado o arquivo.
                  if (gravador.isRecording || !gravador.uri) {
                    throw falha;
                  }
                }

                iniciou = false;
              }

              uri = gravador.uri ?? "";
            } finally {
              await restaurar();
            }
          })();
        }

        return parada;
      }

      async function parar() {
        await pararHardware();

        if (!uri) {
          throw new Error("Não foi possível obter a gravação.");
        }

        return { uri };
      }

      function descartar() {
        if (!descarte) {
          descarte = (async () => {
            try {
              if (iniciou || preparou || parada) {
                await pararHardware();
              }
            } catch {
              try {
                gravador.release();
              } catch {
                // O SDK pode já ter liberado o gravador.
              }
            } finally {
              try {
                uri = uri || gravador.uri || "";
              } catch {
                // Um gravador liberado pode não expor mais a URI.
              }

              try {
                await restaurar();
              } catch {
                // A sessão de áudio pode já ter sido encerrada.
              }

              try {
                if (uri && Platform.OS === "web" && uri.startsWith("blob:")) {
                  URL.revokeObjectURL(uri);
                } else if (uri && Platform.OS !== "web") {
                  const { File } = await import("expo-file-system");

                  const arquivo = new File(uri);
                  if (arquivo.exists) arquivo.delete();
                }
              } catch {
                // A limpeza do cache não bloqueia o encerramento.
              }
            }
          })();
        }

        return descarte;
      }

      try {
        conferir();

        const permissao = await requestRecordingPermissionsAsync();

        conferir();

        if (!permissao.granted) {
          throw new FalhaMicrofone(
            "Permita o microfone para falar ou digite sua busca.",
          );
        }

        if (Platform.OS !== "web") {
          await setAudioModeAsync({
            allowsRecording: true,
            playsInSilentMode: true,
          });

          modo = true;
          conferir();
        }

        preparou = true;
        await gravador.prepareToRecordAsync();
        conferir();

        gravador.record({ forDuration: 30 });
        iniciou = true;

        return { parar, descartar };
      } catch (falha) {
        await descartar();

        if (falha instanceof FalhaMicrofone) throw falha;

        throw new Error(
          "Não foi possível preparar o microfone. Confira a permissão ou digite.",
        );
      }
    }

    const ciclo = criarCicloBuscaVoz({
      capturar,
      transcrever: (audio, signal) => transcreverVoz(audio.uri, token, signal),
      onEstado: (valor) => {
        fase.current = valor;
        definirRegistroEstado({ gravador, token, valor });
      },
      onTexto: (texto) => callbacks.current.aoTexto(texto),
      onErro: (mensagem) => callbacks.current.aoErro(mensagem),
      mensagemErro: mensagemErroBusca,
    });

    controle.current = ciclo;
    fase.current = "parado";

    const observador = AppState.addEventListener("change", (valor) => {
      if (
        valor === "background" ||
        (valor === "inactive" && fase.current === "ouvindo")
      ) {
        void ciclo.cancelar();
      }
    });

    return () => {
      observador.remove();

      if (controle.current === ciclo) {
        controle.current = null;
      }

      void ciclo.descartar();
    };
  }, [gravador, token]);

  return {
    estado,
    disponivel,
    descricao:
      "O áudio será enviado ao serviço de IA para transcrição. Limite de 30 segundos.",
    emAndamento: () => controle.current?.emAndamento() ?? false,
    iniciar: () => {
      void controle.current?.iniciar();
    },
    parar: () => {
      void controle.current?.parar();
    },
    cancelar: () => {
      void controle.current?.cancelar();
    },
  };
}
