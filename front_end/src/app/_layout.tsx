import { Stack } from "expo-router";
import { GestureHandlerRootView } from "react-native-gesture-handler";

export default function RootLayout() {
  return (
    // O flex: 1 é obrigatório para que a tela ocupe todo o espaço
    <GestureHandlerRootView style={{ flex: 1 }}>
      <Stack>
        {/* Esconde o cabeçalho padrão na tela principal para o mapa ficar em ecrã inteiro */}
        <Stack.Screen name="index" options={{ headerShown: false }} />
      </Stack>
    </GestureHandlerRootView>
  );
}
