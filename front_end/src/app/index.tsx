import { Ionicons } from "@expo/vector-icons";
import BottomSheet, { BottomSheetView } from "@gorhom/bottom-sheet";
import * as Location from "expo-location";
import { useRouter } from "expo-router";
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Platform,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { WebView } from "react-native-webview";

interface Posto {
  id: number;
  nome: string;
  latitude: number;
  longitude: number;
  preco_gasolina: number;
  distancia?: string;
}

export default function HomeScreen() {
  const router = useRouter();
  const bottomSheetRef = useRef<BottomSheet>(null);
  const webViewRef = useRef<WebView>(null);
  const snapPoints = useMemo(() => ["25%", "40%"], []);

  const [location, setLocation] = useState<Location.LocationObject | null>(null);
  const [loading, setLoading] = useState(true);
  const [postos, setPostos] = useState<Posto[]>([]);
  const [postoSelecionado, setPostoSelecionado] = useState<Posto | null>(null);

  useEffect(() => {
    (async () => {
      // Pedir permissão rigorosa de GPS
      let { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== "granted") {
        Alert.alert(
          "Permissão negada",
          "O Litro de Ouro precisa da sua localização para mostrar postos próximos."
        );
        setLoading(false);
        return;
      }

      // Obter coordenada real
      let currentLocation = await Location.getCurrentPositionAsync({});
      setLocation(currentLocation);

      // Simular postos baseados na localização atual (Ligar depois ao Flask/MySQL)
      setPostos([
        {
          id: 1,
          nome: "Posto Epitácio",
          latitude: currentLocation.coords.latitude + 0.002,
          longitude: currentLocation.coords.longitude + 0.002,
          preco_gasolina: 5.89,
          distancia: "450m",
        },
        {
          id: 2,
          nome: "Posto Tambaú",
          latitude: currentLocation.coords.latitude - 0.001,
          longitude: currentLocation.coords.longitude - 0.003,
          preco_gasolina: 5.95,
          distancia: "120m",
        },
      ]);

      setLoading(false);
    })();
  }, []);

  // Ponte de comunicação rigorosa: Escuta os cliques vindos de dentro do HTML/Leaflet
  const handleWebViewMessage = (event: any) => {
    try {
      const data = JSON.parse(event.nativeEvent.data);
      if (data.type === "MARKER_CLICKED") {
        const posto = postos.find((p) => p.id === data.id);
        if (posto) {
          setPostoSelecionado(posto);
          // Expande a BottomSheet nativa ao clicar no mapa Web
          bottomSheetRef.current?.expand();
        }
      }
    } catch (error) {
      console.warn("Erro ao interpretar comunicação da WebView:", error);
    }
  };

  // Gerador dinâmico da base do Mapa OpenStreetMap com Leaflet Embutido
  const generateMapHTML = () => {
    if (!location) return "";

    // Injeta os marcadores com segurança
    const markersJS = postos
      .map(
        (posto) => `
      L.marker([${posto.latitude}, ${posto.longitude}]).addTo(map)
        .on('click', function() {
          // Envia um sinal para o React Native avisando qual posto foi clicado
          window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'MARKER_CLICKED', id: ${posto.id} }));
        });
    `
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
          .leaflet-control-attribution { display: none; /* Remove assinatura por motivos estéticos */ }
        </style>
      </head>
      <body>
        <div id="map"></div>
        <script>
          // Inicializa o mapa focado no utilizador
          var map = L.map('map', { zoomControl: false }).setView([${location.coords.latitude}, ${location.coords.longitude}], 15);
          
          // Adiciona a camada limpa do OpenStreetMap
          L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);

          // Cria um Ponto Azul rigoroso para representar o GPS do Utilizador
          var userIcon = L.divIcon({
            className: 'custom-user-icon',
            html: "<div style='background-color:#208AEF; width:18px; height:18px; border-radius:50%; border:3px solid white; box-shadow: 0 0 5px rgba(0,0,0,0.5);'></div>",
            iconSize: [24, 24],
            iconAnchor: [12, 12]
          });
          L.marker([${location.coords.latitude}, ${location.coords.longitude}], { icon: userIcon, zIndexOffset: 1000 }).addTo(map);

          // Insere os postos do backend
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
      {location && (
        <WebView
          ref={webViewRef}
          style={styles.map}
          originWhitelist={["*"]}
          source={{ html: generateMapHTML() }}
          onMessage={handleWebViewMessage}
          scrollEnabled={false}
          bounces={false}
        />
      )}

      {/* Botões Superiores e Inferiores sobrepostos à WebView */}
      <TouchableOpacity
        style={styles.loginButton}
        activeOpacity={0.8}
        onPress={() => router.push("/login")}
      >
        <Ionicons name="person-circle-outline" size={34} color="#333" />
      </TouchableOpacity>

      <TouchableOpacity
        style={styles.fab}
        activeOpacity={0.8}
        onPress={() => router.push("/registar-preco")}
      >
        <Ionicons name="add" size={30} color="#FFF" />
      </TouchableOpacity>

      <BottomSheet
        ref={bottomSheetRef}
        index={-1} // Escondido por predefinição até clicar num marcador
        snapPoints={snapPoints}
        enablePanDownToClose={true}
      >
        <BottomSheetView style={styles.sheetContainer}>
          {postoSelecionado ? (
            <>
              <Text style={styles.postoNome}>{postoSelecionado.nome}</Text>
              <Text style={styles.distancia}>{postoSelecionado.distancia} de si</Text>
              <View style={styles.precoCard}>
                <Text style={styles.combustivelLabel}>Gasolina Comum</Text>
                <Text style={styles.precoDestaque}>
                  R$ {postoSelecionado.preco_gasolina.toFixed(2).replace(".", ",")}
                </Text>
              </View>
              <TouchableOpacity style={styles.btnRota}>
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
  container: { flex: 1 },
  loadingContainer: { flex: 1, justifyContent: "center", alignItems: "center" },
  map: { position: "absolute", top: 0, bottom: 0, left: 0, right: 0 },
  loginButton: { position: "absolute", top: 50, right: 20, backgroundColor: "#FFF", width: 50, height: 50, borderRadius: 25, justifyContent: "center", alignItems: "center", elevation: 5, shadowColor: "#000", shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.3, shadowRadius: 3 },
  fab: { position: "absolute", bottom: 40, right: 20, backgroundColor: "#d79b00", width: 60, height: 60, borderRadius: 30, justifyContent: "center", alignItems: "center", elevation: 5, shadowColor: "#000", shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.3, shadowRadius: 3 },
  sheetContainer: { flex: 1, padding: 20, alignItems: "center" },
  postoNome: { fontSize: 22, fontWeight: "bold", color: "#333" },
  distancia: { fontSize: 14, color: "#666", marginBottom: 15 },
  precoCard: { backgroundColor: "#f5f5f5", padding: 15, borderRadius: 10, width: "100%", alignItems: "center", marginBottom: 15 },
  combustivelLabel: { fontSize: 16, color: "#555" },
  precoDestaque: { fontSize: 28, fontWeight: "bold", color: "#82b366" },
  btnRota: { backgroundColor: "#333", paddingVertical: 12, paddingHorizontal: 40, borderRadius: 8, width: "100%", alignItems: "center" },
  btnRotaText: { color: "#FFF", fontSize: 16, fontWeight: "bold" },
});