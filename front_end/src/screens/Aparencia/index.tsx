import Ionicons from "@expo/vector-icons/Ionicons";
import { useState } from "react";
import { Pressable, Text, View } from "react-native";
import { Notice, Page, Surface, useAppTheme } from "../../components/design";
import type { AppThemeMode } from "../../theme/colors";

const options = [
  { mode: "light", label: "Claro", icon: "sunny-outline" },
  { mode: "dark", label: "Escuro", icon: "moon-outline" },
  {
    mode: "system",
    label: "Seguir o sistema",
    icon: "phone-portrait-outline",
  },
] as const;

export default function Aparencia() {
  const { colors, themeMode, setThemeMode } = useAppTheme();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [focusedMode, setFocusedMode] = useState<AppThemeMode | null>(null);

  const choose = async (mode: AppThemeMode) => {
    if (busy) return;

    setBusy(true);
    setError("");

    try {
      await setThemeMode(mode);
    } catch {
      setError(
        "O tema foi aplicado, mas não foi possível guardar a preferência neste dispositivo.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <Page title="Aparência" subtitle="Escolha o tema do aplicativo.">
      <View style={{ maxWidth: 640, width: "100%" }}>
        <Surface>
          {options.map(({ mode, label, icon }) => (
            <Pressable
              key={mode}
              accessibilityRole="radio"
              accessibilityLabel={label}
              accessibilityState={{
                checked: themeMode === mode,
                disabled: busy,
              }}
              aria-checked={themeMode === mode}
              aria-disabled={busy}
              disabled={busy}
              onPress={() => {
                void choose(mode);
              }}
              onFocus={() => setFocusedMode(mode)}
              onBlur={() => setFocusedMode(null)}
              style={({ pressed }) => ({
                padding: 16,
                minHeight: 56,
                borderRadius: 14,
                borderWidth: 2,
                borderColor:
                  focusedMode === mode
                    ? colors.focus
                    : themeMode === mode
                      ? colors.primary
                      : colors.border,
                backgroundColor:
                  themeMode === mode ? colors.selection : colors.surface,
                flexDirection: "row",
                alignItems: "center",
                gap: 12,
                opacity: pressed ? 0.8 : 1,
              })}
            >
              <Ionicons name={icon} size={24} color={colors.textPrimary} />

              <Text
                style={{
                  flex: 1,
                  color: colors.textPrimary,
                  fontSize: 16,
                  fontWeight: "600",
                }}
              >
                {label}
              </Text>

              <Ionicons
                name={
                  themeMode === mode ? "checkmark-circle" : "ellipse-outline"
                }
                size={24}
                color={colors.textPrimary}
              />
            </Pressable>
          ))}

          <Notice>Sua preferência fica salva neste dispositivo.</Notice>

          {error ? <Notice error>{error}</Notice> : null}
        </Surface>
      </View>
    </Page>
  );
}
