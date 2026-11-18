import * as Location from "expo-location";
import { Platform } from "react-native";
import { PRECISAO_MAPA_MAX_M, PRECISAO_REGISTRO_MAX_M } from "./precisaoGps";

export type PerfilGps = "mapa" | "registro";

export const CENTRO_PADRAO = {
  lat: -7.115,
  lon: -34.861,
};

export type CodigoErroGps =
  | "CONTEXTO_INSEGURO"
  | "PERMISSAO_NEGADA"
  | "SERVICO_DESLIGADO"
  | "TIMEOUT"
  | "IMPRECISA"
  | "DESATUALIZADA"
  | "INDISPONIVEL";

export class ErroGps extends Error {
  readonly codigo: CodigoErroGps;

  constructor(codigo: CodigoErroGps, mensagem: string) {
    super(mensagem);
    this.name = "ErroGps";
    this.codigo = codigo;
  }
}

export interface PosicaoGps {
  latitude: number;
  longitude: number;
  precisaoM: number;
  obtidaEm: number;
  simulada: boolean;
}

export function validarPosicao(
  local: Location.LocationObject,
  perfil: PerfilGps,
  agora = Date.now(),
): PosicaoGps {
  const { latitude, longitude, accuracy } = local.coords;

  if (
    !Number.isFinite(latitude) ||
    Math.abs(latitude) > 90 ||
    !Number.isFinite(longitude) ||
    Math.abs(longitude) > 180 ||
    (latitude === 0 && longitude === 0)
  ) {
    throw new ErroGps(
      "INDISPONIVEL",
      "O dispositivo devolveu coordenadas inválidas.",
    );
  }

  if (
    !Number.isFinite(local.timestamp) ||
    local.timestamp > agora + 5000 ||
    agora - local.timestamp > (perfil === "registro" ? 15000 : 60000)
  ) {
    throw new ErroGps(
      "DESATUALIZADA",
      "A posição recebida está desatualizada. Atualize a localização.",
    );
  }

  const limite =
    perfil === "registro" ? PRECISAO_REGISTRO_MAX_M : PRECISAO_MAPA_MAX_M;
  if (
    typeof accuracy !== "number" ||
    !Number.isFinite(accuracy) ||
    accuracy < 0
  ) {
    throw new ErroGps(
      "IMPRECISA",
      "O dispositivo não informou uma precisão válida. Ative a localização precisa e tente novamente.",
    );
  }

  if (accuracy > limite) {
    throw new ErroGps(
      "IMPRECISA",
      `A precisão recebida é de aproximadamente ±${Math.ceil(accuracy)} m; o limite ${perfil === "registro" ? "para cadastrar preços" : "para localizar no mapa"} é ${limite} m. Ative a localização precisa e tente novamente.`,
    );
  }

  return {
    latitude,
    longitude,
    precisaoM: accuracy,
    obtidaEm: local.timestamp,
    simulada:
      (
        local as Location.LocationObject & {
          mocked?: boolean;
        }
      ).mocked === true,
  };
}

// A API do navegador pede a permissão durante a leitura, sem exigir Permissions API.
async function lerNavegador(perfil: PerfilGps): Promise<PosicaoGps> {
  if (typeof window !== "undefined" && window.isSecureContext === false) {
    throw new ErroGps(
      "CONTEXTO_INSEGURO",
      "Abra o aplicativo por HTTPS para usar a localização. No computador de desenvolvimento, localhost também é permitido.",
    );
  }

  if (typeof navigator === "undefined" || !navigator.geolocation) {
    throw new ErroGps(
      "INDISPONIVEL",
      "Este navegador não disponibilizou a localização. Abra o aplicativo em um navegador atualizado.",
    );
  }

  const local = await new Promise<Location.LocationObject>(
    (resolver, rejeitar) => {
      navigator.geolocation.getCurrentPosition(
        (posicao) =>
          resolver({ coords: posicao.coords, timestamp: posicao.timestamp }),
        (erro) => {
          const codigo =
            erro.code === 1
              ? "PERMISSAO_NEGADA"
              : erro.code === 3
                ? "TIMEOUT"
                : "INDISPONIVEL";
          const mensagem =
            erro.code === 1
              ? "Permita a localização para este site no navegador e nas configurações do sistema. Depois, tente novamente."
              : erro.code === 3
                ? "A localização demorou a responder. Ative a localização do dispositivo e tente novamente."
                : "O navegador não conseguiu determinar sua posição. Ative a localização do sistema e tente novamente.";
          rejeitar(new ErroGps(codigo, mensagem));
        },
        { enableHighAccuracy: true, maximumAge: 0, timeout: 20000 },
      );
    },
  );

  return validarPosicao(local, perfil);
}

async function ler(perfil: PerfilGps) {
  if (Platform.OS === "web") return lerNavegador(perfil);

  let permissao = await Location.getForegroundPermissionsAsync();

  if (!permissao.granted && permissao.canAskAgain) {
    permissao = await Location.requestForegroundPermissionsAsync();
  }

  if (!permissao.granted) {
    throw new ErroGps(
      "PERMISSAO_NEGADA",
      "Permita a localização nas configurações do navegador ou dispositivo e tente novamente.",
    );
  }

  try {
    if (!(await Location.hasServicesEnabledAsync())) {
      throw new ErroGps(
        "SERVICO_DESLIGADO",
        "Ative a localização do dispositivo e tente novamente.",
      );
    }
  } catch (erro) {
    if (erro instanceof ErroGps) throw erro;
  }

  const local = await Location.getCurrentPositionAsync({
    accuracy: Location.Accuracy.High,
  });

  return validarPosicao(local, perfil);
}

export async function obterPosicao(
  perfil: PerfilGps = "mapa",
): Promise<PosicaoGps> {
  let timer: ReturnType<typeof setTimeout> | undefined;

  try {
    return await Promise.race([
      ler(perfil),

      new Promise<never>((_, rejeitar) => {
        timer = setTimeout(
          () =>
            rejeitar(
              new ErroGps(
                "TIMEOUT",
                "A localização demorou a responder. Confira as permissões e tente novamente.",
              ),
            ),
          20000,
        );
      }),
    ]);
  } catch (erro) {
    if (erro instanceof ErroGps) throw erro;

    throw new ErroGps(
      "INDISPONIVEL",
      "Não foi possível obter sua localização. Confira as permissões e tente novamente.",
    );
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}
