// src/screens/Registo/index.tsx
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
import { api } from "../../services/API"; // CORREÇÃO: "api" em minúsculas para evitar erro de TS

type Props = NativeStackScreenProps<AuthStackParamList, "Registo">;

export default function Registo({ navigation }: Props) {
  // CORREÇÃO: "as any" para blindar o TypeScript contra o erro de tipo unknown
  const { colors } = useContext(ThemeContext) as any;
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleRegisto = async () => {
    if (!nome || !email || !senha) {
      Alert.alert("Atenção", "Preencha todos os campos (nome, email, senha).");
      return;
    }

    setIsLoading(true);

    try {
      // Bate no endpoint real de cadastro que acabámos de criar no backend
      await api.post("/auth/cadastro", { nome, email: email.trim(), senha });

      Alert.alert(
        "Sucesso!",
        "Conta criada. Verifique o seu e-mail com o código de acesso.",
      );

      navigation.navigate("ValidarCodigo", {
        email: email.trim(),
        finalidade: "registo",
      });
    } catch (error: any) {
      console.error("[Registo] Erro:", error);
      // Lê a chave "error" que o Flask envia (ex: "Este e-mail já está registado")
      const errorMessage =
        error.response?.data?.error || "Erro ao criar conta.";
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
            Criar Conta
          </Text>
          <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
            Junte-se à comunidade Litro de Ouro.
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
            placeholder="Nome completo"
            placeholderTextColor={colors.textSecondary}
            value={nome}
            onChangeText={setNome}
            editable={!isLoading}
          />

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

          <TextInput
            style={[
              styles.input,
              {
                backgroundColor: colors.surface,
                color: colors.textPrimary,
                borderColor: colors.border,
              },
            ]}
            placeholder="Palavra-passe"
            placeholderTextColor={colors.textSecondary}
            secureTextEntry
            autoCapitalize="none"
            value={senha}
            onChangeText={setSenha}
            editable={!isLoading}
          />

          <TouchableOpacity
            style={[
              styles.button,
              { backgroundColor: colors.primary, opacity: isLoading ? 0.7 : 1 },
            ]}
            onPress={handleRegisto}
            disabled={isLoading}
          >
            {isLoading ? (
              <ActivityIndicator size="small" color="#121212" />
            ) : (
              <Text style={styles.buttonText}>Avançar</Text>
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
              Voltar ao Login
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
  subtitle: { fontSize: 16, textAlign: "center" },
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
});
