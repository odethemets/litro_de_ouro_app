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
    const fetchPostos = async () => {
      try {
        const response = await api.get("/postos", { timeout: 15000 });
        setPostos(response.data);
      } catch (error) {
        console.warn("Aviso: Backend pode estar indisponível.", error);
      }
    };

    fetchPostos();

    // Escutamos os cliques que vêm do iframe do Leaflet!
    const handleMessage = (event: MessageEvent) => {
      try {
        if (event.data && typeof event.data === "string") {
          const parsed = JSON.parse(event.data);
          if (parsed.type === "MARKER_CLICKED") {
            setPostos((currentPostos) => {
              const posto = currentPostos.find((p) => p.id === parsed.id);
              if (posto) setPostoSelecionado(posto);
              return currentPostos;
            });
          }
        }
      } catch (e) {
        // ignora
      }
    };

    if (typeof window !== "undefined") {
      window.addEventListener("message", handleMessage);
      return () => window.removeEventListener("message", handleMessage);
    }
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
    const url = `https://www.google.com/maps/dir/?api=1&destination=${posto.latitude},${posto.longitude}`;
    if (Platform.OS === "web") {
      window.open(url, "_blank");
    } else {
      Linking.openURL(url);
    }
  };
  // Criamos o HTML do Leaflet puro que será renderizado no iframe. Isto desvia-se completamente dos problemas do React-Leaflet
  const mapHtml = `
    <!DOCTYPE html>
    <html lang="pt-PT">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
      <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
      <style>
        body { padding: 0; margin: 0; height: 100vh; width: 100vw; background: #e5e3df; overflow: hidden; }
        #map { height: 100%; width: 100%; }
        .leaflet-control-attribution { display: none; }
      </style>
    </head>
    <body>
      <div id="map"></div>
      <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
      <script>
        var map = L.map('map', { zoomControl: false }).setView([${centerPos.lat}, ${centerPos.lng}], 14);
        
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);

        var customIcon = L.icon({
          iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
          shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
          iconSize: [25, 41],
          iconAnchor: [12, 41],
          popupAnchor: [1, -34],
          shadowSize: [41, 41]
        });

        // Quando o React injetar os postos, o iframe avisa o site
        var postos = ${JSON.stringify(postos)};
        postos.forEach(function(posto) {
          L.marker([posto.latitude, posto.longitude], { icon: customIcon }).addTo(map)
            .bindPopup(posto.nome)
            .on('click', function() {
              window.parent.postMessage(JSON.stringify({ type: 'MARKER_CLICKED', id: posto.id }), '*');
            });
        });
      </script>
    </body>
    </html>
  `;

  return (
    <View style={styles.container}>
      {/* Usamos o iframe nativo da web, sem bibliotecas pesadas de fora */}
      <iframe
        title="map"
        style={{
          width: "100%",
          height: "100%",
          border: "none",
          position: "absolute",
          zIndex: 0,
        }}
        srcDoc={mapHtml}
      />

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
