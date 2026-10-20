import { Stack } from "expo-router";
import { GestureHandlerRootView } from "react-native-gesture-handler";

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <Stack>
        {/* Esconde o cabeçalho padrão para usar o próprio design no mapa */}
        <Stack.Screen name="index" options={{ headerShown: false }} />

        {/* Telas secundárias com cabeçalho nativo */}
        <Stack.Screen
          name="registrar-preco"
          options={{ title: "Registrar Preço" }}
        />
        <Stack.Screen name="menor_preco" options={{ title: "Menor Preço" }} />
        {/* Nota: Se existirem telas de login/registrar, o Expo Router lida com elas automaticamente se estiverem na pasta app */}
      </Stack>
    </GestureHandlerRootView>
  );
}
