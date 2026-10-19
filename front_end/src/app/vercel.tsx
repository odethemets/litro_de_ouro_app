import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Linking,
  Platform,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { api } from "../services/API";

// Importações exclusivas para Web (React-Leaflet)
import L from "leaflet";
// ATENÇÃO: Removido o import direto do CSS para não quebrar o compilador Metro
import { MapContainer, Marker, Popup, TileLayer } from "react-leaflet";

// Configuração para corrigir o ícone padrão do mapa no navegador
const customIcon = new L.Icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  iconRetinaUrl:
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

export interface Posto {
  id: number;
  nome: string;
  bairro?: string;
  latitude: number;
  longitude: number;
  preco_gasolina: number;
  distancia?: string | number;
}

export default function HomeScreenWeb() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [postos, setPostos] = useState<Posto[]>([]);
  const [postoSelecionado, setPostoSelecionado] = useState<Posto | null>(null);

  // Coordenadas centrais da Web (João Pessoa - PB)
  const centerPos = { lat: -7.11532, lng: -34.86105 };

  useEffect(() => {
    // INJEÇÃO SEGURA DE CSS: Resolve o erro do compilador Metro e previne loading infinito
    if (typeof document !== "undefined") {
      if (!document.getElementById("leaflet-css-injection")) {
        const style = document.createElement("style");
        style.id = "leaflet-css-injection";
        style.type = "text/css";
        style.innerHTML = `@import url("https://unpkg.com/leaflet@1.9.4/dist/leaflet.css");`;
        document.head.appendChild(style);
      }
    }

    // Busca os postos reais cadastrados na base de dados Aiven
    carregarPostos();
  }, []);

  const carregarPostos = async () => {
    try {
      const response = await api.get("/postos", { timeout: 10000 });
      setPostos(response.data);
    } catch (error) {
      console.warn("Falha ao carregar API. Exibindo mapa limpo.", error);
    } finally {
      // GARANTE que sai da tela de loading, mesmo se o backend falhar
      setLoading(false);
    }
  };

  const handleTracarRota = (posto: Posto) => {
    const url = `https://www.google.com/maps/dir/?api=1&destination=${posto.latitude},${posto.longitude}`;
    Linking.openURL(url);
  };

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#d79b00" />
        <Text style={{ marginTop: 10, color: "#666" }}>
          A preparar o motor geográfico...
        </Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Condição de segurança contra SSR (Server-Side Rendering) da Vercel */}
      {typeof window !== "undefined" && (
        <MapContainer
          center={[centerPos.lat, centerPos.lng]}
          zoom={14}
          style={{
            height: "100%",
            width: "100%",
            position: "absolute",
            zIndex: 0,
          }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {postos.map((posto) => (
            <Marker
              key={posto.id}
              position={[posto.latitude, posto.longitude]}
              icon={customIcon}
              eventHandlers={{ click: () => setPostoSelecionado(posto) }}
            >
              <Popup>{posto.nome}</Popup>
            </Marker>
          ))}
        </MapContainer>
      )}

      {/* Painel do Posto Selecionado */}
      {postoSelecionado && (
        <View style={styles.sheetContainer}>
          <TouchableOpacity
            style={styles.closeBtn}
            onPress={() => setPostoSelecionado(null)}
          >
            <Ionicons name="close-circle" size={28} color="#999" />
          </TouchableOpacity>
          <Text style={styles.postoNome}>{postoSelecionado.nome}</Text>
          <Text style={styles.distancia}>
            {postoSelecionado.distancia
              ? `${postoSelecionado.distancia} de si`
              : postoSelecionado.bairro || "João Pessoa - PB"}
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
            onPress={() => handleTracarRota(postoSelecionado)}
          >
            <Text style={styles.btnRotaText}>Traçar Rota</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#E5E3DF",
    height: Platform.OS === "web" ? ("100vh" as any) : "100%",
    width: "100%",
  },
  loadingContainer: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    height: Platform.OS === "web" ? ("100vh" as any) : "100%",
  },
  sheetContainer: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: "#FFF",
    padding: 20,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    elevation: 10,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: -5 },
    shadowOpacity: 0.1,
    shadowRadius: 5,
    alignItems: "center",
    zIndex: 20,
  },
  closeBtn: { position: "absolute", top: 10, right: 15, zIndex: 30 },
  postoNome: { fontSize: 22, fontWeight: "bold", color: "#333", marginTop: 5 },
  distancia: { fontSize: 14, color: "#666", marginBottom: 15 },
  precoCard: {
    backgroundColor: "#f5f5f5",
    padding: 15,
    borderRadius: 10,
    width: "100%",
    maxWidth: 400,
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
    maxWidth: 400,
    alignItems: "center",
  },
  btnRotaText: { color: "#FFF", fontSize: 16, fontWeight: "bold" },
});
