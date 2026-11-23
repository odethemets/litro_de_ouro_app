import { Platform } from "react-native";
import { api } from "./API";

const MAX_AUDIO_BYTES = 2 * 1024 * 1024;

const EXTENSOES: Record<string, string> = {
  "audio/mp4": "m4a",
  "audio/webm": "webm",
  "audio/ogg": "ogg",
  "audio/wav": "wav",
};

function conferirCancelamento(signal: AbortSignal) {
  if (signal.aborted) {
    throw new Error("Transcrição cancelada.");
  }
}

export async function transcreverVoz(
  uri: string,
  token: string,
  signal: AbortSignal,
): Promise<string> {
  conferirCancelamento(signal);

  if (!token.trim()) {
    throw new Error("Entre novamente para usar a busca por voz.");
  }

  if (!uri.trim()) {
    throw new Error("A gravação de voz não foi encontrada.");
  }

  const formulario = new FormData();

  if (Platform.OS === "web") {
    const resposta = await fetch(uri, { signal });

    if (!resposta.ok) {
      throw new Error("Não foi possível ler a gravação.");
    }

    const audio = await resposta.blob();
    const tipo = audio.type.split(";")[0].trim().toLowerCase();
    const extensao = EXTENSOES[tipo];

    if (
      typeof extensao !== "string" ||
      !audio.size ||
      audio.size > MAX_AUDIO_BYTES
    ) {
      throw new Error(
        "A gravação está vazia, excede 2 MB ou usa um formato incompatível.",
      );
    }

    formulario.append("audio", audio, "busca." + extensao);
  } else {
    formulario.append("audio", {
      uri,
      type: "audio/mp4",
      name: "busca.m4a",
    } as unknown as Blob);
  }

  conferirCancelamento(signal);

  const { data } = await api.post("/ia/transcrever", formulario, {
    signal,
    timeout: 90000,
    headers: {
      Authorization: "Bearer " + token,
      "Content-Type": "multipart/form-data",
    },
  });

  conferirCancelamento(signal);

  const texto =
    data &&
    typeof data === "object" &&
    !Array.isArray(data) &&
    typeof data.texto === "string"
      ? data.texto.trim()
      : "";

  if (!texto || texto.length > 500) {
    throw new Error(
      "Não recebemos uma transcrição válida de até 500 caracteres.",
    );
  }

  return texto;
}
