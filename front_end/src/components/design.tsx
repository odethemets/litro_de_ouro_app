import Ionicons from "@expo/vector-icons/Ionicons";
import { useContext, useState, type ReactNode } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  useWindowDimensions,
  View,
  type TextInputProps,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { ThemeContext } from "../contexts/ThemeContext";
import { design } from "../theme/design";

export const useAppTheme = () => useContext(ThemeContext);

export function Brand({ compact = false }: { compact?: boolean }) {
  const { colors } = useAppTheme();

  return (
    <View style={styles.brand}>
      <Ionicons
        name="water"
        size={compact ? 24 : 36}
        color={colors.primary}
        accessible={false}
      />
      <Text
        style={{
          color: colors.textPrimary,
          fontSize: compact ? 17 : 24,
          fontWeight: "800",
        }}
      >
        Litro de Ouro
      </Text>
    </View>
  );
}

export function Surface({ children }: { children: ReactNode }) {
  const { colors } = useAppTheme();

  return (
    <View
      style={[
        styles.card,
        {
          backgroundColor: colors.surface,
          borderColor: colors.border,
        },
      ]}
    >
      {children}
    </View>
  );
}

export function AppButton({
  label,
  onPress,
  secondary = false,
  busy = false,
  disabled = false,
  selected,
  icon,
  accessibilityLabel,
  fullWidth = false,
}: {
  label: string;
  onPress(): void;
  secondary?: boolean;
  busy?: boolean;
  disabled?: boolean;
  selected?: boolean;
  icon?: keyof typeof Ionicons.glyphMap;
  accessibilityLabel?: string;
  fullWidth?: boolean;
}) {
  const { colors } = useAppTheme();
  const [focused, setFocused] = useState(false);
  const [hovered, setHovered] = useState(false);

  const blocked = disabled || busy;

  const foreground = blocked
    ? colors.textSecondary
    : secondary || selected
      ? colors.textPrimary
      : colors.primaryText;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityState={{ disabled: blocked, busy, selected }}
      aria-disabled={blocked}
      aria-busy={busy}
      aria-pressed={selected}
      disabled={blocked}
      onPress={onPress}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      onHoverIn={() => setHovered(true)}
      onHoverOut={() => setHovered(false)}
      style={({ pressed }) => [
        styles.button,
        {
          minHeight: 52,
          minWidth: 0,
          maxWidth: fullWidth ? "100%" : design.form,
          alignSelf: "stretch",
          flexShrink: 1,
          paddingHorizontal: 16,
          cursor:
            Platform.OS === "web" ? (blocked ? "auto" : "pointer") : undefined,
          backgroundColor: blocked
            ? colors.input
            : selected
              ? colors.selection
              : secondary
                ? hovered || pressed
                  ? colors.input
                  : colors.surface
                : colors.primary,
          borderColor: focused
            ? colors.focus
            : (hovered && !blocked) || selected
              ? colors.textPrimary
              : secondary
                ? colors.border
                : "transparent",
          opacity: blocked ? 0.7 : pressed ? 0.8 : 1,
        },
      ]}
    >
      {busy ? (
        <ActivityIndicator color={foreground} />
      ) : icon ? (
        <Ionicons name={icon} size={22} color={foreground} accessible={false} />
      ) : null}

      <Text
        style={{
          color: foreground,
          fontSize: 16,
          lineHeight: 22,
          fontWeight: "700",
          textAlign: "center",
          flexShrink: 1,
          minWidth: 0,
        }}
      >
        {busy ? "Aguarde..." : label}
      </Text>
    </Pressable>
  );
}

export function AppField({
  label,
  ...props
}: TextInputProps & { label: string }) {
  const { colors } = useAppTheme();
  const [focused, setFocused] = useState(false);

  return (
    <View style={{ gap: 8 }}>
      <Text
        style={{
          color: colors.textPrimary,
          fontSize: 16,
          fontWeight: "600",
        }}
      >
        {label}
      </Text>

      <TextInput
        {...props}
        accessibilityLabel={label}
        placeholderTextColor={colors.textSecondary}
        onFocus={(e) => {
          setFocused(true);
          props.onFocus?.(e);
        }}
        onBlur={(e) => {
          setFocused(false);
          props.onBlur?.(e);
        }}
        style={[
          styles.input,
          {
            color: colors.textPrimary,
            backgroundColor: colors.input,
            borderColor: focused ? colors.focus : colors.border,
          },
          props.style,
        ]}
      />
    </View>
  );
}

