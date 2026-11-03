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
import { api } from "../services/API"; // O ficheiro que configurámos com o IP local

export default function Registrar() {
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const handleRegister = async () => {
    if (!nome.trim() || !email.trim() || !senha.trim()) {
      Alert.alert("Atenção", "Por favor, preencha todos os campos.");
      return;
    }
    if (senha.length < 6) {
      Alert.alert("Atenção", "A senha deve ter pelo menos 6 caracteres.");
      return;
    }
    setLoading(true);
    try {
      // 1. Rota corrigida para português (bate certo com o auth.py)
      const response = await api.post("/auth/registrar", {
        nome: nome.trim(),
        email: email.trim().toLowerCase(),
        senha: senha,
      });

      Alert.alert("Conta Criada! 🎉", response.data.mensagem, [
        { text: "Ir para Login", onPress: () => router.replace("/login") },
      ]);
    } catch (error: any) {
      // 2. Extração de erro corrigida (data.error em vez de data.erro)
      const mensagemErro =
        error.response?.data?.error ||
        (error.response
          ? "O servidor recusou o pedido."
          : "Não foi possível contactar o servidor. Verifique o IP e a rede.");
      Alert.alert("Falha no Registo", mensagemErro);
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Criar Conta</Text>

      <TextInput
        style={styles.input}
        placeholder="O seu nome"
        value={nome}
        onChangeText={setNome}
        autoCapitalize="words"
      />

      <TextInput
        style={styles.input}
        placeholder="E-mail (ex: joao123@email.com)"
        value={email}
        onChangeText={setEmail}
        keyboardType="email-address"
        autoCapitalize="none"
      />

      <TextInput
        style={styles.input}
        placeholder="Senha (mínimo 6 caracteres)"
        value={senha}
        onChangeText={setSenha}
        secureTextEntry
      />

      <TouchableOpacity
        style={[styles.button, loading && styles.buttonDisabled]}
        onPress={handleRegister}
        disabled={loading}
      >
        {loading ? (
          <ActivityIndicator color="#1F2937" />
        ) : (
          <Text style={styles.buttonText}>Registar</Text>
        )}
      </TouchableOpacity>

      <TouchableOpacity
        onPress={() => router.replace("/login")}
        style={styles.linkButton}
      >
        <Text style={styles.linkText}>Já tem conta? Inicie sessão aqui.</Text>
      </TouchableOpacity>
    </View>
  );
}

// Estilos básicos (pode adaptar à identidade visual amarela/escura do Litro de Ouro)
const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 20,
    justifyContent: "center",
    backgroundColor: "#F9FAFB",
  },
  title: {
    fontSize: 28,
    fontWeight: "bold",
    color: "#1F2937",
    marginBottom: 30,
    textAlign: "center",
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
  linkButton: { marginTop: 20, alignItems: "center" },
  linkText: { color: "#4B5563", fontSize: 14, textDecorationLine: "underline" },
});
