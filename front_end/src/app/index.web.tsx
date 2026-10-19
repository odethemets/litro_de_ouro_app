import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import {
  Linking,
  Platform,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { api } from "../services/API";
import { getToken } from "../utils/token";

// Importações Web
import L from "leaflet";
// @ts-ignore
import "leaflet/dist/leaflet.css";
import { MapContainer, Marker, Popup, TileLayer } from "react-leaflet";

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
  const [postos, setPostos] = useState<Posto[]>([]);
  const [postoSelecionado, setPostoSelecionado] = useState<Posto | null>(null);

  // Coordenadas João Pessoa
  const centerPos = { lat: -7.11532, lng: -34.86105 };

  useEffect(() => {
    // 1. Injeta CSS seguro para evitar que o Metro Bundler crash localmente
    if (typeof document !== "undefined") {
      const styleId = "leaflet-safe-style";
      if (!document.getElementById(styleId)) {
        const style = document.createElement("style");
        style.id = styleId;
        style.innerHTML = `@import url("https://unpkg.com/leaflet@1.9.4/dist/leaflet.css");`;
        document.head.appendChild(style);
      }
    }

    // 2. Busca os dados de forma assíncrona, sem bloquear o mapa
    const fetchPostos = async () => {
      try {
        const response = await api.get("/postos", { timeout: 15000 });
        setPostos(response.data);
      } catch (error) {
        console.warn(
          "Backend do Render pode estar a dormir ou indisponível:",
          error,
        );
      }
    };

    fetchPostos();
  }, []);

  const handleProfileClick = async () => {
    try {
      const token = await getToken();
      if (token) router.push("/perfil");
      else router.push("/login");
    } catch {
      router.push("/login");
    }
  };

  const handleTracarRota = (posto: Posto) => {
    Linking.openURL(
      `https://www.google.com/maps/dir/?api=1&destination=${posto.latitude},${posto.longitude}`,
    );
  };

  // Se não estivermos na Web, retorna nulo para segurança extra do SSR
  if (Platform.OS !== "web" || typeof window === "undefined") {
    return null;
  }

  return (
    <View style={styles.container}>
      {/* O Mapa carrega IMEDIATAMENTE, não espera pela API */}
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

      {/* Botões */}
      <TouchableOpacity style={styles.loginButton} onPress={handleProfileClick}>
        <Ionicons name="person-circle" size={45} color="#d79b00" />
      </TouchableOpacity>

      <TouchableOpacity
        style={styles.fab}
        onPress={() => router.push("/registrar-preco")}
      >
        <Ionicons name="add" size={30} color="#FFF" />
      </TouchableOpacity>

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
    height: "100vh" as any,
    width: "100%",
  },
  loginButton: {
    position: "absolute",
    top: 20,
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
    bottom: 20,
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
