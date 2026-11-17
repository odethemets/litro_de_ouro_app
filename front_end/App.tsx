import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { useAppTheme } from "./src/components/design";
import { AuthProvider } from "./src/contexts/AuthContext";
import { ThemeProvider } from "./src/contexts/ThemeContext";
import { Routes } from "./src/routes";

void SplashScreen.preventAutoHideAsync().catch(() => undefined);

function Content() {
  const { activeTheme } = useAppTheme();

  return (
    <AuthProvider>
      <StatusBar style={activeTheme === "dark" ? "light" : "dark"} />
      <Routes />
    </AuthProvider>
  );
}

export default function App() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider style={{ flex: 1 }}>
        <ThemeProvider>
          <Content />
        </ThemeProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
