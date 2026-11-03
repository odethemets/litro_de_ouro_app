import { Ionicons } from "@expo/vector-icons";
import BottomSheet, { BottomSheetView } from "@gorhom/bottom-sheet";
import axios from "axios";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Linking,
  Platform,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";

import MapaLeaflet from "../components/mapa/MapaLeaflet";
import type {
  MapaLeafletHandle,
  PosicaoUsuario,
  PostoNoMapa,
  RegiaoMapa,
} from "../components/mapa/tipos";
import { api } from "../services/API";
import { calcularCorDoPosto } from "../utils/cores";
import { ErroGps, obterPosicao } from "../utils/localizacao";
import { getToken, removeToken } from "../utils/token";

export interface Posto {
  id: number;
  nome: string;
  endereco?: string;
  bairro?: string;
  cidade?: string;
  uf?: string;
  latitude: number;
  longitude: number;
  preco_gasolina: number;
  data_atualizacao?: string | null;
  distancia?: number;
  horario_funcionamento?: string;
  tipo_posto?: "Convencional" | "Eletroposto";
}

type FiltroMapa = "Todos" | "Convencional" | "Eletroposto";

const FILTROS: { id: FiltroMapa; rotulo: string }[] = [
  { id: "Todos", rotulo: "Todos" },
  { id: "Convencional", rotulo: "Combustão" },
  { id: "Eletroposto", rotulo: "Elétricos" },
];

const COR_ELETROPOSTO = "#208AEF";
const FALLBACK = { lat: -7.1153, lon: -34.861 }; // João Pessoa, quando não há GPS
const REBUSCA_KM = 3; // só busca postos de novo quando o mapa andar mais do que isto

const calcularDistanciaKM = (
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
) => {
  const R = 6371;
  const dLat = (lat2 - lat1) * (Math.PI / 180);
  const dLon = (lon2 - lon1) * (Math.PI / 180);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(lat1 * (Math.PI / 180)) *
      Math.cos(lat2 * (Math.PI / 180)) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
};

