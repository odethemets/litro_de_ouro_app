import { Ionicons } from "@expo/vector-icons";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Stack, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { api } from "../services/API";

export default function PerfilScreen() {
  const router = useRouter();
  const [perfil, setPerfil] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    carregarPerfil();
  }, []);

  const carregarPerfil = async () => {
    try {
      const response = await api.get("/auth/perfil");
      setPerfil(response.data);
    } catch (error) {
      Alert.alert("Sessão Expirada", "Por favor, faça login novamente.");
      await handleLogout();
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = async () => {
    await AsyncStorage.removeItem("token");
    router.replace("/");
  };

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#d79b00" />
      </View>
    );
  }

  return (
    <>
      {/* CORREÇÃO: Remove o cabeçalho duplicado */}
      <Stack.Screen options={{ headerShown: false }} />

      <View style={styles.container}>
        <View style={styles.headerTop}>
          <TouchableOpacity
            style={styles.btnVoltar}
            onPress={() => router.back()}
          >
            <Ionicons name="arrow-back" size={28} color="#333" />
          </TouchableOpacity>
        </View>

        <View style={styles.profileHeader}>
          <View style={styles.avatarContainer}>
            <Ionicons name="person" size={55} color="#FFF" />
          </View>
          <Text style={styles.nome}>{perfil?.nome || "Utilizador"}</Text>
          <Text style={styles.email}>{perfil?.email || "email@teste.com"}</Text>
        </View>

        {/* CORREÇÃO: Mais margem superior para descolar da foto */}
        <View style={styles.statsContainer}>
          <View style={styles.statBox}>
            <Ionicons name="star" size={30} color="#d79b00" />
            <Text style={styles.statValue}>{perfil?.karma || 0}</Text>
            <Text style={styles.statLabel}>Karma</Text>
          </View>

          <View style={styles.statBox}>
            <Ionicons name="shield-checkmark" size={30} color="#208AEF" />
            <Text style={styles.statValue}>{perfil?.plano || "Grátis"}</Text>
            <Text style={styles.statLabel}>Plano</Text>
          </View>
        </View>

        <TouchableOpacity style={styles.btnLogout} onPress={handleLogout}>
          <Ionicons name="log-out-outline" size={22} color="#FFF" />
          <Text style={styles.btnLogoutText}>Sair da Conta</Text>
        </TouchableOpacity>
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#F8F9FA" },
  loadingContainer: { flex: 1, justifyContent: "center", alignItems: "center" },
  headerTop: { paddingHorizontal: 20, paddingTop: 50, paddingBottom: 10 },
  btnVoltar: { width: 40, height: 40, justifyContent: "center" },
  profileHeader: { alignItems: "center", marginBottom: 40 },
  avatarContainer: {
    width: 110,
    height: 110,
    borderRadius: 55,
    backgroundColor: "#d79b00",
    justifyContent: "center",
    alignItems: "center",
    marginBottom: 15,
    shadowColor: "#d79b00",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 6,
    elevation: 5,
  },
  nome: { fontSize: 26, fontWeight: "bold", color: "#333" },
  email: { fontSize: 16, color: "#666", marginTop: 4 },
  statsContainer: {
    flexDirection: "row",
    justifyContent: "space-evenly",
    paddingHorizontal: 20,
    marginBottom: 50,
  },
  statBox: {
    backgroundColor: "#FFF",
    width: "42%",
    paddingVertical: 25,
    borderRadius: 15,
    alignItems: "center",
    borderWidth: 1,
    borderColor: "#E2E8F0",
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  statValue: { fontSize: 22, fontWeight: "bold", color: "#333", marginTop: 10 },
  statLabel: { fontSize: 14, color: "#666", marginTop: 4, fontWeight: "500" },
  btnLogout: {
    flexDirection: "row",
    backgroundColor: "#E63946",
    marginHorizontal: 30,
    paddingVertical: 15,
    borderRadius: 12,
    justifyContent: "center",
    alignItems: "center",
    shadowColor: "#E63946",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 5,
    elevation: 4,
  },
  btnLogoutText: {
    color: "#FFF",
    fontSize: 18,
    fontWeight: "bold",
    marginLeft: 10,
  },
});
