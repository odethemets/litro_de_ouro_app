import { Stack } from "expo-router";
import { GestureHandlerRootView } from "react-native-gesture-handler";

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <Stack>
        {/* Esconde o cabeçalho padrão para você usar o seu próprio design */}
        <Stack.Screen name="index" options={{ headerShown: false }} />
        <Stack.Screen
          name="registrar-preco"
          options={{ title: "Registrar Preço" }}
        />
        <Stack.Screen name="menor_preco" options={{ title: "Menor Preço" }} />
      </Stack>
    </GestureHandlerRootView>
  );
}