export function Notice({
  children,
  error = false,
}: {
  children: ReactNode;
  error?: boolean;
}) {
  const { colors } = useAppTheme();

  return (
    <Text
      accessibilityRole={error ? "alert" : undefined}
      style={{
        color: error ? colors.danger : colors.textSecondary,
        fontSize: 15,
        lineHeight: 23,
      }}
    >
      {children}
    </Text>
  );
}

export function AuthLayout({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
}) {
  const { colors } = useAppTheme();
  const desktop = useWindowDimensions().width >= design.desktop;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.background }}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={styles.authScroll}
        >
          <View
            style={[
              styles.authContent,
              desktop && {
                flexDirection: "row",
                alignItems: "center",
                gap: 64,
              },
            ]}
          >
            <View
              style={{
                flex: desktop ? 1 : undefined,
                gap: 20,
                minWidth: 0,
              }}
            >
              <Brand />

              <Text
                accessibilityRole="header"
                style={{
                  color: colors.textPrimary,
                  fontSize: desktop ? 40 : 30,
                  lineHeight: desktop ? 48 : 38,
                  fontWeight: "800",
                }}
              >
                {title}
              </Text>

              <Notice>{subtitle}</Notice>

              {desktop ? (
                <View
                  style={[
                    styles.illustration,
                    {
                      backgroundColor: colors.surface,
                      borderColor: colors.border,
                    },
                  ]}
                >
                  <Ionicons
                    name="map-outline"
                    size={80}
                    color={colors.textSecondary}
                    accessible={false}
                  />
                  <View style={{ gap: 12 }}>
                    <Ionicons
                      name="location"
                      size={30}
                      color="#1D4ED8"
                      accessible={false}
                    />
                    <Ionicons
                      name="location"
                      size={30}
                      color="#7C3AED"
                      accessible={false}
                    />
                  </View>
                </View>
              ) : null}
            </View>

            <View
              style={{
                width: "100%",
                maxWidth: design.form,
                gap: 16,
                alignSelf: desktop ? "center" : "stretch",
              }}
            >
              {children}
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

export function Page({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  const { colors } = useAppTheme();

  return (
    <SafeAreaView
      edges={["top", "left", "right"]}
      style={{ flex: 1, backgroundColor: colors.background }}
    >
      <ScrollView contentContainerStyle={{ flexGrow: 1, padding: 24 }}>
        <View
          style={{
            width: "100%",
            maxWidth: design.content,
            alignSelf: "center",
            gap: 20,
          }}
        >
          <ScrollView
            keyboardShouldPersistTaps="handled"
            contentContainerStyle={{ flexGrow: 1, padding: 24 }}
          ></ScrollView>
          <Text
            accessibilityRole="header"
            style={{
              color: colors.textPrimary,
              fontSize: 28,
              fontWeight: "800",
            }}
          >
            {title}
          </Text>

          {subtitle ? <Notice>{subtitle}</Notice> : null}
          {children}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  brand: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  card: {
    borderRadius: design.radius,
    padding: 24,
    gap: 16,
    borderWidth: 1,
  },
  button: {
    minHeight: design.touch,
    borderRadius: design.fieldRadius,
    padding: 14,
    borderWidth: 2,
    flexDirection: "row",
    justifyContent: "center",
    alignItems: "center",
    gap: 10,
  },
  input: {
    minHeight: 52,
    borderWidth: 2,
    borderRadius: design.fieldRadius,
    padding: 14,
    fontSize: 16,
  },
  authScroll: {
    flexGrow: 1,
    justifyContent: "center",
    padding: 24,
  },
  authContent: {
    width: "100%",
    maxWidth: design.content,
    alignSelf: "center",
    gap: 28,
  },
  illustration: {
    borderWidth: 1,
    borderRadius: design.radius,
    padding: 32,
    flexDirection: "row",
    gap: 24,
    justifyContent: "center",
    alignItems: "center",
  },
});
