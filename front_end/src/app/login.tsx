import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useState } from "react";
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { saveToken } from "../utils/token"; // <-- NOVA IMPORTAÇÃO LIMPA

export default function LoginScreen() {
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    if (!email || !password) {
      Alert.alert("Atenção", "Por favor, preencha o email e a senha.");
      return;
    }

    setLoading(true);

    try {
      const API_URL =
        Platform.OS === "web"
          ? "https://litro-de-ouro-app.onrender.com"
          : "https://litro-de-ouro-app.onrender.com";

      const response = await fetch(`${API_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.message || "Credenciais inválidas");
      }

      // USO LIMPO DA FUNÇÃO CENTRAL
      await saveToken(data.token);
      router.replace("/");
    } catch (error: any) {
      Alert.alert(
        "Erro no Login",
        error.message || "Não foi possível conectar ao servidor.",
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : "height"}
    >
      <View style={styles.header}>
        <TouchableOpacity
          style={styles.backButton}
          onPress={() => router.back()}
        >
          <Ionicons name="arrow-back" size={28} color="#333" />
        </TouchableOpacity>
      </View>

      <View style={styles.content}>
        <View style={styles.logoContainer}>
          <Ionicons name="water" size={80} color="#d79b00" />
          <Text style={styles.title}>Litro de Ouro</Text>
          <Text style={styles.subtitle}>Faça login para registar preços</Text>
        </View>

        <View style={styles.form}>
          <View style={styles.inputContainer}>
            <Ionicons
              name="mail-outline"
              size={20}
              color="#666"
              style={styles.inputIcon}
            />
            <TextInput
              style={styles.input}
              placeholder="Email"
              value={email}
              onChangeText={setEmail}
              keyboardType="email-address"
              autoCapitalize="none"
              autoCorrect={false}
              editable={!loading}
            />
          </View>

          <View style={styles.inputContainer}>
            <Ionicons
              name="lock-closed-outline"
              size={20}
              color="#666"
              style={styles.inputIcon}
            />
            <TextInput
              style={styles.input}
              placeholder="Senha"
              value={password}
              onChangeText={setPassword}
              secureTextEntry={!showPassword}
              autoCapitalize="none"
              editable={!loading}
            />
            <TouchableOpacity
              onPress={() => setShowPassword(!showPassword)}
              style={styles.eyeIcon}
            >
              <Ionicons
                name={showPassword ? "eye-outline" : "eye-off-outline"}
                size={20}
                color="#666"
              />
            </TouchableOpacity>
          </View>

          <TouchableOpacity
            style={styles.forgotPassword}
            activeOpacity={0.8}
            onPress={() => router.push("/recuperar-senha")}
          >
            <Text style={styles.forgotPasswordText}>Esqueceu a senha?</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.loginBtn, loading && styles.loginBtnDisabled]}
            activeOpacity={0.8}
            onPress={handleLogin}
            disabled={loading}
          >
            {loading ? (
              <ActivityIndicator color="#FFF" />
            ) : (
              <Text style={styles.loginBtnText}>Entrar</Text>
            )}
          </TouchableOpacity>

          <View style={styles.registerContainer}>
            <Text style={styles.registerText}>Ainda não tem conta? </Text>
            <TouchableOpacity onPress={() => router.push("/registrar")}>
              <Text style={styles.registerLink}>Registe-se</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#FFF" },
  header: {
    paddingTop: Platform.OS === "ios" ? 50 : 30,
    paddingHorizontal: 20,
  },
  backButton: { width: 40, height: 40, justifyContent: "center" },
  content: {
    flex: 1,
    paddingHorizontal: 30,
    justifyContent: "center",
    marginTop: -50,
  },
  logoContainer: { alignItems: "center", marginBottom: 40 },
  title: { fontSize: 28, fontWeight: "bold", color: "#333", marginTop: 10 },
  subtitle: { fontSize: 16, color: "#666", marginTop: 5 },
  form: { width: "100%" },
  inputContainer: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#F5F5F5",
    borderRadius: 10,
    marginBottom: 15,
    paddingHorizontal: 15,
    height: 55,
    borderWidth: 1,
    borderColor: "#E0E0E0",
  },
  inputIcon: { marginRight: 10 },
  input: { flex: 1, height: "100%", color: "#333", fontSize: 16 },
  eyeIcon: { padding: 10 },
  forgotPassword: { alignSelf: "flex-end", marginBottom: 25 },
  forgotPasswordText: { color: "#208AEF", fontSize: 14, fontWeight: "600" },
  loginBtn: {
    backgroundColor: "#208AEF",
    height: 55,
    borderRadius: 10,
    justifyContent: "center",
    alignItems: "center",
    elevation: 3,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 3,
  },
  loginBtnDisabled: { backgroundColor: "#A0C8F0", elevation: 0 },
  loginBtnText: { color: "#FFF", fontSize: 18, fontWeight: "bold" },
  registerContainer: {
    flexDirection: "row",
    justifyContent: "center",
    marginTop: 30,
  },
  registerText: { color: "#666", fontSize: 15 },
  registerLink: { color: "#d79b00", fontSize: 15, fontWeight: "bold" },
});
