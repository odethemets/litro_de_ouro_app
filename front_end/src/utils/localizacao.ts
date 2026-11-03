import * as Location from "expo-location";

export type CodigoErroGps =
  | "PERMISSAO_NEGADA"
  | "SERVICO_DESLIGADO"
  | "TIMEOUT"
  | "INDISPONIVEL";

export class ErroGps extends Error {
  constructor(
    public readonly codigo: CodigoErroGps,
    mensagem: string,
    /** Se false, só as configurações do sistema resolvem (use Linking.openSettings()). */
    public readonly podePedirNovamente: boolean = true,
  ) {
    super(mensagem);
    this.name = "ErroGps";
  }
}

export interface PosicaoGps {
  latitude: number;
  longitude: number;
  /** Raio de incerteza em metros, ou null se o aparelho não informou. */
  precisaoM: number | null;
  obtidaEm: number;
  /** Android informa quando a localização vem de app de "localização falsa". */
  simulada: boolean;
}

export type PerfilGps = "mapa" | "registro";

const PERFIS: Record<
  PerfilGps,
  {
    precisao: Location.LocationAccuracy;
    idadeMaximaMs: number;
    timeoutMs: number;
  }
> = {
  // Só para centralizar o mapa: aceita posição recente e menos exata.
  mapa: {
    precisao: Location.Accuracy.Balanced,
    idadeMaximaMs: 60_000,
    timeoutMs: 8_000,
  },
  // Registro de preço (geofencing): exige leitura fresca e a melhor precisão.
  registro: {
    precisao: Location.Accuracy.High,
    idadeMaximaMs: 10_000,
    timeoutMs: 15_000,
  },
};

function comTimeout<T>(promessa: Promise<T>, ms: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout>;
  const limite = new Promise<never>((_, rejeitar) => {
    timer = setTimeout(
      () =>
        rejeitar(
          new ErroGps("TIMEOUT", "Tempo esgotado ao obter a localização."),
        ),
      ms,
    );
  });
  return Promise.race([promessa, limite]).finally(() => clearTimeout(timer));
}

function paraPosicao(l: Location.LocationObject): PosicaoGps {
  const { latitude, longitude, accuracy } = l.coords;
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
    throw new ErroGps(
      "INDISPONIVEL",
      "O aparelho devolveu uma localização inválida.",
    );
  }
  return {
    latitude,
    longitude,
    precisaoM:
      typeof accuracy === "number" && Number.isFinite(accuracy)
        ? accuracy
        : null,
    obtidaEm: l.timestamp || Date.now(),
    simulada: (l as { mocked?: boolean }).mocked === true,
  };
}

async function garantirPermissao(): Promise<void> {
  let perm = await Location.getForegroundPermissionsAsync();
  if (!perm.granted && perm.canAskAgain)
    perm = await Location.requestForegroundPermissionsAsync();
  if (!perm.granted) {
    throw new ErroGps(
      "PERMISSAO_NEGADA",
      perm.canAskAgain
        ? "Precisamos da sua localização para mostrar os postos próximos."
        : "A permissão de localização está bloqueada. Ative-a nas configurações do aparelho.",
      perm.canAskAgain,
    );
  }
}

/**
 * Obtém a posição atual com permissão, serviço ligado, timeout e fallback.
 * Sempre rejeita com ErroGps (nunca com erro cru), para a tela mostrar a mensagem certa.
 */
export async function obterPosicao(
  perfil: PerfilGps = "mapa",
): Promise<PosicaoGps> {
  const cfg = PERFIS[perfil];

  await garantirPermissao();

  try {
    if (!(await Location.hasServicesEnabledAsync())) {
      throw new ErroGps(
        "SERVICO_DESLIGADO",
        "O GPS do aparelho está desligado. Ative-o e tente novamente.",
      );
    }
  } catch (e) {
    if (e instanceof ErroGps) throw e;
    // Na web essa verificação pode não existir; segue e deixa o navegador decidir.
  }

  // 1) Posição em cache, se recente o bastante (resposta instantânea).
  try {
    const recente = await Location.getLastKnownPositionAsync({
      maxAge: cfg.idadeMaximaMs,
    });
    if (recente) return paraPosicao(recente);
  } catch {
    // Sem cache disponível: segue para a leitura ao vivo.
  }

  // 2) Leitura ao vivo com limite de tempo.
  try {
    return paraPosicao(
      await comTimeout(
        Location.getCurrentPositionAsync({ accuracy: cfg.precisao }),
        cfg.timeoutMs,
      ),
    );
  } catch (e) {
    if (e instanceof ErroGps && e.codigo !== "TIMEOUT") throw e;
    // 3) Para o mapa, uma posição antiga é melhor que nenhuma. Para o registro, nunca.
    if (perfil === "mapa") {
      try {
        const antiga = await Location.getLastKnownPositionAsync({});
        if (antiga) return paraPosicao(antiga);
      } catch {
        // ignora e cai no erro abaixo
      }
    }
    if (e instanceof ErroGps) throw e;
    throw new ErroGps(
      "INDISPONIVEL",
      "Não foi possível obter a sua localização. Vá para um local aberto e tente novamente.",
    );
  }
}
