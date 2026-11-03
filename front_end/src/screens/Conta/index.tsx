// src/screens/Conta/index.tsx
import { useFocusEffect, useNavigation } from "@react-navigation/native";
import { useCallback, useContext, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";

import { AuthContext } from "../../contexts/AuthContext";
import { ThemeContext } from "../../contexts/ThemeContext";
import { api } from "../../services/API";

interface PerfilUsuario {
  nome: string;
  email: string;
  plano: string;
  karma: number;
  membro_desde: string;
}

export default function Conta() {
  const { colors } = useContext(ThemeContext) as any;
  const { signOut } = useContext(AuthContext);
  const navigation = useNavigation();

  const [perfil, setPerfil] = useState<PerfilUsuario | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  useFocusEffect(
    useCallback(() => {
      carregarPerfil();
    }, []),
  );

  const carregarPerfil = async () => {
    setIsLoading(true);
    try {
      const response = await api.get("/auth/perfil");
      setPerfil(response.data);
    } catch (error: any) {
      console.error("Erro ao carregar perfil:", error);
      if (error.response?.status === 401) {
        signOut();
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleLogout = async () => {
    if (Platform.OS === "web") {
      // Na Web, o Alert.alert não executa botões. Usamos a confirmação nativa da Web:
      const confirmou = window.confirm("Tem a certeza de que deseja sair?");
      if (confirmou) {
        setIsLoggingOut(true);
        await signOut();
      }
    } else {
      // No iOS/Android, o Alert.alert funciona perfeitamente:
      Alert.alert("Terminar Sessão", "Tem a certeza de que deseja sair?", [
        { text: "Cancelar", style: "cancel" },
        {
          text: "Sair",
          style: "destructive",
          onPress: async () => {
            setIsLoggingOut(true);
            await signOut();
          },
        },
      ]);
    }
  };

  if (isLoading) {
    return (
      <View
        style={[
          styles.center,
          { backgroundColor: colors?.background || "#121212" },
        ]}
      >
        <ActivityIndicator size="large" color={colors?.primary || "#F59E0B"} />
      </View>
    );
  }

  if (!perfil) {
    return (
      <View
        style={[
          styles.center,
          { backgroundColor: colors?.background || "#121212" },
        ]}
      >
        <Text style={{ color: colors?.textSecondary || "#A1A1AA" }}>
          Não foi possível carregar o perfil.
        </Text>
        <TouchableOpacity style={{ marginTop: 16 }} onPress={handleLogout}>
          <Text
            style={{ color: colors?.primary || "#F59E0B", fontWeight: "bold" }}
          >
            Voltar ao Login
          </Text>
        </TouchableOpacity>
      </View>
    );
  }

  const iniciais = perfil.nome
    ? perfil.nome
        .split(" ")
        .slice(0, 2)
        .map((n) => n[0])
        .join("")
        .toUpperCase()
    : "U";

  return (
    <ScrollView
      style={[
        styles.container,
        { backgroundColor: colors?.background || "#121212" },
      ]}
    >
      <View style={styles.header}>
        <Text
          style={[styles.title, { color: colors?.textPrimary || "#FFFFFF" }]}
        >
          Meu Perfil
        </Text>
      </View>

      <View
        style={[
          styles.card,
          {
            backgroundColor: colors?.surface || "#1E1E1E",
            borderColor: colors?.border || "#333333",
          },
        ]}
      >
        <View style={styles.profileHeader}>
          <View
            style={[
              styles.avatar,
              { backgroundColor: colors?.primary || "#F59E0B" },
            ]}
          >
            <Text style={styles.avatarText}>{iniciais}</Text>
          </View>
          <View style={styles.profileInfo}>
            <Text
              style={[styles.name, { color: colors?.textPrimary || "#FFFFFF" }]}
            >
              {perfil.nome}
            </Text>
            <Text style={{ color: colors?.textSecondary || "#A1A1AA" }}>
              {perfil.email}
            </Text>
          </View>
        </View>

        <View style={styles.divider} />

        <View style={styles.statsRow}>
          <View style={styles.statItem}>
            <Text
              style={[
                styles.statValue,
                { color: colors?.primary || "#F59E0B" },
              ]}
            >
              {perfil.karma}
            </Text>
            <Text
              style={{
                color: colors?.textSecondary || "#A1A1AA",
                fontSize: 12,
              }}
            >
              Karma 🏆
            </Text>
          </View>
          <View style={styles.statItem}>
            <Text
              style={[
                styles.statValue,
                { color: colors?.textPrimary || "#FFFFFF" },
              ]}
            >
              {perfil.plano === "gratis" ? "Grátis" : "Premium"}
            </Text>
            <Text
              style={{
                color: colors?.textSecondary || "#A1A1AA",
                fontSize: 12,
              }}
            >
              Plano
            </Text>
          </View>
          <View style={styles.statItem}>
            <Text
              style={[
                styles.statValue,
                {
                  color: colors?.textPrimary || "#FFFFFF",
                  fontSize: 14,
                  marginTop: 4,
                },
              ]}
            >
              {perfil.membro_desde}
            </Text>
            <Text
              style={{
                color: colors?.textSecondary || "#A1A1AA",
                fontSize: 12,
              }}
            >
              Membro desde
            </Text>
          </View>
        </View>
      </View>

      <View style={styles.menuContainer}>
        <TouchableOpacity
          style={[
            styles.menuItem,
            { borderBottomColor: colors?.border || "#333333" },
          ]}
          onPress={() => navigation.navigate("Definicoes" as never)}
        >
          <Text
            style={[
              styles.menuText,
              { color: colors?.textPrimary || "#FFFFFF" },
            ]}
          >
            ⚙️ Definições da Conta
          </Text>
          <Text style={{ color: colors?.textSecondary || "#A1A1AA" }}>›</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[
            styles.menuItem,
            { borderBottomColor: colors?.border || "#333333" },
          ]}
          onPress={() => navigation.navigate("Notificacoes" as never)}
        >
          <Text
            style={[
              styles.menuText,
              { color: colors?.textPrimary || "#FFFFFF" },
            ]}
          >
            🔔 Notificações
          </Text>
          <Text style={{ color: colors?.textSecondary || "#A1A1AA" }}>›</Text>
        </TouchableOpacity>
      </View>

      {/* BOTÃO COM FEEDBACK VISUAL DE CARREGAMENTO */}
      <TouchableOpacity
        style={[
          styles.btnLogout,
          {
            borderColor: colors?.border || "#333333",
            opacity: isLoggingOut ? 0.6 : 1,
          },
        ]}
        onPress={handleLogout}
        disabled={isLoggingOut}
      >
        {isLoggingOut ? (
          <ActivityIndicator color="#FF3B30" size="small" />
        ) : (
          <Text style={styles.btnLogoutText}>Terminar Sessão</Text>
        )}
      </TouchableOpacity>

      <Text
        style={[styles.versionText, { color: colors?.border || "#333333" }]}
      >
        Litro de Ouro v1.0
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, justifyContent: "center", alignItems: "center" },
  container: { flex: 1, paddingHorizontal: 20 },
  header: { paddingTop: 60, paddingBottom: 24 },
  title: { fontSize: 28, fontWeight: "bold" },
  card: { borderRadius: 16, borderWidth: 1, padding: 20, marginBottom: 24 },
  profileHeader: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: 20,
  },
  avatar: {
    width: 64,
    height: 64,
    borderRadius: 32,
    justifyContent: "center",
    alignItems: "center",
    marginRight: 16,
  },
  avatarText: { color: "#121212", fontSize: 24, fontWeight: "bold" },
  profileInfo: { flex: 1 },
  name: { fontSize: 20, fontWeight: "bold", marginBottom: 4 },
  divider: { height: 1, backgroundColor: "#333", marginBottom: 20 },
  statsRow: { flexDirection: "row", justifyContent: "space-between" },
  statItem: { alignItems: "center", flex: 1 },
  statValue: { fontSize: 20, fontWeight: "bold", marginBottom: 4 },
  menuContainer: { marginBottom: 32 },
  menuItem: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 16,
    borderBottomWidth: 1,
  },
  menuText: { fontSize: 16, fontWeight: "500" },
  btnLogout: {
    paddingVertical: 16,
    borderRadius: 12,
    borderWidth: 1,
    alignItems: "center",
    backgroundColor: "#FF3B3015",
  },
  btnLogoutText: { color: "#FF3B30", fontSize: 16, fontWeight: "bold" },
  versionText: {
    textAlign: "center",
    marginTop: 24,
    marginBottom: 40,
    fontSize: 12,
  },
});
