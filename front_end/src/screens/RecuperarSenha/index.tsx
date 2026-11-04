// src/screens/RecuperarSenha/index.tsx
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

type Props = NativeStackScreenProps<AuthStackParamList, "RecuperarSenha">;

export default function RecuperarSenha({ navigation }: Props) {
  const { colors } = useContext(ThemeContext);
  const [email, setEmail] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleEnviarCodigo = async () => {
    if (!email) {
      Alert.alert("Atenção", "Por favor, informe o seu e-mail.");
      return;
    }

    setIsLoading(true);

    try {
      await api.post("/auth/recuperar-senha", { email: email.trim() });
      navigation.navigate("ValidarCodigo", {
        email: email.trim(),
        finalidade: "recuperacao",
      });
    } catch (error: any) {
      console.error("[RecuperarSenha] Erro:", error);
      const errorMessage =
        error.response?.data?.message ||
        "Erro ao enviar o código. Verifique o e-mail.";
      Alert.alert("Erro", errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  // 1. Extraímos o conteúdo visual para uma função independente
  const renderContent = () => (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
      <View style={styles.contentWrapper}>
        <View style={styles.header}>
          <Text style={[styles.title, { color: colors.primary }]}>
            Recuperar Acesso
          </Text>
          <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
            Insira o seu e-mail associado à conta.
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
            placeholder="E-mail"
            placeholderTextColor={colors.textSecondary}
            keyboardType="email-address"
            autoCapitalize="none"
            value={email}
            onChangeText={setEmail}
            editable={!isLoading}
          />

          <TouchableOpacity
            style={[
              styles.button,
              { backgroundColor: colors.primary, opacity: isLoading ? 0.7 : 1 },
            ]}
            onPress={handleEnviarCodigo}
            disabled={isLoading}
          >
            {isLoading ? (
              <ActivityIndicator size="small" color="#121212" />
            ) : (
              <Text style={styles.buttonText}>Enviar Código</Text>
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
              Cancelar e Voltar
            </Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );

  // 2. Na Web, entregamos a interface crua (garante o foco natural do rato)
  if (Platform.OS === "web") {
    return renderContent();
  }

  // 3. No Mobile, protegemos a interface contra o teclado
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
