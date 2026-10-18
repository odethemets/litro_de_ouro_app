import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useState } from "react";

import {
    FlatList,
    StyleSheet,
    Text,
    TouchableOpacity,
    View,
} from "react-native";

const DADOS_SIMULADOS = [
  {
    id: "1",
    nome: "Posto Epitácio",
    preco: 5.89,
    distancia: "450m",
    atualizado: "Há 10 min",
  },
  {
    id: "2",
    nome: "Posto Tambaú",
    preco: 5.95,
    distancia: "1.2km",
    atualizado: "Há 1 hora",
  },
  {
    id: "3",
    nome: "Posto Bancários",
    preco: 6.05,
    distancia: "3.5km",
    atualizado: "Há 2 horas",
  },
];

export default function MenorPrecoScreen() {
  const router = useRouter();
  const [filtroAtivo, setFiltroAtivo] = useState("Gasolina");

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
        {["Gasolina", "Etanol", "Diesel"].map((tipo) => (
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
              {tipo}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <FlatList
        data={DADOS_SIMULADOS}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.listContainer}
        renderItem={({ item, index }) => (
          <View style={styles.card}>
            <View style={styles.rankContainer}>
              <Text style={styles.rankText}>{index + 1}º</Text>
            </View>
            <View style={styles.infoContainer}>
              <Text style={styles.nomePosto}>{item.nome}</Text>
              <Text style={styles.distanciaText}>
                <Ionicons name="location-outline" size={14} /> {item.distancia}{" "}
                • {item.atualizado}
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
      />
    </View>
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
