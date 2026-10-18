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

export default function RegistarScreen() {
  const router = useRouter();
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleRegister = async () => {
    if (!nome || !email || !password) {
      Alert.alert("Atenção", "Por favor, preencha todos os campos.");
      return;
    }

    setLoading(true);

    try {
      // IMPORTANTE: Substitua pelo IP da sua máquina
      const API_URL =
        Platform.OS === "web"
          ? "https://litro-de-ouro-app.onrender.com"
          : "https://litro-de-ouro-app.onrender.com";

      const response = await fetch(`${API_URL}/auth/registrar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nome, email, password }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.message || "Erro ao criar conta.");
      }

      Alert.alert(
        "Sucesso!",
        "Conta criada com sucesso. Faça login para continuar.",
      );
      router.replace("/login"); // Volta para o login após criar a conta
    } catch (error: any) {
      Alert.alert(
        "Erro",
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
        <Text style={styles.title}>Criar Conta</Text>
        <Text style={styles.subtitle}>Junte-se ao Litro de Ouro</Text>

        <View style={styles.form}>
          <View style={styles.inputContainer}>
            <Ionicons
              name="person-outline"
              size={20}
              color="#666"
              style={styles.inputIcon}
            />
            <TextInput
              style={styles.input}
              placeholder="Nome Completo"
              value={nome}
              onChangeText={setNome}
              autoCapitalize="words"
              editable={!loading}
            />
          </View>

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
            style={[styles.loginBtn, loading && styles.loginBtnDisabled]}
            activeOpacity={0.8}
            onPress={handleRegister}
            disabled={loading}
          >
            {loading ? (
              <ActivityIndicator color="#FFF" />
            ) : (
              <Text style={styles.loginBtnText}>Registrar</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

// OS ESTILOS SÃO IDÊNTICOS AO DO LOGIN PARA MANTER COESÃO VISUAL
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
  title: { fontSize: 28, fontWeight: "bold", color: "#333", marginBottom: 5 },
  subtitle: { fontSize: 16, color: "#666", marginBottom: 30 },
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
  loginBtn: {
    backgroundColor: "#d79b00",
    height: 55,
    borderRadius: 10,
    justifyContent: "center",
    alignItems: "center",
    marginTop: 20,
    elevation: 3,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 3,
  },
  loginBtnDisabled: { backgroundColor: "#e8c366", elevation: 0 },
  loginBtnText: { color: "#FFF", fontSize: 18, fontWeight: "bold" },
});
