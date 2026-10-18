import { Stack } from "expo-router";

export default function Layout() {
  return (
    <Stack>
      {/* 
        A propriedade headerShown: false desliga aquela barra branca do sistema.
        Isto permite que o NOSSO design bonito (que fizemos em cada tela) ocupe o espaço todo.
      */}
      <Stack.Screen name="index" options={{ headerShown: false }} />
      <Stack.Screen name="login" options={{ headerShown: false }} />
      <Stack.Screen name="registrar" options={{ headerShown: false }} />
      <Stack.Screen name="recuperar-senha" options={{ headerShown: false }} />
      <Stack.Screen name="perfil" options={{ headerShown: false }} />
      <Stack.Screen name="registar-preco" options={{ headerShown: false }} />
    </Stack>
  );
}
