import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  FlatList,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { api } from "../services/API"; // A nossa ligação ao Render

// Adicione isto por baixo dos imports
interface PostoPreco {
  id: string | number;
  nome: string;
  preco: number;
  distancia: string;
}

export default function MenorPrecoScreen() {
  const router = useRouter();

  // Nomes exatos conforme a sua base de dados exige
  const [filtroAtivo, setFiltroAtivo] = useState("Gasolina Comum");

  // Substituímos os DADOS_SIMULADOS por um estado que começa vazio
  // Altere esta linha:
  const [dadosReais, setDadosReais] = useState<PostoPreco[]>([]);
  const [loading, setLoading] = useState(true);

  // Executa sempre que o ecrã abre e sempre que o utilizador muda o filtro
  useEffect(() => {
    buscarMenoresPrecos();
  }, [filtroAtivo]);

  const buscarMenoresPrecos = async () => {
    setLoading(true);
    try {
      // Ajuste esta rota para o endpoint GET correto que criou no backend Flask
      const response = await api.get(
        `/postos/menores-precos?tipo_combustivel=${filtroAtivo}`,
      );
      setDadosReais(response.data);
    } catch (error) {
      console.error(error);
      Alert.alert("Erro", "Não foi possível carregar os preços atualizados.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity
          onPress={() => router.back()}
          style={styles.backButton}
        >
          <Ionicons name="arrow-back" size={28} color="#333" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Menor Preço</Text>
        <View style={{ width: 28 }} />
      </View>

      <View style={styles.filtrosContainer}>
        {["Gasolina Comum", "Etanol", "Diesel"].map((tipo) => (
          <TouchableOpacity
            key={tipo}
            style={[
              styles.filtroBtn,
              filtroAtivo === tipo && styles.filtroBtnAtivo,
            ]}
            onPress={() => setFiltroAtivo(tipo)}
          >
            <Text
              style={[
                styles.filtroText,
                filtroAtivo === tipo && styles.filtroTextAtivo,
              ]}
            >
              {tipo === "Gasolina Comum" ? "Gasolina" : tipo}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Se estiver a carregar a API, mostra a roda a girar. Se não, mostra a lista real */}
      {loading ? (
        <View
          style={{ flex: 1, justifyContent: "center", alignItems: "center" }}
        >
          <ActivityIndicator size="large" color="#d79b00" />
        </View>
      ) : (
        <FlatList
          data={dadosReais}
          keyExtractor={(item) => item.id.toString()}
          contentContainerStyle={styles.listContainer}
          renderItem={({ item, index }) => (
            <View style={styles.card}>
              <View style={styles.rankContainer}>
                <Text style={styles.rankText}>{index + 1}º</Text>
              </View>
              <View style={styles.infoContainer}>
                <Text style={styles.nomePosto}>{item.nome}</Text>
                <Text style={styles.distanciaText}>
                  <Ionicons name="location-outline" size={14} />{" "}
                  {item.distancia} • Atualizado recentemente
                </Text>
              </View>
              <View style={styles.precoContainer}>
                <Text style={styles.cifrao}>R$</Text>
                <Text style={styles.precoValor}>
                  {item.preco.toFixed(2).replace(".", ",")}
                </Text>
              </View>
            </View>
          )}
          ListEmptyComponent={() => (
            <Text style={{ textAlign: "center", marginTop: 20, color: "#888" }}>
              Nenhum preço registado para este combustível ainda.
            </Text>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  // Mantenha os seus styles originais exatos aqui para baixo...
  container: { flex: 1, backgroundColor: "#f9f9f9" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    padding: 20,
    paddingTop: 50,
    backgroundColor: "#FFF",
    borderBottomWidth: 1,
    borderColor: "#eee",
  },
  backButton: { padding: 5 },
  headerTitle: { fontSize: 18, fontWeight: "bold", color: "#333" },
  filtrosContainer: {
    flexDirection: "row",
    justifyContent: "space-around",
    padding: 15,
    backgroundColor: "#FFF",
    borderBottomWidth: 1,
    borderColor: "#eee",
  },
  filtroBtn: {
    paddingVertical: 8,
    paddingHorizontal: 20,
    borderRadius: 20,
    backgroundColor: "#f5f5f5",
  },
  filtroBtnAtivo: { backgroundColor: "#d79b00" },
  filtroText: { color: "#666", fontWeight: "600" },
  filtroTextAtivo: { color: "#FFF" },
  listContainer: { padding: 15 },
  card: {
    flexDirection: "row",
    backgroundColor: "#FFF",
    borderRadius: 12,
    padding: 15,
    marginBottom: 15,
    alignItems: "center",
    elevation: 2,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
  },
  rankContainer: { width: 40, alignItems: "center" },
  rankText: { fontSize: 18, fontWeight: "bold", color: "#d79b00" },
  infoContainer: { flex: 1, paddingHorizontal: 10 },
  nomePosto: { fontSize: 16, fontWeight: "bold", color: "#333" },
  distanciaText: { fontSize: 13, color: "#888", marginTop: 4 },
  precoContainer: { alignItems: "flex-end" },
  cifrao: { fontSize: 12, color: "#82b366", fontWeight: "bold" },
  precoValor: { fontSize: 22, fontWeight: "bold", color: "#82b366" },
});
