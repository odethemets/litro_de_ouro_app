import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import {
    ScrollView,
    StyleSheet,
    Text,
    TouchableOpacity,
    View
} from "react-native";

export default function PerfilScreen() {
  const router = useRouter();

  return (
    <ScrollView style={styles.container} bounces={false}>
      <View style={styles.header}>
        <TouchableOpacity
          onPress={() => router.back()}
          style={styles.backButton}
        >
          <Ionicons name="arrow-back" size={28} color="#FFF" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Meu Perfil</Text>
        <TouchableOpacity style={styles.editButton}>
          <Ionicons name="pencil" size={22} color="#FFF" />
        </TouchableOpacity>
      </View>

      <View style={styles.profileSection}>
        <View style={styles.avatarContainer}>
          <Ionicons name="person" size={50} color="#d79b00" />
        </View>
        <Text style={styles.userName}>Pedro Henrique</Text>
        <Text style={styles.userEmail}>pedro@email.com</Text>
      </View>

      <View style={styles.statsContainer}>
        <View style={styles.statBox}>
          <Text style={styles.statNumber}>12</Text>
          <Text style={styles.statLabel}>Preços Registados</Text>
        </View>
        <View style={styles.divider} />
        <View style={styles.statBox}>
          <Text style={styles.statNumber}>4</Text>
          <Text style={styles.statLabel}>Postos Validados</Text>
        </View>
      </View>

      <View style={styles.menuContainer}>
        <Text style={styles.menuTitle}>Configurações da Conta</Text>

        <TouchableOpacity style={styles.menuItem}>
          <Ionicons name="car-outline" size={24} color="#666" />
          <Text style={styles.menuItemText}>Meu Veículo</Text>
          <Ionicons name="chevron-forward" size={20} color="#ccc" />
        </TouchableOpacity>

        <TouchableOpacity style={styles.menuItem}>
          <Ionicons name="notifications-outline" size={24} color="#666" />
          <Text style={styles.menuItemText}>Notificações</Text>
          <Ionicons name="chevron-forward" size={20} color="#ccc" />
        </TouchableOpacity>

        <TouchableOpacity style={styles.menuItem}>
          <Ionicons name="shield-checkmark-outline" size={24} color="#666" />
          <Text style={styles.menuItemText}>Privacidade e Segurança</Text>
          <Ionicons name="chevron-forward" size={20} color="#ccc" />
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.menuItem, styles.logoutItem]}
          onPress={() => router.replace("/login")}
        >
          <Ionicons name="log-out-outline" size={24} color="#d9534f" />
          <Text style={styles.logoutText}>Sair da Conta</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f9f9f9" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    padding: 20,
    paddingTop: 50,
    backgroundColor: "#d79b00",
  },
  backButton: { padding: 5 },
  headerTitle: { fontSize: 18, fontWeight: "bold", color: "#FFF" },
  editButton: { padding: 5 },
  profileSection: {
    backgroundColor: "#d79b00",
    alignItems: "center",
    paddingBottom: 30,
    borderBottomLeftRadius: 30,
    borderBottomRightRadius: 30,
  },
  avatarContainer: {
    width: 100,
    height: 100,
    backgroundColor: "#FFF",
    borderRadius: 50,
    justifyContent: "center",
    alignItems: "center",
    marginBottom: 15,
    elevation: 5,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 4,
  },
  userName: { fontSize: 24, fontWeight: "bold", color: "#FFF" },
  userEmail: { fontSize: 14, color: "#ffe082", marginTop: 5 },
  statsContainer: {
    flexDirection: "row",
    backgroundColor: "#FFF",
    marginHorizontal: 20,
    marginTop: -20,
    borderRadius: 15,
    paddingVertical: 20,
    elevation: 3,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 3,
  },
  statBox: { flex: 1, alignItems: "center" },
  statNumber: { fontSize: 22, fontWeight: "bold", color: "#333" },
  statLabel: { fontSize: 12, color: "#888", marginTop: 5 },
  divider: { width: 1, backgroundColor: "#eee" },
  menuContainer: { padding: 20, marginTop: 10 },
  menuTitle: {
    fontSize: 16,
    fontWeight: "bold",
    color: "#555",
    marginBottom: 15,
  },
  menuItem: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#FFF",
    padding: 15,
    borderRadius: 12,
    marginBottom: 10,
  },
  menuItemText: { flex: 1, fontSize: 16, color: "#333", marginLeft: 15 },
  logoutItem: {
    marginTop: 20,
    borderWidth: 1,
    borderColor: "#ffebee",
    backgroundColor: "#fff5f5",
  },
  logoutText: {
    flex: 1,
    fontSize: 16,
    color: "#d9534f",
    fontWeight: "bold",
    marginLeft: 15,
  },
});
