import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useState } from "react";
import {
    Alert,
    KeyboardAvoidingView,
    Platform,
    StyleSheet,
    Text,
    TextInput,
    TouchableOpacity,
    View
} from "react-native";
// import { api } from '../services/api'; // O seu serviço Axios configurado
// import * as SecureStore from 'expo-secure-store'; // Para guardar o token

export default function LoginScreen() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [mostrarSenha, setMostrarSenha] = useState(false);

  const handleLogin = async () => {
    if (!email || !password) {
      Alert.alert("Erro", "Por favor, preencha o e-mail e a palavra-passe.");
      return;
    }

    setLoading(true);
    try {
      // 1. Chamada real à sua API Flask:
      // const response = await api.post('/login', { email, password });

      // 2. Guardar o token no dispositivo de forma segura (usando expo-secure-store):
      // await SecureStore.setItemAsync('userToken', response.data.token);

      // Simulação de sucesso para testarmos o fluxo:
      setTimeout(() => {
        setLoading(false);
        router.replace("/"); // Vai para o Mapa e impede de voltar ao Login com o botão "Back"
      }, 1000);
    } catch (error) {
      Alert.alert("Erro", "Credenciais inválidas ou erro no servidor.");
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : "height"}
    >
      <View style={styles.content}>
        {/* Ícone ou Logo do Aplicativo */}
        <View style={styles.logoContainer}>
          <Ionicons name="water" size={80} color="#d79b00" />
          <Text style={styles.logoTitle}>Litro de Ouro</Text>
          <Text style={styles.logoSubtitle}>
            Encontre o combustível mais barato
          </Text>
        </View>

        <Text style={styles.title}>Bem-vindo de volta!</Text>

        <View style={styles.inputContainer}>
          <Ionicons
            name="mail-outline"
            size={24}
            color="#666"
            style={styles.inputIcon}
          />
          <TextInput
            style={styles.input}
            placeholder="O seu E-mail"
            keyboardType="email-address"
            autoCapitalize="none"
            value={email}
            onChangeText={setEmail}
          />
        </View>

        <View style={styles.inputContainer}>
          <Ionicons
            name="lock-closed-outline"
            size={24}
            color="#666"
            style={styles.inputIcon}
          />
          <TextInput
            style={styles.input}
            placeholder="A sua Palavra-passe"
            secureTextEntry={!mostrarSenha}
            value={password}
            onChangeText={setPassword}
          />
          <TouchableOpacity
            onPress={() => setMostrarSenha(!mostrarSenha)}
            style={styles.eyeIcon}
          >
            <Ionicons
              name={mostrarSenha ? "eye-off-outline" : "eye-outline"}
              size={24}
              color="#666"
            />
          </TouchableOpacity>
        </View>

        <TouchableOpacity style={styles.forgotPassword}>
          <Text style={styles.forgotPasswordText}>
            Esqueceu a palavra-passe?
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.btnLogin, loading && { opacity: 0.7 }]}
          onPress={handleLogin}
          disabled={loading}
        >
          <Text style={styles.btnLoginText}>
            {loading ? "A entrar..." : "Entrar"}
          </Text>
        </TouchableOpacity>

        <View style={styles.registerContainer}>
          <Text style={styles.registerText}>Ainda não tem conta? </Text>
          <TouchableOpacity>
            <Text style={styles.registerLink}>Registe-se</Text>
          </TouchableOpacity>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#FFF" },
  content: { flex: 1, justifyContent: "center", padding: 30 },
  logoContainer: { alignItems: "center", marginBottom: 40 },
  logoTitle: { fontSize: 32, fontWeight: "bold", color: "#333", marginTop: 10 },
  logoSubtitle: { fontSize: 16, color: "#666", marginTop: 5 },
  title: { fontSize: 22, fontWeight: "bold", color: "#333", marginBottom: 20 },
  inputContainer: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#f5f5f5",
    borderRadius: 10,
    paddingHorizontal: 15,
    marginBottom: 15,
    borderWidth: 1,
    borderColor: "#eee",
  },
  inputIcon: { marginRight: 10 },
  input: { flex: 1, paddingVertical: 15, fontSize: 16, color: "#333" },
  eyeIcon: { padding: 10 },
  forgotPassword: { alignItems: "flex-end", marginBottom: 30 },
  forgotPasswordText: { color: "#d79b00", fontWeight: "600" },
  btnLogin: {
    backgroundColor: "#d79b00",
    paddingVertical: 15,
    borderRadius: 10,
    alignItems: "center",
    elevation: 2,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 3,
  },
  btnLoginText: { color: "#FFF", fontSize: 18, fontWeight: "bold" },
  registerContainer: {
    flexDirection: "row",
    justifyContent: "center",
    marginTop: 30,
  },
  registerText: { color: "#666", fontSize: 16 },
  registerLink: { color: "#d79b00", fontSize: 16, fontWeight: "bold" },
});
