// src/contexts/ThemeContext.tsx
import AsyncStorage from "@react-native-async-storage/async-storage";
import { createContext, ReactNode, useEffect, useState } from "react";
import { useColorScheme } from "react-native";
import { AppThemeMode, cores, ThemeType } from "../theme/colors";

// Interface tipada para o TypeScript garantir a segurança no uso das variáveis
interface ThemeContextData {
  themeMode: AppThemeMode;
  activeTheme: ThemeType;
  colors: typeof cores.light;
  setThemeMode: (mode: AppThemeMode) => Promise<void>;
}

export const ThemeContext = createContext<ThemeContextData>(
  {} as ThemeContextData,
);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const systemColorScheme = useColorScheme(); // Lê o modo atual do Sistema Operativo
  const [themeMode, setThemeModeState] = useState<AppThemeMode>("system");
  const [isReady, setIsReady] = useState(false);

  // Carrega a escolha guardada pelo utilizador assim que a app abre
  useEffect(() => {
    async function loadTheme() {
      try {
        const savedMode = await AsyncStorage.getItem("@LitroDeOuro:themeMode");
        if (savedMode) {
          setThemeModeState(savedMode as AppThemeMode);
        }
      } catch (error) {
        console.error("[Theme] Erro ao carregar a preferência visual:", error);
      } finally {
        setIsReady(true);
      }
    }
    loadTheme();
  }, []);

  // Função para mudar o tema no ecrã de "Conta/Configurações" e gravar a escolha
  const setThemeMode = async (mode: AppThemeMode) => {
    try {
      setThemeModeState(mode);
      await AsyncStorage.setItem("@LitroDeOuro:themeMode", mode);
    } catch (error) {
      console.error("[Theme] Erro ao gravar a preferência visual:", error);
    }
  };

  // Lógica de resolução: se for 'system', segue o SO. Caso contrário, força Claro ou Escuro.
  const activeTheme: ThemeType =
    themeMode === "system" ? systemColorScheme || "dark" : themeMode;

  const currentColors = cores[activeTheme];

  // Evita renderizar a app genérica por milissegundos enquanto lê do AsyncStorage
  if (!isReady) return null;

  return (
    <ThemeContext.Provider
      value={{ themeMode, activeTheme, colors: currentColors, setThemeMode }}
    >
      {children}
    </ThemeContext.Provider>
  );
}
