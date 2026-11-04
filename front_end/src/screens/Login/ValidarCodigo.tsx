// src/screens/ValidarCodigo/index.tsx
import { NativeStackScreenProps } from "@react-navigation/native-stack";
import { useContext, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Keyboard,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  TouchableWithoutFeedback,
  View,
} from "react-native";
import { ThemeContext } from "../../contexts/ThemeContext";
import { AuthStackParamList } from "../../routes/auth.routes";
import { api } from "../../services/API";

type Props = NativeStackScreenProps<AuthStackParamList, "ValidarCodigo">;

export default function ValidarCodigo({ route, navigation }: Props) {
  const { colors } = useContext(ThemeContext);
  const { email, finalidade } = route.params;

  const [codigo, setCodigo] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleValidar = async () => {
    if (codigo.length !== 6) {
      Alert.alert("Atenção", "O código deve conter exatamente 6 dígitos.");
      return;
    }

    // Se for recuperação, o backend só valida o código junto com a nova senha. Avançamos direto.
    if (finalidade === "recuperacao") {
      navigation.navigate("RedefinirSenha", { email, codigo });
      return;
    }

    // Se for registo, bate na API de confirmação
    setIsLoading(true);
    try {
      await api.post("/auth/confirmar-email", { email, codigo });
      Alert.alert(
        "Sucesso",
        "E-mail confirmado com sucesso! Já pode fazer login.",
      );
      navigation.navigate("Login");
    } catch (error: any) {
      console.error("[ValidarCodigo] Erro:", error);
      const errorMessage =
        error.response?.data?.error || "Código inválido ou expirado.";
      Alert.alert("Erro", errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const renderContent = () => (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
      <View style={styles.contentWrapper}>
        <View style={styles.header}>
          <Text style={[styles.title, { color: colors.primary }]}>
            Verificação
          </Text>
          <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
            Código de 6 dígitos enviado para:
          </Text>
          <Text style={[styles.emailHighlight, { color: colors.textPrimary }]}>
            {email}
          </Text>
        </View>

        <View style={styles.form}>
          <TextInput
            style={[
              styles.input,
              {
                backgroundColor: colors.surface,
                color: colors.textPrimary,
                borderColor: colors.border,
              },
            ]}
            placeholder="000000"
            placeholderTextColor={colors.textSecondary}
            keyboardType="number-pad"
            maxLength={6}
            textAlign="center"
            value={codigo}
            onChangeText={setCodigo}
            editable={!isLoading}
          />

          <TouchableOpacity
            style={[
              styles.button,
              {
                backgroundColor: colors.primary,
                opacity: isLoading || codigo.length < 6 ? 0.7 : 1,
              },
            ]}
            onPress={handleValidar}
            disabled={isLoading || codigo.length < 6}
          >
            {isLoading ? (
              <ActivityIndicator size="small" color="#121212" />
            ) : (
              <Text style={styles.buttonText}>Confirmar Código</Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.backButton}
            onPress={() => navigation.goBack()}
            disabled={isLoading}
          >
            <Text
              style={[styles.backButtonText, { color: colors.textSecondary }]}
            >
              Voltar
            </Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );

  if (Platform.OS === "web") return renderContent();

  return (
    <KeyboardAvoidingView
      style={{ flex: 1 }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <TouchableWithoutFeedback onPress={Keyboard.dismiss}>
        {renderContent()}
      </TouchableWithoutFeedback>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: "center", alignItems: "center" },
  contentWrapper: { width: "100%", maxWidth: 400, paddingHorizontal: 24 },
  header: { marginBottom: 48, alignItems: "center" },
  title: { fontSize: 32, fontWeight: "bold", marginBottom: 8 },
  subtitle: { fontSize: 16, textAlign: "center", marginBottom: 4 },
  emailHighlight: { fontSize: 16, fontWeight: "bold", textAlign: "center" },
  form: { width: "100%" },
  input: {
    height: 54,
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 16,
    marginBottom: 16,
    fontSize: 16,
  },
  button: {
    height: 54,
    borderRadius: 8,
    justifyContent: "center",
    alignItems: "center",
    marginTop: 8,
  },
  buttonText: { color: "#121212", fontSize: 16, fontWeight: "bold" },
  backButton: { marginTop: 24, alignItems: "center" },
  backButtonText: { fontSize: 16 },
  linksContainer: { marginTop: 24, alignItems: "center" },
});