export default function HomeScreen() {
  const router = useRouter();
  const bottomSheetRef = useRef<BottomSheet>(null);
  const mapaRef = useRef<MapaLeafletHandle>(null);
  const snapPoints = useMemo(() => ["25%", "40%"], []);

  const [posicao, setPosicao] = useState<PosicaoUsuario | null>(null);
  const [carregandoInicial, setCarregandoInicial] = useState(true);
  const [postos, setPostos] = useState<Posto[]>([]);
  const [postoSelecionado, setPostoSelecionado] = useState<Posto | null>(null);
  const [filtroMapa, setFiltroMapa] = useState<FiltroMapa>("Todos");

  // Controle de requisições: cancela a anterior e lembra onde foi a última busca bem-sucedida.
  const abortRef = useRef<AbortController | null>(null);
  const ultimaBuscaRef = useRef<{ lat: number; lon: number } | null>(null);
  const origemRef = useRef(FALLBACK); // ponto de onde as distâncias são medidas
  const sessaoAvisadaRef = useRef(false);

  const carregarPostos = useCallback(
    async (centro: { lat: number; lon: number }) => {
      const token = await getToken();
      if (!token) {
        console.warn("Token ausente. Navegação para login recomendada.");
        setPostos([]);
        return;
      }

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const response = await api.get("/postos", {
          params: { lat: centro.lat, lng: centro.lon },
          signal: controller.signal,
        });

        if (!Array.isArray(response.data)) {
          console.error("API não devolveu uma lista:", response.data);
          setPostos([]);
          return;
        }

        const origem = origemRef.current;
        const lista = (response.data as Posto[])
          .map((posto) => ({
            ...posto,
            distancia: calcularDistanciaKM(
              origem.lat,
              origem.lon,
              posto.latitude,
              posto.longitude,
            ),
          }))
          .sort((a, b) => (a.distancia || 0) - (b.distancia || 0));

        ultimaBuscaRef.current = centro;
        setPostos(lista);
      } catch (error: any) {
        if (axios.isCancel(error)) return; // substituída por uma busca mais nova
        console.error("Erro na API de postos:", error.message);

        if (error.response?.status === 401 && !sessaoAvisadaRef.current) {
          sessaoAvisadaRef.current = true;
          Alert.alert("Sessão Expirada", "Por favor, faça login novamente.");
          await removeToken();
        }
        // Em outros erros mantém os postos já exibidos em vez de esvaziar o mapa.
      }
    },
    [],
  );

  // Carga inicial: GPS (com tratamento de falhas) -> centraliza o mapa -> busca postos.
  useEffect(() => {
    let ativo = true;

    (async () => {
      let origem = FALLBACK;
      try {
        const pos = await obterPosicao("mapa");
        origem = { lat: pos.latitude, lon: pos.longitude };
        if (ativo) {
          setPosicao({
            lat: pos.latitude,
            lon: pos.longitude,
            precisaoM: pos.precisaoM,
          });
        }
      } catch (e) {
        if (e instanceof ErroGps && ativo) {
          Alert.alert(
            "Localização indisponível",
            `${e.message}\n\nMostrando João Pessoa.`,
            e.codigo === "PERMISSAO_NEGADA" && !e.podePedirNovamente
              ? [
                  {
                    text: "Abrir configurações",
                    onPress: () => Linking.openSettings(),
                  },
                  { text: "Continuar", style: "cancel" },
                ]
              : undefined,
          );
        } else {
          console.warn("Falha inesperada ao obter localização:", e);
        }
      }
      if (!ativo) return;

      origemRef.current = origem;
      mapaRef.current?.centralizar(origem.lat, origem.lon, 14);
      await carregarPostos(origem);
      if (ativo) setCarregandoInicial(false);
    })();

    return () => {
      ativo = false;
      abortRef.current?.abort();
    };
  }, [carregarPostos]);

  // Ao arrastar o mapa para longe da última busca, carrega os postos dessa região.
  const aoMudarRegiao = useCallback(
    (regiao: RegiaoMapa) => {
      const ultima = ultimaBuscaRef.current;
      if (!ultima) return; // ainda na carga inicial
      if (
        calcularDistanciaKM(ultima.lat, ultima.lon, regiao.lat, regiao.lon) <
        REBUSCA_KM
      )
        return;
      carregarPostos({ lat: regiao.lat, lon: regiao.lon });
    },
    [carregarPostos],
  );

  const aoSelecionarPosto = useCallback(
    (id: number) => {
      const posto = postos.find((p) => p.id === id);
      if (posto) {
        setPostoSelecionado(posto);
        bottomSheetRef.current?.expand();
      }
    },
    [postos],
  );

  // Dados do mapa derivados e memoizados: só mudam quando postos/filtro mudam.
  const postosNoMapa = useMemo<PostoNoMapa[]>(() => {
    const visiveis = postos.filter((p) => {
      if (filtroMapa === "Todos") return true;
      if (filtroMapa === "Eletroposto") return p.tipo_posto === "Eletroposto";
      return p.tipo_posto !== "Eletroposto";
    });

    // Concorrência: menor e maior preço entre os postos exibidos
    const precos = visiveis
      .filter((p) => p.preco_gasolina > 0)
      .map((p) => Number(p.preco_gasolina));
    const menor = precos.length > 0 ? Math.min(...precos) : 0;
    const maior = precos.length > 0 ? Math.max(...precos) : 0;

    return visiveis.map((p) => ({
      id: p.id,
      lat: p.latitude,
      lon: p.longitude,
      cor:
        p.tipo_posto === "Eletroposto"
          ? COR_ELETROPOSTO
          : calcularCorDoPosto(
              p.preco_gasolina,
              menor,
              maior,
              p.data_atualizacao,
            ),
    }));
  }, [postos, filtroMapa]);

  const selecionarFiltro = (filtro: FiltroMapa) => {
    setFiltroMapa(filtro);
    setPostoSelecionado(null);
    bottomSheetRef.current?.close();
  };

  const handleProfileClick = async () => {
    try {
      const token = await getToken();
      if (token) router.push("/perfil");
      else router.push("/login");
    } catch (e) {
      router.push("/login");
    }
  };

  const handleTracarRota = (posto: Posto) => {
    const url = `https://www.google.com/maps/dir/?api=1&destination=${posto.latitude},${posto.longitude}`;
    Linking.openURL(url).catch(() => {
      Alert.alert("Erro", "Não foi possível abrir o aplicativo de mapas.");
    });
  };

  return (
    <View style={styles.container}>
      {/* O mapa fica montado desde o início e nunca recarrega: a página Leaflet é carregada uma
          única vez e só recebe comandos (postos, posição, centro). */}
      <View style={styles.map}>
        <MapaLeaflet
          ref={mapaRef}
          postos={postosNoMapa}
          usuario={posicao}
          onSelecionarPosto={aoSelecionarPosto}
          onRegiaoMudou={aoMudarRegiao}
        />
      </View>

      <View style={styles.mapFilterContainer}>
        {FILTROS.map((filtro) => (
          <TouchableOpacity
            key={filtro.id}
            style={[
              styles.filterButton,
              filtroMapa === filtro.id && styles.filterButtonActive,
            ]}
            onPress={() => selecionarFiltro(filtro.id)}
          >
            <Text
              style={[
                styles.filterText,
                filtroMapa === filtro.id && styles.filterTextActive,
              ]}
            >
              {filtro.rotulo}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <TouchableOpacity
        style={styles.loginButton}
        activeOpacity={0.8}
        onPress={handleProfileClick}
      >
        <Ionicons name="person-circle" size={45} color="#d79b00" />
      </TouchableOpacity>

      <TouchableOpacity
        style={styles.fab}
        activeOpacity={0.8}
        onPress={() => router.push("/registrar-preco")}
      >
        <Ionicons name="add" size={30} color="#FFF" />
      </TouchableOpacity>

      <BottomSheet
        ref={bottomSheetRef}
        index={-1}
        snapPoints={snapPoints}
        enablePanDownToClose={true}
      >
        <BottomSheetView style={styles.sheetContainer}>
          {postoSelecionado ? (
            <>
              <Text style={styles.postoNome}>{postoSelecionado.nome}</Text>
              <Text style={styles.distancia}>
                {postoSelecionado.horario_funcionamento || "24 Horas"} •{" "}
                {postoSelecionado.distancia !== undefined
                  ? `${postoSelecionado.distancia.toFixed(1)} km de si`
                  : postoSelecionado.bairro || "João Pessoa"}
              </Text>
              <View style={styles.precoCard}>
                <Text style={styles.combustivelLabel}>
                  {postoSelecionado.tipo_posto === "Eletroposto"
                    ? "Recarga (kWh)"
                    : "Gasolina Comum"}
                </Text>
                <Text style={styles.precoDestaque}>
                  R${" "}
                  {Number(postoSelecionado.preco_gasolina ?? 0)
                    .toFixed(2)
                    .replace(".", ",")}
                </Text>
              </View>
              <TouchableOpacity
                style={styles.btnRota}
                activeOpacity={0.8}
                onPress={() => handleTracarRota(postoSelecionado)}
              >
                <Text style={styles.btnRotaText}>Traçar Rota</Text>
              </TouchableOpacity>
            </>
          ) : (
            <Text>Selecione um posto no mapa</Text>
          )}
        </BottomSheetView>
      </BottomSheet>

      {carregandoInicial && (
        <View
          style={[
            styles.loadingContainer,
            StyleSheet.absoluteFill,
            { backgroundColor: "#FFF", zIndex: 30 },
          ]}
        >
          <ActivityIndicator size="large" color="#d79b00" />
          <Text style={{ marginTop: 10 }}>
            A preparar o motor geográfico...
          </Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    width: "100%",
    height: Platform.OS === "web" ? ("100vh" as any) : "100%",
  },
  loadingContainer: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    height: Platform.OS === "web" ? ("100vh" as any) : "100%",
  },
  map: {
    position: "absolute",
    top: 0,
    bottom: 0,
    left: 0,
    right: 0,
    width: "100%",
    height: "100%",
    zIndex: 1,
  },
  mapFilterContainer: {
    position: "absolute",
    top: 50,
    left: 20,
    right: 80,
    flexDirection: "row",
    backgroundColor: "#FFF",
    borderRadius: 25,
    padding: 4,
    elevation: 5,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.3,
    shadowRadius: 3,
    zIndex: 10,
  },
  filterButton: {
    flex: 1,
    paddingVertical: 8,
    alignItems: "center",
    borderRadius: 20,
  },
  filterButtonActive: {
    backgroundColor: "#d79b00",
  },
  filterText: {
    fontSize: 12,
    fontWeight: "bold",
    color: "#666",
  },
  filterTextActive: {
    color: "#FFF",
  },
  loginButton: {
    position: "absolute",
    top: 45,
    right: 20,
    backgroundColor: "#FFF",
    width: 50,
    height: 50,
    borderRadius: 25,
    justifyContent: "center",
    alignItems: "center",
    elevation: 5,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.3,
    shadowRadius: 3,
    zIndex: 10,
  },
  fab: {
    position: "absolute",
    bottom: 40,
    right: 20,
    backgroundColor: "#d79b00",
    width: 60,
    height: 60,
    borderRadius: 30,
    justifyContent: "center",
    alignItems: "center",
    elevation: 5,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.3,
    shadowRadius: 3,
    zIndex: 10,
  },
  sheetContainer: {
    flex: 1,
    padding: 20,
    alignItems: "center",
    zIndex: 20,
  },
  postoNome: {
    fontSize: 22,
    fontWeight: "bold",
    color: "#333",
    textAlign: "center",
  },
  distancia: { fontSize: 14, color: "#666", marginBottom: 15 },
  precoCard: {
    backgroundColor: "#f5f5f5",
    padding: 15,
    borderRadius: 10,
    width: "100%",
    alignItems: "center",
    marginBottom: 15,
  },
  combustivelLabel: { fontSize: 16, color: "#555" },
  precoDestaque: { fontSize: 28, fontWeight: "bold", color: "#82b366" },
  btnRota: {
    backgroundColor: "#333",
    paddingVertical: 12,
    paddingHorizontal: 40,
    borderRadius: 8,
    width: "100%",
    alignItems: "center",
  },
  btnRotaText: { color: "#FFF", fontSize: 16, fontWeight: "bold" },
});
