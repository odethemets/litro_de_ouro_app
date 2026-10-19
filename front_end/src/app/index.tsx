import { useEffect, useMemo, useRef, useState } from "react";
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
import { WebView } from "react-native-webview";

import { Ionicons } from "@expo/vector-icons";
import BottomSheet, { BottomSheetView } from "@gorhom/bottom-sheet";
import * as Location from "expo-location";
import { useRouter } from "expo-router";

import { getToken } from "../utils/token";

// 1. Interface definida no escopo GLOBAL
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
  distancia?: number;
}

// 2. Componente principal da aplicação
export default function HomeScreen() {
  const router = useRouter();
  const bottomSheetRef = useRef<BottomSheet>(null);
  const webViewRef = useRef<WebView>(null);
  const snapPoints = useMemo(() => ["25%", "40%"], []);

  const [location, setLocation] = useState<Location.LocationObject | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [postos, setPostos] = useState<Posto[]>([]);
  const [postoSelecionado, setPostoSelecionado] = useState<Posto | null>(null);

  // Escuta de cliques do mapa Leaflet (iframe) especificamente no navegador Web
  useEffect(() => {
    const handleWebMessage = (event: MessageEvent) => {
      try {
        const data =
          typeof event.data === "string" ? JSON.parse(event.data) : event.data;

        if (data && data.type === "MARKER_CLICKED") {
          const posto = postos.find((p) => p.id === data.id);
          if (posto) {
            setPostoSelecionado(posto);
            bottomSheetRef.current?.expand();
          }
        }
      } catch (e) {
        // Ignora mensagens de extensões ou outros scripts do navegador
      }
    };

    if (Platform.OS === "web" && typeof window !== "undefined") {
      window.addEventListener("message", handleWebMessage);
    }

    return () => {
      if (Platform.OS === "web" && typeof window !== "undefined") {
        window.removeEventListener("message", handleWebMessage);
      }
    };
  }, [postos]);

  // Escuta os cliques dos marcadores vindos do HTML/Leaflet
  const handleWebViewMessage = (event: any) => {
    try {
      const data = JSON.parse(event.nativeEvent.data);
      if (data.type === "MARKER_CLICKED") {
        const posto = postos.find((p) => p.id === data.id);
        if (posto) {
          setPostoSelecionado(posto);
          bottomSheetRef.current?.expand();
        }
      }
    } catch (error) {
      console.warn("Erro ao interpretar mensagem da WebView:", error);
    }
  };

  // Navegação para a página de perfil ou login
  const handleProfileClick = async () => {
    try {
      const token = await getToken();
      if (token) {
        router.push("/perfil");
      } else {
        router.push("/login");
      }
    } catch (e) {
      router.push("/login");
    }
  };

  // Traçar rota no Google Maps
  const handleTracarRota = (posto: Posto) => {
    const url = `https://www.google.com/maps/dir/?api=1&destination=${posto.latitude},${posto.longitude}`;

    Linking.openURL(url).catch(() => {
      Alert.alert("Erro", "Não foi possível abrir o aplicativo de mapas.");
    });
  };

  // Gerador dinâmico do HTML com Leaflet
  const generateMapHTML = () => {
    // Coordenadas padrão de João Pessoa se o GPS não estiver pronto
    const userLat = location?.coords.latitude ?? -7.1153;
    const userLng = location?.coords.longitude ?? -34.861;

    const markersJS = postos
      .map(
        (posto) => `
      L.marker([${posto.latitude}, ${posto.longitude}]).addTo(map)
        .on('click', function() {
          if (window.ReactNativeWebView && window.ReactNativeWebView.postMessage) {
            window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'MARKER_CLICKED', id: ${posto.id} }));
          } else if (window.parent) {
            window.parent.postMessage(JSON.stringify({ type: 'MARKER_CLICKED', id: ${posto.id} }), '*');
          }
        });
    `,
      )
      .join("\n");

    return `
      <!DOCTYPE html>
      <html>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
          body, html { margin: 0; padding: 0; height: 100%; width: 100%; background-color: #f5f5f5; }
          #map { height: 100vh; width: 100vw; }
          .leaflet-control-attribution { display: none; }
        </style>
      </head>
      <body>
        <div id="map"></div>
        <script>
          var map = L.map('map', { zoomControl: false }).setView([${userLat}, ${userLng}], 14);
          
          L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);

          var userIcon = L.divIcon({
            className: 'custom-user-icon',
            html: "<div style='background-color:#208AEF; width:18px; height:18px; border-radius:50%; border:3px solid white; box-shadow: 0 0 5px rgba(0,0,0,0.5);'></div>",
            iconSize: [24, 24],
            iconAnchor: [12, 12]
          });
          L.marker([${userLat}, ${userLng}], { icon: userIcon, zIndexOffset: 1000 }).addTo(map);

          ${markersJS}
        </script>
      </body>
      </html>
    `;
  };

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#d79b00" />
        <Text style={{ marginTop: 10 }}>A preparar o motor geográfico...</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <WebView
        ref={webViewRef}
        style={styles.map}
        originWhitelist={["*"]}
        source={{ html: generateMapHTML() }}
        onMessage={handleWebViewMessage}
        scrollEnabled={false}
        bounces={false}
      />

      {/* Botão de Perfil */}
      <TouchableOpacity
        style={styles.loginButton}
        activeOpacity={0.8}
        onPress={handleProfileClick}
      >
        <Ionicons name="person-circle" size={45} color="#d79b00" />
      </TouchableOpacity>

      {/* Botão Adicionar Preço */}
      <TouchableOpacity
        style={styles.fab}
        activeOpacity={0.8}
        onPress={() => router.push("/registrar-preco")}
      >
        <Ionicons name="add" size={30} color="#FFF" />
      </TouchableOpacity>

      {/* BottomSheet de Detalhes */}
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
                {postoSelecionado.distancia
                  ? `${postoSelecionado.distancia} de si`
                  : postoSelecionado.bairro || "João Pessoa"}
              </Text>
              <View style={styles.precoCard}>
                <Text style={styles.combustivelLabel}>Gasolina Comum</Text>
                <Text style={styles.precoDestaque}>
                  R${" "}
                  {Number(postoSelecionado?.preco_gasolina ?? 0)
                    .toFixed(2)
                    .replace(".", ",")}
                </Text>
              </View>
              <TouchableOpacity
                style={styles.btnRota}
                activeOpacity={0.8}
                onPress={() => handleTracarRota(postoSelecionado!)}
              >
                <Text style={styles.btnRotaText}>Traçar Rota</Text>
              </TouchableOpacity>
            </>
          ) : (
            <Text>Selecione um posto no mapa</Text>
          )}
        </BottomSheetView>
      </BottomSheet>
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
  loginButton: {
    position: "absolute",
    top: 50,
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
  postoNome: { fontSize: 22, fontWeight: "bold", color: "#333" },
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
