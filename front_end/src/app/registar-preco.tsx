import { Ionicons } from "@expo/vector-icons";
import * as Location from "expo-location";
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
    View,
} from "react-native";

export default function RegistarPrecoScreen() {
  const router = useRouter();
  const [preco, setPreco] = useState("");
  const [tipoCombustivel, setTipoCombustivel] = useState("Gasolina Comum");
  const [loading, setLoading] = useState(false);

  const tipos = ["Gasolina Comum", "Etanol", "Diesel"];

  const handleSubmeterPreco = async () => {
    if (!preco) {
      Alert.alert("Erro", "Por favor, introduza um preço válido.");
      return;
    }

    setLoading(true);
    try {
      // Captura a localização exata no momento do clique para enviar à API
      const location = await Location.getCurrentPositionAsync({});

      // Aqui entrará a chamada real à sua API Flask:
      // await api.post('/precos', {
      //   posto_id: 1,
      //   tipo: tipoCombustivel,
      //   preco: parseFloat(preco),
      //   latitude: location.coords.latitude,
      //   longitude: location.coords.longitude
      // });

      Alert.alert(
        "Sucesso",
        "Preço registado! A nossa API validou a sua distância com sucesso.",
      );
      router.back(); // Volta para o mapa
    } catch (error) {
      Alert.alert(
        "Erro",
        "Está demasiado longe do posto (Erro 403) ou ocorreu um problema.",
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
          onPress={() => router.back()}
          style={styles.backButton}
        >
          <Ionicons name="arrow-back" size={28} color="#333" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Registar Novo Preço</Text>
        <View style={{ width: 28 }} />
      </View>

      <View style={styles.content}>
        <Text style={styles.label}>Posto Selecionado</Text>
        <View style={styles.postoCard}>
          <Ionicons name="business" size={24} color="#d79b00" />
          <Text style={styles.postoNome}>Posto Epitácio</Text>
        </View>

        <Text style={styles.label}>Tipo de Combustível</Text>
        <View style={styles.tiposContainer}>
          {tipos.map((tipo) => (
            <TouchableOpacity
              key={tipo}
              style={[
                styles.tipoBadge,
                tipoCombustivel === tipo && styles.tipoBadgeAtivo,
              ]}
              onPress={() => setTipoCombustivel(tipo)}
            >
              <Text
                style={[
                  styles.tipoText,
                  tipoCombustivel === tipo && styles.tipoTextAtivo,
                ]}
              >
                {tipo}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <Text style={styles.label}>Preço Atualizado (R$)</Text>
        <TextInput
          style={styles.inputPreco}
          keyboardType="decimal-pad"
          placeholder="Ex: 5,89"
          value={preco}
          onChangeText={setPreco}
          maxLength={5}
        />

        <TouchableOpacity
          style={[styles.btnSubmit, loading && { opacity: 0.7 }]}
          onPress={handleSubmeterPreco}
          disabled={loading}
        >
          <Text style={styles.btnSubmitText}>
            {loading ? "A validar localização..." : "Publicar Preço"}
          </Text>
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#FFF" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    padding: 20,
    paddingTop: 50,
    backgroundColor: "#f9f9f9",
    borderBottomWidth: 1,
    borderColor: "#eee",
  },
  backButton: { padding: 5 },
  headerTitle: { fontSize: 18, fontWeight: "bold", color: "#333" },
  content: { padding: 20 },
  label: {
    fontSize: 16,
    fontWeight: "600",
    color: "#555",
    marginTop: 20,
    marginBottom: 10,
  },
  postoCard: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#fff2cc",
    padding: 15,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "#d6b656",
  },
  postoNome: {
    fontSize: 18,
    fontWeight: "bold",
    marginLeft: 10,
    color: "#333",
  },
  tiposContainer: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  tipoBadge: {
    paddingVertical: 10,
    paddingHorizontal: 15,
    borderRadius: 20,
    backgroundColor: "#f5f5f5",
    borderWidth: 1,
    borderColor: "#ddd",
  },
  tipoBadgeAtivo: { backgroundColor: "#333", borderColor: "#333" },
  tipoText: { color: "#666", fontWeight: "500" },
  tipoTextAtivo: { color: "#FFF" },
  inputPreco: {
    fontSize: 40,
    fontWeight: "bold",
    color: "#82b366",
    textAlign: "center",
    borderBottomWidth: 2,
    borderColor: "#ddd",
    paddingVertical: 15,
    marginBottom: 30,
  },
  btnSubmit: {
    backgroundColor: "#d79b00",
    paddingVertical: 15,
    borderRadius: 10,
    alignItems: "center",
    elevation: 2,
  },
  btnSubmitText: { color: "#FFF", fontSize: 18, fontWeight: "bold" },
});
