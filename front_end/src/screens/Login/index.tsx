//src/screens/Login/index.tsx
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

import { AuthContext } from "../../contexts/AuthContext"; // 1. Importação no topo
import { ThemeContext } from "../../contexts/ThemeContext";
import { AuthStackParamList } from "../../routes/auth.routes";
import { api } from "../../services/API";

type Props = NativeStackScreenProps<AuthStackParamList, "Login">;

export default function Login({ navigation }: Props) {
  // =====================================================================
  // 2. O LUGAR CORRETO: Os useContext têm de ficar AQUI, soltos no topo!
  // =====================================================================
  const { colors } = useContext(ThemeContext) as any;
  const { signIn } = useContext(AuthContext);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleLogin = async () => {
    // 3. NUNCA coloque o useContext aqui dentro!
    if (!email || !password) {
      Alert.alert("Atenção", "Preencha todos os campos.");
      return;
    }

    setIsLoading(true);
    try {
      const response = await api.post("/auth/login", {
        email,
        senha: password,
      });

      // Aqui usamos apenas a função signIn que já foi extraída lá em cima
      await signIn(response.data.token);
    } catch (error: any) {
      if (
        error.response?.status === 403 &&
        error.response.data?.require_validation
      ) {
        navigation.navigate("ValidarCodigo", {
          email: email,
          finalidade: "registo",
        });
      } else {
        const errorMessage =
          error.response?.data?.error || "Não foi possível fazer login.";
        Alert.alert("Erro na autenticação", errorMessage);
      }
    } finally {
      setIsLoading(false);
    }
  };

  // ... resto do código (return, view, inputs, etc) ...
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
                Litro de Ouro
              </Text>
              <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
                A comunidade de preços em tempo real
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
                autoCorrect={false}
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
                value={password}
                onChangeText={setPassword}
                editable={!isLoading}
              />

              <TouchableOpacity
                style={[
                  styles.button,
                  {
                    backgroundColor: colors.primary,
                    opacity: isLoading ? 0.7 : 1,
                  },
                ]}
                onPress={handleLogin}
                disabled={isLoading}
              >
                {isLoading ? (
                  <ActivityIndicator size="small" color="#121212" />
                ) : (
                  <Text style={styles.buttonText}>Entrar</Text>
                )}
              </TouchableOpacity>

              <View style={styles.linksContainer}>
                <TouchableOpacity
                  onPress={() => navigation.navigate("RecuperarSenha")}
                >
                  <Text
                    style={{
                      color: colors.primary,
                      fontSize: 14,
                      fontWeight: "600",
                    }}
                  >
                    Esqueci-me da palavra-passe
                  </Text>
                </TouchableOpacity>

                <TouchableOpacity
                  onPress={() => navigation.navigate("Registo")}
                  style={{ marginTop: 24 }}
                >
                  <Text style={{ color: colors.textSecondary, fontSize: 14 }}>
                    Não tem conta?{" "}
                    <Text style={{ color: colors.primary, fontWeight: "bold" }}>
                      Criar Conta
                    </Text>
                  </Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </View>
      </ContentWrapper>
    </KeyboardAvoidingView>
  );
}

// ... COLE AQUI O SEU CONST STYLES ABAIXO ...

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
