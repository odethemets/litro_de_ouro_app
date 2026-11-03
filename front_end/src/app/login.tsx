import { useRouter } from "expo-router";
import { useState } from "react";
import {
  ActivityIndicator,
  Alert,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { api } from "../services/API";
import { saveToken } from "../utils/token";

export default function Login() {
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const handleLogin = async () => {
    if (!email.trim() || !senha.trim()) {
      Alert.alert("Atenção", "Por favor, preencha o e-mail e a senha.");
      return;
    }
    setLoading(true);
    try {
      const response = await api.post("/auth/login", {
        email: email.trim().toLowerCase(),
        senha: senha,
      });

      const { token } = response.data;
      await saveToken(token);
      router.replace("/home");
    } catch (error: any) {
      if (error.response) {
        const status = error.response.status;
        const mensagemErro = error.response.data.error;
        if (status === 403)
          Alert.alert("Verificação Necessária 🔒", mensagemErro);
        else if (status === 401)
          Alert.alert("Falha no Login", "E-mail ou senha incorretos.");
        else
          Alert.alert("Erro", mensagemErro || "Ocorreu um erro no servidor.");
      } else {
        Alert.alert(
          "Erro de Conexão",
          "Não foi possível contactar o servidor. Verifique o seu IP.",
        );
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Litro de Ouro ⛽</Text>
      <Text style={styles.subtitle}>O mapa dos melhores preços</Text>

      <TextInput
        style={styles.input}
        placeholder="O seu e-mail"
        value={email}
        onChangeText={setEmail}
        keyboardType="email-address"
        autoCapitalize="none"
      />

      <TextInput
        style={styles.input}
        placeholder="A sua senha"
        value={senha}
        onChangeText={setSenha}
        secureTextEntry
      />

      <TouchableOpacity
        style={[styles.button, loading && styles.buttonDisabled]}
        onPress={handleLogin}
        disabled={loading}
      >
        {loading ? (
          <ActivityIndicator color="#1F2937" />
        ) : (
          <Text style={styles.buttonText}>Entrar</Text>
        )}
      </TouchableOpacity>

      {/* NOVO BOTÃO: ESQUECI A SENHA */}
      <TouchableOpacity
        onPress={() => router.push("/recuperar-senha")}
        style={styles.forgotButton}
      >
        <Text style={styles.forgotText}>Esqueci a minha senha</Text>
      </TouchableOpacity>

      <TouchableOpacity
        onPress={() => router.push("/registrar")}
        style={styles.linkButton}
      >
        <Text style={styles.linkText}>
          Não tem conta? Crie uma aqui gratuitamente.
        </Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 20,
    justifyContent: "center",
    backgroundColor: "#F9FAFB",
  },
  title: {
    fontSize: 32,
    fontWeight: "900",
    color: "#1F2937",
    textAlign: "center",
  },
  subtitle: {
    fontSize: 16,
    color: "#4B5563",
    textAlign: "center",
    marginBottom: 40,
  },
  input: {
    backgroundColor: "#FFFFFF",
    padding: 15,
    borderRadius: 8,
    marginBottom: 15,
    borderWidth: 1,
    borderColor: "#E5E7EB",
  },
  button: {
    backgroundColor: "#FACC15",
    padding: 15,
    borderRadius: 8,
    alignItems: "center",
    marginTop: 10,
  },
  buttonDisabled: { opacity: 0.7 },
  buttonText: { color: "#1F2937", fontWeight: "bold", fontSize: 16 },
  forgotButton: { marginTop: 25, alignItems: "center" },
  forgotText: { color: "#208AEF", fontSize: 14, fontWeight: "bold" },
  linkButton: { marginTop: 20, alignItems: "center" },
  linkText: { color: "#4B5563", fontSize: 14, textDecorationLine: "underline" },
});
