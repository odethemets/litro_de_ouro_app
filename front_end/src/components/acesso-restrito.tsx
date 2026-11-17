import Ionicons from "@expo/vector-icons/Ionicons";
import type { ReactNode } from "react";
import { Text, View } from "react-native";
import { useAuth } from "../contexts/AuthContext";
import { AppButton, Notice, Page, Surface, useAppTheme } from "./design";

export function AcessoRestrito({ children }: { children: ReactNode }) {
  const { status, openAuth } = useAuth();
  const { colors } = useAppTheme();

  if (status === "AUTHENTICATED") return <>{children}</>;

  return (
    <Page title="Modo visitante" subtitle="Explore o mapa e o Feed sem conta.">
      <View
        style={{
          width: "100%",
          maxWidth: 520,
          alignSelf: "center",
        }}
      >
        <Surface>
          <Ionicons
            name="person-circle-outline"
            size={72}
            color={colors.textSecondary}
            accessible={false}
          />

          <Text
            style={{
              color: colors.textPrimary,
              fontSize: 24,
              fontWeight: "800",
            }}
          >
            Entre para continuar
          </Text>

          <Notice>
            Para contribuir, acompanhar sua atividade e acessar esta área, entre
            na sua conta.
          </Notice>

          <AppButton label="Fazer login" onPress={() => openAuth("Login")} />
          <AppButton
            label="Criar conta"
            secondary
            onPress={() => openAuth("Registo")}
          />
        </Surface>
      </View>
    </Page>
  );
}
