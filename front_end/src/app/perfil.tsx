import { Ionicons } from "@expo/vector-icons";
import { Stack, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { api } from "../services/API";
import { removeToken } from "../utils/token";

export default function PerfilScreen() {
  const router = useRouter();

  // Estado original
  const [perfil, setPerfil] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Estados de edição
  const [editNome, setEditNome] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editSenha, setEditSenha] = useState("");

  // Controles de interface
  const [campoAtivo, setCampoAtivo] = useState<string | null>(null);

  useEffect(() => {
    carregarPerfil();
  }, []);

  const carregarPerfil = async () => {
    try {
      const response = await api.get("/auth/perfil");
      setPerfil(response.data);
      setEditNome(response.data.nome);
      setEditEmail(response.data.email);
    } catch (error) {
      Alert.alert("Sessão Expirada", "Faça login novamente.");
      handleLogout();
    } finally {
      setLoading(false);
    }
  };

  const handleSalvarAlteracoes = async () => {
    try {
      setSaving(true);
      const payload: any = {};

      if (editNome !== perfil.nome) payload.nome = editNome;
      if (editEmail !== perfil.email) payload.email = editEmail.trim();
      if (editSenha) payload.senha = editSenha;

      if (Object.keys(payload).length === 0) {
        setCampoAtivo(null);
        return; // Nada mudou
      }

      await api.put("/auth/perfil", payload);

      Alert.alert("Sucesso", "Perfil atualizado com sucesso!");
      setCampoAtivo(null);
      setEditSenha(""); // Limpa o campo de senha após salvar
      carregarPerfil(); // Recarrega os dados fresquinhos do banco
    } catch (error: any) {
      const msgErro =
        error.response?.data?.error || "Erro ao salvar alterações.";
      Alert.alert("Erro", msgErro);
    } finally {
      setSaving(false);
    }
  };

  const handleLogout = async () => {
    try {
      await removeToken();
      if (Platform.OS === "web") {
        window.location.href = "/";
      } else {
        router.replace("/");
      }
    } catch (error) {
      Alert.alert("Erro", "Não foi possível sair da conta.");
    }
  };

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#d79b00" />
      </View>
    );
  }

  // Componente Reutilizável inspirado na Imagem (Settings List Pattern)
  const SettingItem = ({
    title,
    description,
    value,
    onChange,
    field,
    isSecure = false,
    placeholder = "",
  }: any) => {
    const isEditing = campoAtivo === field;

    return (
      <View style={styles.settingRow}>
        {/* Esquerda: Textos */}
        <View style={styles.settingTextContainer}>
          <Text style={styles.settingTitle}>{title}</Text>
          <Text style={styles.settingDescription}>{description}</Text>
        </View>

        {/* Direita: Input e Botão Editar */}
        <View style={styles.settingInputContainer}>
          <TextInput
            style={[styles.input, isEditing && styles.inputActive]}
            value={value}
            onChangeText={onChange}
            editable={isEditing}
            secureTextEntry={isSecure && !isEditing} // Esconde se for senha e não estiver a editar
            placeholder={placeholder}
            placeholderTextColor="#999"
          />
          <TouchableOpacity
            style={styles.editBtn}
            onPress={() => setCampoAtivo(isEditing ? null : field)}
          >
            <Ionicons
              name={isEditing ? "close-outline" : "pencil-outline"}
              size={20}
              color="#666"
            />
            <Text style={styles.editBtnText}>
              {isEditing ? "Cancelar" : "Edit"}
            </Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  };

  return (
    <>
      <Stack.Screen options={{ headerShown: false }} />

      <ScrollView style={styles.container}>
        <View style={styles.header}>
          <TouchableOpacity
            style={styles.btnVoltar}
            onPress={() => router.back()}
          >
            <Ionicons name="arrow-back" size={28} color="#333" />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Configurações de Conta</Text>
        </View>

        {/* Estatísticas e Status da Conta (Cabeçalho Reduzido) */}
        <View style={styles.statusRow}>
          <View style={styles.statusBadge}>
            <Ionicons
              name="star"
              size={16}
              color="#d79b00"
              style={{ marginRight: 4 }}
            />
            <Text style={styles.statusText}>{perfil?.karma} Karma</Text>
          </View>
          <View
            style={[
              styles.statusBadge,
              { backgroundColor: "#EBF4FF", borderColor: "#208AEF" },
            ]}
          >
            <Ionicons
              name="shield-checkmark"
              size={16}
              color="#208AEF"
              style={{ marginRight: 4 }}
            />
            <Text style={[styles.statusText, { color: "#208AEF" }]}>
              Plano {perfil?.plano || "Grátis"}
            </Text>
          </View>
        </View>

        <View style={styles.settingsSection}>
          <SettingItem
            title="Nome Público"
            description="Nome visível na comunidade do Litro de Ouro."
            value={editNome}
            onChange={setEditNome}
            field="nome"
          />

          <SettingItem
            title="Endereço de E-mail"
            description="Usado para autenticação e recuperação de conta."
            value={editEmail}
            onChange={setEditEmail}
            field="email"
          />

          <SettingItem
            title="Alterar Senha"
            description="A Render codifica e protege a sua senha automaticamente."
            value={editSenha}
            onChange={setEditSenha}
            field="senha"
            isSecure={true}
            placeholder="Digite nova senha"
          />
        </View>

        {/* Botão de Salvar Global (Aparece apenas se algo foi alterado) */}
        {(editNome !== perfil.nome ||
          editEmail !== perfil.email ||
          editSenha !== "") && (
          <TouchableOpacity
            style={styles.btnSaveGlobal}
            onPress={handleSalvarAlteracoes}
            disabled={saving}
          >
            {saving ? (
              <ActivityIndicator color="#FFF" />
            ) : (
              <Text style={styles.btnSaveGlobalText}>Salvar Alterações</Text>
            )}
          </TouchableOpacity>
        )}

        <TouchableOpacity style={styles.btnLogout} onPress={handleLogout}>
          <Ionicons name="log-out-outline" size={22} color="#FFF" />
          <Text style={styles.btnLogoutText}>Sair da Conta</Text>
        </TouchableOpacity>
      </ScrollView>
    </>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#FAFAFA" },
  loadingContainer: { flex: 1, justifyContent: "center", alignItems: "center" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 20,
    paddingTop: 50,
    paddingBottom: 20,
    backgroundColor: "#FFF",
    borderBottomWidth: 1,
    borderColor: "#E2E8F0",
  },
  btnVoltar: {
    width: 40,
    height: 40,
    justifyContent: "center",
    marginRight: 10,
  },
  headerTitle: { fontSize: 22, fontWeight: "bold", color: "#333" },

  statusRow: {
    flexDirection: "row",
    paddingHorizontal: 20,
    paddingVertical: 15,
    borderBottomWidth: 1,
    borderColor: "#F0F0F0",
  },
  statusBadge: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#FFF9E6",
    borderWidth: 1,
    borderColor: "#d79b00",
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 15,
    marginRight: 10,
  },
  statusText: { fontSize: 13, fontWeight: "bold", color: "#d79b00" },

  settingsSection: { marginTop: 10 },

  // Estilo inspirado na imagem (Render Dashboard)
  settingRow: {
    flexDirection: Platform.OS === "web" ? "row" : "column",
    justifyContent: "space-between",
    padding: 20,
    borderBottomWidth: 1,
    borderColor: "#F0F0F0",
    backgroundColor: "#FFF",
  },
  settingTextContainer: {
    flex: 1,
    paddingRight: Platform.OS === "web" ? 40 : 0,
    marginBottom: Platform.OS === "web" ? 0 : 15,
  },
  settingTitle: {
    fontSize: 16,
    fontWeight: "bold",
    color: "#222",
    marginBottom: 6,
  },
  settingDescription: { fontSize: 13, color: "#666", lineHeight: 18 },

  settingInputContainer: {
    flex: Platform.OS === "web" ? 1.5 : 1,
    flexDirection: "row",
    alignItems: "center",
  },
  input: {
    flex: 1,
    height: 44,
    backgroundColor: "#F9F9F9",
    borderWidth: 1,
    borderColor: "#EAEAEA",
    borderRadius: 6,
    paddingHorizontal: 12,
    color: "#333",
    fontSize: 14,
  },
  inputActive: {
    backgroundColor: "#FFF",
    borderColor: "#208AEF",
    shadowColor: "#208AEF",
    shadowOpacity: 0.1,
    shadowRadius: 3,
    elevation: 1,
  },

  editBtn: { flexDirection: "row", alignItems: "center", paddingLeft: 15 },
  editBtnText: { color: "#666", fontSize: 14, marginLeft: 4 },

  btnSaveGlobal: {
    backgroundColor: "#208AEF",
    marginHorizontal: 20,
    marginTop: 30,
    paddingVertical: 14,
    borderRadius: 8,
    alignItems: "center",
    shadowColor: "#208AEF",
    shadowOpacity: 0.3,
    shadowRadius: 5,
    elevation: 3,
  },
  btnSaveGlobalText: { color: "#FFF", fontSize: 16, fontWeight: "bold" },

  btnLogout: {
    flexDirection: "row",
    marginHorizontal: 20,
    marginTop: 40,
    marginBottom: 50,
    paddingVertical: 14,
    borderRadius: 8,
    justifyContent: "center",
    alignItems: "center",
    borderWidth: 1,
    borderColor: "#E63946",
    backgroundColor: "#FFF",
  },
  btnLogoutText: {
    color: "#E63946",
    fontSize: 16,
    fontWeight: "bold",
    marginLeft: 10,
  },
});
