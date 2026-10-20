import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
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
import { api } from "../services/API";
import { deleteToken } from "../utils/token";

export default function PerfilScreen() {
  const router = useRouter();

  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [plano, setPlano] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const fetchPerfil = async () => {
      try {
        // O Axios injeta o token automaticamente via Interceptor!
        const response = await api.get("/auth/perfil");

        setNome(response.data.nome);
        setEmail(response.data.email);
        setPlano(response.data.plano || "Gratuito");
      } catch (error: any) {
        if (error.response?.status === 401) {
          Alert.alert("Sessão Expirada", "Faça login novamente.");
          router.replace("/login");
        } else {
          Alert.alert("Erro", "Não foi possível carregar o perfil.");
        }
      } finally {
        setLoading(false);
      }
    };

    fetchPerfil();
  }, []);

  const handleUpdate = async () => {
    if (!nome) {
      Alert.alert("Atenção", "O nome não pode estar vazio.");
      return;
    }

    setSaving(true);
    try {
      await api.put("/auth/perfil", { nome });
      Alert.alert("Sucesso", "Perfil atualizado com sucesso!");
    } catch (error: any) {
      Alert.alert(
        "Erro",
        error.response?.data?.error || "Não foi possível atualizar o perfil.",
      );
    } finally {
      setSaving(false);
    }
  };

  const handleLogout = async () => {
    await deleteToken();
    router.replace("/");
  };

  if (loading) {
    return (
      <View
        style={[
          styles.container,
          { justifyContent: "center", alignItems: "center" },
        ]}
      >
        <ActivityIndicator size="large" color="#d79b00" />
      </View>
    );
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : "height"}
    >
      <View style={styles.header}>
        <TouchableOpacity
          style={styles.backButton}
          onPress={() => router.replace("/")}
        >
          <Ionicons name="arrow-back" size={28} color="#333" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Meu Perfil</Text>
        <TouchableOpacity onPress={handleLogout} style={styles.logoutBtn}>
          <Ionicons name="log-out-outline" size={26} color="#E53935" />
        </TouchableOpacity>
      </View>

      <View style={styles.content}>
        <View style={styles.avatarContainer}>
          <Ionicons name="person-circle-outline" size={100} color="#d79b00" />
          <View style={styles.badgeContainer}>
            <Text style={styles.badgeText}>Plano {plano}</Text>
          </View>
        </View>

        <View style={styles.form}>
          <Text style={styles.label}>Nome Completo</Text>
          <View style={styles.inputContainer}>
            <Ionicons
              name="person-outline"
              size={20}
              color="#666"
              style={styles.inputIcon}
            />
            <TextInput
              style={styles.input}
              value={nome}
              onChangeText={setNome}
              autoCapitalize="words"
            />
          </View>

          <Text style={styles.label}>Email (Apenas Leitura)</Text>
          <View style={[styles.inputContainer, styles.inputDisabled]}>
            <Ionicons
              name="mail-outline"
              size={20}
              color="#999"
              style={styles.inputIcon}
            />
            <TextInput
              style={[styles.input, { color: "#999" }]}
              value={email}
              editable={false}
            />
          </View>

          <TouchableOpacity
            style={[styles.saveBtn, saving && styles.saveBtnDisabled]}
            activeOpacity={0.8}
            onPress={handleUpdate}
            disabled={saving}
          >
            {saving ? (
              <ActivityIndicator color="#FFF" />
            ) : (
              <Text style={styles.saveBtnText}>Guardar Alterações</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

// Estilos preservados
const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#FFF" },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingTop: Platform.OS === "ios" ? 50 : 30,
    paddingHorizontal: 20,
    paddingBottom: 15,
    borderBottomWidth: 1,
    borderBottomColor: "#eee",
  },
  backButton: { width: 40, height: 40, justifyContent: "center" },
  headerTitle: { fontSize: 20, fontWeight: "bold", color: "#333" },
  logoutBtn: {
    width: 40,
    height: 40,
    justifyContent: "center",
    alignItems: "flex-end",
  },
  content: { flex: 1, paddingHorizontal: 30, paddingTop: 30 },
  avatarContainer: { alignItems: "center", marginBottom: 40 },
  badgeContainer: {
    backgroundColor: "#FFF9C4",
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 20,
    marginTop: -15,
    borderWidth: 1,
    borderColor: "#FBC02D",
  },
  badgeText: {
    color: "#F57F17",
    fontWeight: "bold",
    fontSize: 12,
    textTransform: "capitalize",
  },
  form: { width: "100%" },
  label: {
    fontSize: 14,
    fontWeight: "bold",
    color: "#666",
    marginBottom: 8,
    marginLeft: 5,
  },
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
  inputDisabled: { backgroundColor: "#EFEFEF", borderColor: "#DDD" },
  inputIcon: { marginRight: 10 },
  input: { flex: 1, height: "100%", color: "#333", fontSize: 16 },
  saveBtn: {
    backgroundColor: "#d79b00",
    height: 55,
    borderRadius: 10,
    justifyContent: "center",
    alignItems: "center",
    marginTop: 10,
    elevation: 3,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 3,
  },
  saveBtnDisabled: { backgroundColor: "#e8c366", elevation: 0 },
  saveBtnText: { color: "#FFF", fontSize: 18, fontWeight: "bold" },
});
