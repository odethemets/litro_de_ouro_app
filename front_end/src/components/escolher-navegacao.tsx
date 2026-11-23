import { useEffect, useRef, useState } from "react";
import { Linking, Platform, Text, View } from "react-native";

import {
    identificarSistemaNavegacao,
    montarLinksNavegacao,
    opcoesNavegacao,
    type AplicativoNavegacao,
    type DadosNavegador,
    type DestinoNavegacao,
} from "../utils/linksNavegacao";
import { AppButton, useAppTheme } from "./design";

interface Props extends DestinoNavegacao {
  onErro(mensagem: string): void;
}

interface AmbienteWeb {
  navigator?: DadosNavegador;
  location?: {
    assign(url: string): void;
  };
}

export function EscolherNavegacao({ latitude, longitude, onErro }: Props) {
  const { colors } = useAppTheme();

  const [aberto, definirAberto] = useState(false);
  const [abrindo, definirAbrindo] = useState(false);

  const ocupado = useRef(false);
  const montado = useRef(true);

  const ambiente = globalThis as unknown as AmbienteWeb;

  const sistema = identificarSistemaNavegacao(
    Platform.OS,
    Platform.OS === "web" ? ambiente.navigator : undefined,
  );

  useEffect(() => {
    montado.current = true;

    return () => {
      montado.current = false;
    };
  }, []);

  function alternar() {
    if (ocupado.current) return;

    onErro("");
    definirAberto((valor) => !valor);
  }

  async function abrir(aplicativo: AplicativoNavegacao) {
    if (ocupado.current) return;

    onErro("");

    let links: string[];

    try {
      links = montarLinksNavegacao(
        aplicativo,
        { latitude, longitude },
        sistema,
        Platform.OS !== "web",
      );
    } catch {
      onErro("As coordenadas deste posto não permitem abrir uma rota.");
      return;
    }

    ocupado.current = true;
    definirAbrindo(true);

    try {
      for (const link of links) {
        try {
          if (
            Platform.OS === "web" &&
            link.startsWith("geo:") &&
            ambiente.location
          ) {
            ambiente.location.assign(link);
          } else {
            await Linking.openURL(link);
          }

          if (montado.current) {
            definirAberto(false);
          }

          return;
        } catch {
          // No aplicativo nativo, tenta o link web como alternativa.
          if (!montado.current) return;
        }
      }

      if (montado.current) {
        onErro("Não foi possível abrir a rota. Tente outro aplicativo.");
      }
    } finally {
      ocupado.current = false;

      if (montado.current) {
        definirAbrindo(false);
      }
    }
  }

  return (
    <View style={{ gap: 12 }}>
      <AppButton
        label={aberto ? "Fechar opções de rota" : "Traçar rota"}
        secondary
        onPress={alternar}
      />

      {aberto ? (
        <View
          pointerEvents={abrindo ? "none" : "auto"}
          accessibilityState={{ busy: abrindo }}
          style={{
            padding: 16,
            gap: 12,
            borderWidth: 1,
            borderRadius: 14,
            borderColor: colors.border,
            backgroundColor: colors.surface,
          }}
        >
          <Text
            accessibilityRole="header"
            style={{
              color: colors.textPrimary,
              fontWeight: "700",
              fontSize: 17,
            }}
          >
            Abrir rota com
          </Text>

          {opcoesNavegacao(sistema).map((opcao) => (
            <AppButton
              key={opcao.id}
              label={opcao.label}
              secondary
              onPress={() => {
                void abrir(opcao.id);
              }}
            />
          ))}

          <Text
            style={{
              color: colors.textSecondary,
              lineHeight: 22,
            }}
          >
            O aplicativo escolhido poderá usar sua localização atual para
            calcular a rota, se você permitir.
          </Text>

          {sistema === "android" ? (
            <Text
              style={{
                color: colors.textSecondary,
                lineHeight: 22,
              }}
            >
              A opção do aparelho pode abrir o mapa padrão ou mostrar
              aplicativos compatíveis.
            </Text>
          ) : null}

          {abrindo ? (
            <Text
              accessibilityLiveRegion="polite"
              style={{ color: colors.textSecondary }}
            >
              Abrindo rota…
            </Text>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}
