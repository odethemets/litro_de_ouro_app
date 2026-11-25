import Ionicons from "@expo/vector-icons/Ionicons";
import { useIsFocused } from "@react-navigation/native";
import { useState } from "react";
import { Modal, Pressable, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { useAuth } from "../contexts/AuthContext";
import { FormularioBuscaAssistida } from "./busca-assistida";
import { AppButton, Page, useAppTheme } from "./design";

interface Props {
  aoAplicar?(): void;
}

// A troca de foco ou sessão desmonta a busca anterior e limpa seu estado.
export function AtalhoBuscaMapa({ aoAplicar }: Props) {
  const { token, status, openAuth } = useAuth();
  const focado = useIsFocused();

  return (
    <ConteudoAtalhoBuscaMapa
      key={JSON.stringify([token, status, focado])}
      token={token && status === "AUTHENTICATED" ? token : null}
      focado={focado}
      abrirLogin={() => openAuth("Login")}
      aoAplicar={aoAplicar}
    />
  );
}

interface PropsConteudo extends Props {
  token: string | null;
  focado: boolean;
  abrirLogin(): void;
}

function ConteudoAtalhoBuscaMapa({
  token,
  focado,
  abrirLogin,
  aoAplicar,
}: PropsConteudo) {
  const { colors } = useAppTheme();
  const [aberto, definirAberto] = useState(false);
  const [botaoFocado, definirBotaoFocado] = useState(false);

  return (
    <>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Buscar postos por voz ou texto"
        accessibilityHint="Abre a busca no próprio mapa."
        onPress={() => {
          if (!token) {
            abrirLogin();
            return;
          }

          definirAberto(true);
        }}
        onFocus={() => definirBotaoFocado(true)}
        onBlur={() => definirBotaoFocado(false)}
        style={({ pressed }) => ({
          width: 48,
          height: 48,
          borderRadius: 24,
          borderWidth: 1,
          borderColor: botaoFocado ? colors.textPrimary : colors.border,
          backgroundColor: colors.surface,
          alignItems: "center",
          justifyContent: "center",
          opacity: pressed ? 0.75 : 1,
        })}
      >
        <Ionicons
          name="mic-outline"
          size={24}
          color={colors.textPrimary}
          accessible={false}
        />
      </Pressable>

      {aberto && focado && token ? (
        <Modal
          visible
          transparent
          animationType="slide"
          onRequestClose={() => definirAberto(false)}
        >
          <View
            style={{
              flex: 1,
              justifyContent: "flex-end",
              backgroundColor: "rgba(0, 0, 0, 0.35)",
            }}
          >
            <SafeAreaView
              edges={["bottom", "left", "right"]}
              accessibilityViewIsModal
              style={{
                height: "88%",
                width: "100%",
                maxWidth: 640,
                alignSelf: "center",
                backgroundColor: colors.background,
                borderTopLeftRadius: 20,
                borderTopRightRadius: 20,
                overflow: "hidden",
              }}
            >
              <Page
                title="Buscar postos"
                subtitle="Fale ou digite sua busca e confira antes de aplicar."
              >
                <FormularioBuscaAssistida
                  token={token}
                  mostrarPostos={false}
                  aoAplicar={() => {
                    definirAberto(false);
                    aoAplicar?.();
                  }}
                />
              </Page>

              <View style={{ padding: 16 }}>
                <AppButton
                  label="Fechar busca"
                  secondary
                  onPress={() => definirAberto(false)}
                />
              </View>
            </SafeAreaView>
          </View>
        </Modal>
      ) : null}
    </>
  );
}
