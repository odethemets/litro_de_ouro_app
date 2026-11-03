// App.tsx
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { AuthProvider } from "./src/contexts/AuthContext"; // <-- ADICIONADO
import { ThemeProvider } from "./src/contexts/ThemeContext";
import { Routes } from "./src/routes";

export default function App() {
  return (
    // O flex: 1 aqui é obrigatório para a Web não colapsar a altura da página
    <SafeAreaProvider style={{ flex: 1 }}>
      {/* O AuthProvider abraça toda a aplicação para gerir o estado de login */}
      <AuthProvider>
        <ThemeProvider>
          <StatusBar style="auto" />
          <Routes />
        </ThemeProvider>
      </AuthProvider>
    </SafeAreaProvider>
  );
}
