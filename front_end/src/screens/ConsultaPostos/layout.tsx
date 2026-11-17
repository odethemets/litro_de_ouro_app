import Ionicons from "@expo/vector-icons/Ionicons";
import { Pressable, StyleSheet, Text } from "react-native";

import { useAppTheme } from "../../components/design";

export function BotaoConsulta({
  label,
  icone,
  onPress,
}: {
  label: string;
  icone: keyof typeof Ionicons.glyphMap;
  onPress(): void;
}) {
  const { colors } = useAppTheme();

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={[
        styles.acao,
        {
          backgroundColor: colors.surface,
          borderColor: colors.border,
        },
      ]}
    >
      <Ionicons
        name={icone}
        size={22}
        color={colors.textPrimary}
      />

      <Text
        style={{
          color: colors.textPrimary,
          fontSize: 12,
        }}
      >
        {label}
      </Text>
    </Pressable>
  );
}

export const styles = StyleSheet.create({
  cabecalho: {
    padding: 16,
    gap: 6,
    borderBottomWidth: 1,
  },
  titulo: {
    fontSize: 23,
    fontWeight: "800",
  },
  cartao: {
    borderWidth: 1,
    padding: 16,
    borderRadius: 18,
  },
  linha: {
    flexDirection: "row",
    gap: 12,
    alignItems: "center",
  },
  nome: {
    fontSize: 17,
    fontWeight: "700",
    flexShrink: 1,
  },
  preco: {
    fontSize: 18,
    fontWeight: "800",
    flexShrink: 1,
  },
  acoes: {
    flexDirection: "row",
    padding: 8,
    gap: 6,
    borderTopWidth: 1,
  },
  acao: {
    flex: 1,
    minWidth: 48,
    minHeight: 56,
    padding: 6,
    borderRadius: 12,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: 4,
  },
  aviso: {
    position: "absolute",
    top: 12,
    alignSelf: "center",
    padding: 10,
    borderRadius: 12,
  },
  fundoModal: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,.4)",
    justifyContent: "flex-end",
    alignItems: "center",
  },
  painelModal: {
    width: "100%",
    maxWidth: 640,
    maxHeight: "90%",
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    overflow: "hidden",
  },
});