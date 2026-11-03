// src/screens/Atividade/index.tsx
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useContext, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
// Adicione à primeira linha do seu ficheiro
import { useCallback } from "react";
// Adicione aos imports do react-navigation:
import { useFocusEffect } from "@react-navigation/native";

import { ThemeContext } from "../../contexts/ThemeContext";
import { api } from "../../services/API";
import { obterPostosVistos, PostoVisto } from "../../services/historicoVistos";

interface RegistoPrecoUser {
  id: number;
  tipo_combustivel: string;
  preco: number;
  data_formatada: string;
  posto_nome: string;
  posto_endereco: string;
}

export default function Atividade() {
  const { colors } = useContext(ThemeContext);

  const [abaAtiva, setAbaAtiva] = useState<"registos" | "vistos">("registos");
  const [registos, setRegistos] = useState<RegistoPrecoUser[]>([]);
  const [vistos, setVistos] = useState<PostoVisto[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isLogado, setIsLogado] = useState(false);

  const carregarDados = async () => {
    setIsLoading(true);
    const token = await AsyncStorage.getItem("@LitroDeOuro:token");
    setIsLogado(!!token);

    // Carrega postos vistos (Armazenamento Local)
    const vistosLocais = await obterPostosVistos();
    setVistos(vistosLocais);

    // Carrega registos de preço (API Flask se estiver logado)
    if (token) {
      try {
        const response = await api.get("/atividade/meus-registos", {
          headers: { Authorization: `Bearer ${token}` },
        });
        setRegistos(response.data);
      } catch (error) {
        console.error("Erro ao buscar registros:", error);
      }
    } else {
      setRegistos([]);
    }
    setIsLoading(false);
  };

  useFocusEffect(
    useCallback(() => {
      carregarDados();
    }, []),
  );

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await carregarDados();
    setIsRefreshing(false);
  };

  return (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
      <Text style={[styles.title, { color: colors.textPrimary }]}>
        Sua Atividade
      </Text>

      {/* Selector de Abas */}
      <View
        style={[
          styles.tabsContainer,
          { backgroundColor: colors.surface, borderColor: colors.border },
        ]}
      >
        <TouchableOpacity
          style={[
            styles.tab,
            abaAtiva === "registos" && { backgroundColor: colors.primary },
          ]}
          onPress={() => setAbaAtiva("registos")}
        >
          <Text
            style={{
              color: abaAtiva === "registos" ? "#121212" : colors.textPrimary,
              fontWeight: "bold",
            }}
          >
            Meus Preços
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[
            styles.tab,
            abaAtiva === "vistos" && { backgroundColor: colors.primary },
          ]}
          onPress={() => setAbaAtiva("vistos")}
        >
          <Text
            style={{
              color: abaAtiva === "vistos" ? "#121212" : colors.textPrimary,
              fontWeight: "bold",
            }}
          >
            Vistos Recente
          </Text>
        </TouchableOpacity>
      </View>

      {/* Conteúdo */}
      {isLoading ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
      ) : abaAtiva === "registos" ? (
        !isLogado ? (
          <View style={styles.center}>
            <Text style={{ color: colors.textSecondary, textAlign: "center" }}>
              Inicie sessão para ver o seu histórico de contribuições de preço.
            </Text>
          </View>
        ) : registos.length === 0 ? (
          <View style={styles.center}>
            <Text style={{ color: colors.textSecondary }}>
              Ainda não registou nenhum preço.
            </Text>
          </View>
        ) : (
          <FlatList
            data={registos}
            keyExtractor={(item) => item.id.toString()}
            refreshControl={
              <RefreshControl
                refreshing={isRefreshing}
                onRefresh={handleRefresh}
              />
            }
            contentContainerStyle={styles.listContent}
            renderItem={({ item }) => (
              <View
                style={[
                  styles.card,
                  {
                    backgroundColor: colors.surface,
                    borderColor: colors.border,
                  },
                ]}
              >
                <View style={{ flex: 1 }}>
                  <Text
                    style={[styles.cardTitle, { color: colors.textPrimary }]}
                  >
                    {item.posto_nome}
                  </Text>
                  <Text style={{ color: colors.textSecondary, fontSize: 13 }}>
                    {item.tipo_combustivel}
                  </Text>
                  <Text
                    style={{
                      color: colors.textSecondary,
                      fontSize: 11,
                      marginTop: 4,
                    }}
                  >
                    {item.data_formatada}
                  </Text>
                </View>
                <Text style={[styles.cardPrice, { color: colors.primary }]}>
                  R$ {item.preco.toFixed(2).replace(".", ",")}
                </Text>
              </View>
            )}
          />
        )
      ) : vistos.length === 0 ? (
        <View style={styles.center}>
          <Text style={{ color: colors.textSecondary }}>
            Nenhum posto consultado recentemente.
          </Text>
        </View>
      ) : (
        <FlatList
          data={vistos}
          keyExtractor={(item) => item.id.toString()}
          refreshControl={
            <RefreshControl
              refreshing={isRefreshing}
              onRefresh={handleRefresh}
            />
          }
          contentContainerStyle={styles.listContent}
          renderItem={({ item }) => (
            <View
              style={[
                styles.card,
                { backgroundColor: colors.surface, borderColor: colors.border },
              ]}
            >
              <View style={{ flex: 1 }}>
                <Text style={[styles.cardTitle, { color: colors.textPrimary }]}>
                  {item.nome}
                </Text>
                <Text style={{ color: colors.textSecondary, fontSize: 12 }}>
                  📍 {item.endereco}
                </Text>
              </View>
              <Text style={{ color: colors.textSecondary, fontSize: 11 }}>
                Visto em: {item.dataVisualizacao}
              </Text>
            </View>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, paddingHorizontal: 20, paddingTop: 60 },
  title: { fontSize: 28, fontWeight: "bold", marginBottom: 20 },
  tabsContainer: {
    flexDirection: "row",
    borderRadius: 12,
    borderWidth: 1,
    padding: 4,
    marginBottom: 16,
  },
  tab: { flex: 1, paddingVertical: 10, alignItems: "center", borderRadius: 8 },
  center: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: 20,
  },
  listContent: { paddingBottom: 24 },
  card: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 10,
  },
  cardTitle: { fontSize: 16, fontWeight: "bold", marginBottom: 2 },
  cardPrice: { fontSize: 18, fontWeight: "900" },
});
