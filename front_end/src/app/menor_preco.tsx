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
import { api } from "../services/API";

interface PostoPreco {
  posto_id: number;
  registo_id: number;
  nome: string;
  bairro?: string;
  distancia: string;
  preco: number;
  confianca_score: number;
}

export default function MenorPrecoScreen() {
  const router = useRouter();
  const [filtroAtivo, setFiltroAtivo] = useState("Gasolina Comum");
  const [dadosReais, setDadosReais] = useState<PostoPreco[]>([]);
  const [loading, setLoading] = useState(true);
  const [votando, setVotando] = useState<number | null>(null); // Bloqueia spam de cliques

  useEffect(() => {
    buscarMenoresPrecos();
  }, [filtroAtivo]);

  const buscarMenoresPrecos = async () => {
    setLoading(true);
    try {
      // Uso do Axios e da nova rota criada
      const response = await api.get(
        `/postos/menores-precos?tipo_combustivel=${filtroAtivo}`,
      );
      setDadosReais(response.data);
    } catch (error: any) {
      Alert.alert("Erro", "Não foi possível carregar os preços atualizados.");
    } finally {
      setLoading(false);
    }
  };

  // SISTEMA DE VOTO (INTEGRAÇÃO COM O BACKEND DE KARMA)
  const handleVoto = async (
    registo_id: number,
    tipo_voto: "positivo" | "negativo",
  ) => {
    try {
      setVotando(registo_id);
      const response = await api.post(`/precos/${registo_id}/votar`, {
        voto: tipo_voto,
      });

      if (
        response.data.message ===
        "Você já registrou este mesmo voto para este preço."
      ) {
        return; // Ignora visualmente
      }

      // Atualiza o score no ecrã localmente para ser instantâneo (Otimista)
      setDadosReais((prev) =>
        prev.map((item) => {
          if (item.registo_id === registo_id) {
            return {
              ...item,
              confianca_score:
                tipo_voto === "positivo"
                  ? item.confianca_score + 1
                  : item.confianca_score - 1,
            };
          }
          return item;
        }),
      );
    } catch (error: any) {
      if (error.response?.status === 401) {
        Alert.alert("Acesso Negado", "Faça login para poder votar nos preços.");
        router.push("/login");
      } else {
        Alert.alert(
          "Aviso",
          error.response?.data?.error || "Erro ao computar voto.",
        );
      }
    } finally {
      setVotando(null);
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

      {loading ? (
        <View
          style={{ flex: 1, justifyContent: "center", alignItems: "center" }}
        >
          <ActivityIndicator size="large" color="#d79b00" />
        </View>
      ) : (
        <FlatList
          data={dadosReais}
          keyExtractor={(item) => item.posto_id.toString()}
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
                  {item.distancia}
                </Text>
              </View>

              <View style={styles.precoContainer}>
                <Text style={styles.cifrao}>R$</Text>
                <Text style={styles.precoValor}>
                  {item.preco.toFixed(2).replace(".", ",")}
                </Text>
              </View>

              {/* COLUNA DE VOTOS (ESTILO REDDIT) */}
              <View style={styles.voteContainer}>
                <TouchableOpacity
                  disabled={votando === item.registo_id}
                  onPress={() => handleVoto(item.registo_id, "positivo")}
                >
                  <Ionicons name="caret-up-outline" size={28} color="#82b366" />
                </TouchableOpacity>

                {votando === item.registo_id ? (
                  <ActivityIndicator size="small" color="#666" />
                ) : (
                  <Text style={styles.scoreText}>{item.confianca_score}</Text>
                )}

                <TouchableOpacity
                  disabled={votando === item.registo_id}
                  onPress={() => handleVoto(item.registo_id, "negativo")}
                >
                  <Ionicons
                    name="caret-down-outline"
                    size={28}
                    color="#E53935"
                  />
                </TouchableOpacity>
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
  precoContainer: { alignItems: "flex-end", marginRight: 15 },
  cifrao: { fontSize: 12, color: "#82b366", fontWeight: "bold" },
  precoValor: { fontSize: 22, fontWeight: "bold", color: "#82b366" },
  voteContainer: {
    alignItems: "center",
    justifyContent: "center",
    borderLeftWidth: 1,
    borderColor: "#eee",
    paddingLeft: 10,
  },
  scoreText: {
    fontSize: 16,
    fontWeight: "bold",
    color: "#333",
    marginVertical: -2,
  },
});
