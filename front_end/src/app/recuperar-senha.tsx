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

export default function RecuperarSenhaScreen() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);

  const handleRecuperar = async () => {
    if (!email) {
      Alert.alert("Atenção", "Por favor, introduza o seu email.");
      return;
    }

    setLoading(true);

    try {
      // IMPORTANTE: Substitua pelo IP da sua máquina
      const API_URL =
        Platform.OS === "web"
          ? "https://litro-de-ouro-app.onrender.com"
          : "https://litro-de-ouro-app.onrender.com";

      const response = await fetch(`${API_URL}/auth/recuperar-senha`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });

      const data = await response.json();

      Alert.alert("Recuperação", data.message);
      router.back(); // Volta ao ecrã anterior
    } catch (error: any) {
      Alert.alert("Erro", "Não foi possível conectar ao servidor.");
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
        <Ionicons
          name="key-outline"
          size={60}
          color="#d79b00"
          style={{ marginBottom: 20 }}
        />
        <Text style={styles.title}>Recuperar Senha</Text>
        <Text style={styles.subtitle}>
          Insira o email associado à sua conta para receber as instruções de
          recuperação.
        </Text>

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
              editable={!loading}
            />
          </View>

          <TouchableOpacity
            style={[styles.btnAction, loading && styles.btnDisabled]}
            activeOpacity={0.8}
            onPress={handleRecuperar}
            disabled={loading}
          >
            {loading ? (
              <ActivityIndicator color="#FFF" />
            ) : (
              <Text style={styles.btnText}>Enviar Instruções</Text>
            )}
          </TouchableOpacity>
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
  title: { fontSize: 28, fontWeight: "bold", color: "#333", marginBottom: 10 },
  subtitle: { fontSize: 16, color: "#666", marginBottom: 30, lineHeight: 22 },
  form: { width: "100%" },
  inputContainer: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#F5F5F5",
    borderRadius: 10,
    marginBottom: 25,
    paddingHorizontal: 15,
    height: 55,
    borderWidth: 1,
    borderColor: "#E0E0E0",
  },
  inputIcon: { marginRight: 10 },
  input: { flex: 1, height: "100%", color: "#333", fontSize: 16 },
  btnAction: {
    backgroundColor: "#333",
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
  btnDisabled: { backgroundColor: "#888", elevation: 0 },
  btnText: { color: "#FFF", fontSize: 18, fontWeight: "bold" },
});
