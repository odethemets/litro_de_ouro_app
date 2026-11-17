import {
  DarkTheme,
  DefaultTheme,
  NavigationContainer,
} from "@react-navigation/native";
import * as SplashScreen from "expo-splash-screen";
import { useEffect } from "react";
import { ActivityIndicator, View } from "react-native";
import {
  AppButton,
  Brand,
  Notice,
  Page,
  Surface,
  useAppTheme,
} from "../components/design";
import { useAuth } from "../contexts/AuthContext";
import { AppRoutes } from "./app.routes";
import { AuthRoutes } from "./auth.routes";

export function Routes() {
  const { status, erroInicializacao, retryInitialization } = useAuth();

  const { activeTheme, colors } = useAppTheme();
  const pronto = status !== "INITIALIZING" || Boolean(erroInicializacao);

  useEffect(() => {
    if (pronto) {
      void SplashScreen.hideAsync().catch(() => undefined);
    }
  }, [pronto]);

  if (status === "INITIALIZING")
    return (
      <Page
        title={erroInicializacao ? "Não conseguimos conectar" : "Carregando"}
      >
        <View
          style={{
            width: "100%",
            maxWidth: 480,
            alignSelf: "center",
          }}
        >
          <Surface>
            <Brand />

            {erroInicializacao ? (
              <>
                <Notice error>{erroInicializacao}</Notice>

                <AppButton
                  label="Tentar novamente"
                  onPress={() => {
                    void retryInitialization();
                  }}
                />

                <Notice>Uma falha de conexão não apaga sua sessão.</Notice>
              </>
            ) : (
              <ActivityIndicator
                accessibilityLabel="Verificando sessão"
                color={colors.primary}
              />
            )}
          </Surface>
        </View>
      </Page>
    );

  const base = activeTheme === "dark" ? DarkTheme : DefaultTheme;

  return (
    <View
      style={{
        flex: 1,
        minHeight: 0,
        backgroundColor: colors.background,
      }}
    >
      <NavigationContainer
        key={status}
        theme={{
          ...base,
          colors: {
            ...base.colors,
            primary: colors.focus,
            background: colors.background,
            card: colors.surface,
            text: colors.textPrimary,
            border: colors.border,
          },
        }}
      >
        {status === "AUTHENTICATED" || status === "GUEST" ? (
          <AppRoutes />
        ) : (
          <AuthRoutes />
        )}
      </NavigationContainer>
    </View>
  );
}
