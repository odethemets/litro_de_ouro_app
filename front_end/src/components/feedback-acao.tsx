import { useContext } from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { ThemeContext } from "../contexts/ThemeContext";
import type { MensagemAcao } from "../utils/feedbackPostos";

interface Props {
  feedback: MensagemAcao | null;
  onClose?: () => void;
  acao?: { rotulo: string; executar: () => void };
}

export function FeedbackAcao({ feedback, onClose, acao }: Props) {
  const { colors } = useContext(ThemeContext);
  if (!feedback) return null;

  const cor =
    feedback.tipo === "sucesso"
      ? colors.success
      : feedback.tipo === "erro"
        ? colors.danger
        : feedback.tipo === "aviso"
          ? colors.primary
          : colors.textSecondary;
  const simbolo =
    feedback.tipo === "sucesso" ? "✓" : feedback.tipo === "info" ? "i" : "!";

  return (
    <View
      style={[
        styles.container,
        { backgroundColor: colors.surface, borderColor: cor },
      ]}
    >
      <Text
        accessibilityElementsHidden
        importantForAccessibility="no"
        style={[styles.simbolo, { color: cor }]}
      >
        {simbolo}
      </Text>
      <View
        style={styles.conteudo}
        accessibilityRole="alert"
        accessibilityLiveRegion="polite"
      >
        <Text style={[styles.titulo, { color: colors.textPrimary }]}>
          {feedback.titulo}
        </Text>
        <Text style={[styles.mensagem, { color: colors.textSecondary }]}>
          {feedback.mensagem}
        </Text>
        {acao && (
          <TouchableOpacity
            onPress={acao.executar}
            accessibilityRole="button"
            style={styles.acao}
          >
            <Text style={{ color: colors.textPrimary, fontWeight: "bold" }}>
              {acao.rotulo}
            </Text>
          </TouchableOpacity>
        )}
      </View>
      {onClose && (
        <TouchableOpacity
          onPress={onClose}
          accessibilityRole="button"
          accessibilityLabel="Fechar aviso"
          style={styles.fechar}
        >
          <Text style={{ color: colors.textSecondary, fontSize: 20 }}>×</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    alignItems: "flex-start",
    padding: 14,
    borderWidth: 1,
    borderLeftWidth: 4,
    borderRadius: 12,
  },
  simbolo: { fontSize: 22, fontWeight: "bold", marginRight: 12 },
  conteudo: { flex: 1 },
  titulo: { fontSize: 15, fontWeight: "bold", marginBottom: 4 },
  mensagem: { fontSize: 13, lineHeight: 19 },
  fechar: {
    minWidth: 36,
    minHeight: 36,
    alignItems: "center",
    justifyContent: "center",
    marginLeft: 4,
  },
  acao: { paddingVertical: 10, marginTop: 4 },
});
