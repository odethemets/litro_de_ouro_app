import { CommonActions } from "@react-navigation/native";
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

type Props = NativeStackScreenProps<AuthStackParamList, "RedefinirSenha">;

export default function RedefinirSenha({ route, navigation }: Props) {
  const { colors } = useContext(ThemeContext);
  const { email, codigo } = route.params;

  const [novaSenha, setNovaSenha] = useState("");
  const [confirmarSenha, setConfirmarSenha] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleAtualizarSenha = async () => {
    if (!novaSenha || !confirmarSenha) {
      Alert.alert("Atenção", "Preencha os dois campos.");
      return;
    }
    if (novaSenha !== confirmarSenha) {
      Alert.alert("Erro", "As senhas não coincidem.");
      return;
    }
    if (novaSenha.length < 6) {
      Alert.alert("Atenção", "A senha deve ter pelo menos 6 caracteres.");
      return;
    }

    setIsLoading(true);
    try {
      await api.post("/auth/redefinir-senha", {
        email,
        codigo,
        nova_senha: novaSenha,
      });

      Alert.alert("Sucesso", "Palavra-passe atualizada com sucesso!");

      navigation.dispatch(
        CommonActions.reset({
          index: 0,
          routes: [{ name: "Login" }],
        }),
      );
    } catch (error: any) {
      const msg =
        error.response?.data?.error || "Erro ao redefinir a palavra-passe.";
      Alert.alert("Erro", msg);
    } finally {
      setIsLoading(false);
    }
  };

  const ContentWrapper =
    Platform.OS === "web" ? View : TouchableWithoutFeedback;
  const wrapperProps =
    Platform.OS === "web"
      ? { style: { flex: 1 } }
      : { onPress: Keyboard.dismiss };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1 }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ContentWrapper {...wrapperProps}>
        <View
          style={[styles.container, { backgroundColor: colors.background }]}
        >
          <View style={styles.contentWrapper}>
            <View style={styles.header}>
              <Text style={[styles.title, { color: colors.primary }]}>
                Nova Palavra-passe
              </Text>
              <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
                Escolha uma senha forte para a sua conta.
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
                placeholder="Nova palavra-passe"
                placeholderTextColor={colors.textSecondary}
                secureTextEntry
                autoCapitalize="none"
                value={novaSenha}
                onChangeText={setNovaSenha}
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
                placeholder="Confirmar palavra-passe"
                placeholderTextColor={colors.textSecondary}
                secureTextEntry
                autoCapitalize="none"
                value={confirmarSenha}
                onChangeText={setConfirmarSenha}
                editable={!isLoading}
              />

              {/* CORREÇÃO: Botão com estilo correto apontando para a API */}
              <TouchableOpacity
                style={[
                  styles.button,
                  {
                    backgroundColor: colors.primary,
                    opacity: isLoading ? 0.7 : 1,
                  },
                ]}
                onPress={handleAtualizarSenha}
                disabled={isLoading}
              >
                {isLoading ? (
                  <ActivityIndicator size="small" color="#121212" />
                ) : (
                  <Text style={styles.buttonText}>Atualizar Senha</Text>
                )}
              </TouchableOpacity>

              <TouchableOpacity
                style={styles.backButton}
                onPress={() => navigation.navigate("Login")}
                disabled={isLoading}
              >
                <Text
                  style={[
                    styles.backButtonText,
                    { color: colors.textSecondary },
                  ]}
                >
                  Cancelar e Voltar
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </ContentWrapper>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: "center", alignItems: "center" },
  contentWrapper: { width: "100%", maxWidth: 400, paddingHorizontal: 24 },
  header: { marginBottom: 32, alignItems: "center" },
  title: { fontSize: 24, fontWeight: "bold", marginBottom: 8 },
  subtitle: { fontSize: 14, textAlign: "center" },
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
  backButtonText: { fontSize: 14 },
});
