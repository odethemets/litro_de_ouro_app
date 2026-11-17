import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ActivityIndicator, useColorScheme, View } from "react-native";
import {
  cores,
  isThemeMode,
  type AppThemeMode,
  type ThemeColors,
  type ThemeType,
} from "../theme/colors";

interface ThemeContextData {
  themeMode: AppThemeMode;
  activeTheme: ThemeType;
  colors: ThemeColors;
  setThemeMode(mode: AppThemeMode): Promise<void>;
}
export const ThemeContext = createContext<ThemeContextData>(
  {} as ThemeContextData,
);
const KEY = "@LitroDeOuro:themeMode";

export function ThemeProvider({ children }: { children: ReactNode }) {
  const system = useColorScheme();
  const [themeMode, setMode] = useState<AppThemeMode>("system");
  const [ready, setReady] = useState(false);
  const writes = useRef<Promise<void>>(Promise.resolve());

  useEffect(() => {
    let active = true;
    void AsyncStorage.getItem(KEY)
      .then((saved) => {
        if (active && isThemeMode(saved)) setMode(saved);
      })
      .catch(() => undefined)
      .finally(() => {
        if (active) setReady(true);
      });

    return () => {
      active = false;
    };
  }, []);

  const setThemeMode = useCallback((mode: AppThemeMode) => {
    if (!isThemeMode(mode)) return Promise.reject(new Error("Tema inválido."));
    setMode(mode);

    const save = writes.current
      .catch(() => undefined)
      .then(() => AsyncStorage.setItem(KEY, mode));

    writes.current = save;
    return save;
  }, []);

  const activeTheme: ThemeType =
    themeMode === "system" ? (system ?? "light") : themeMode;

  const colors = cores[activeTheme];

  const value = useMemo(
    () => ({ themeMode, activeTheme, colors, setThemeMode }),
    [themeMode, activeTheme, colors, setThemeMode],
  );

  if (!ready)
    return (
      <View
        style={{
          flex: 1,
          backgroundColor: colors.background,
          justifyContent: "center",
        }}
      >
        <ActivityIndicator
          accessibilityLabel="Carregando aparência"
          color={colors.primary}
        />
      </View>
    );

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}
