import * as Location from "expo-location";

export type PerfilGps = "mapa" | "registro";

export const CENTRO_PADRAO = {
  lat: -7.115,
  lon: -34.861,
};

export type CodigoErroGps =
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
    Math.abs(longitude) > 180
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

  const limite = perfil === "registro" ? 150 : 500;

  if (
    typeof accuracy !== "number" ||
    !Number.isFinite(accuracy) ||
    accuracy < 0 ||
    accuracy > limite
  ) {
    throw new ErroGps(
      "IMPRECISA",
      "A localização está imprecisa ou sem precisão informada. Ative a localização precisa e tente novamente.",
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

async function ler(perfil: PerfilGps) {
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
