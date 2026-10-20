import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Linking,
  Platform,
  ScrollView,
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
}

const TIPOS_COMBUSTIVEL = [
  "Gasolina Comum",
  "Etanol",
  "Diesel",
  "Gasolina adtivada",
];

export default function HomeScreenWeb() {
  const router = useRouter();
  const [postos, setPostos] = useState<Posto[]>([]);
  const [postoSelecionado, setPostoSelecionado] = useState<Posto | null>(null);

  // Novos Estados
  const [tipoCombustivel, setTipoCombustivel] = useState("Gasolina Comum");
  const [historico, setHistorico] = useState<any[]>([]);
  const [loadingHistorico, setLoadingHistorico] = useState(false);

  const centerPos = { lat: -7.11532, lng: -34.86105 };

  // Carrega Postos Iniciais
  useEffect(() => {
    const fetchPostos = async () => {
      try {
        const response = await api.get("/postos/");
        setPostos(response.data);
      } catch (error) {
        console.warn("Aviso: Backend pode estar indisponível.");
      }
    };
    fetchPostos();

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
      } catch (e) {}
    };

    if (typeof window !== "undefined") {
      window.addEventListener("message", handleMessage);
      return () => window.removeEventListener("message", handleMessage);
    }
  }, []);

  // Busca o Histórico de Preços sempre que muda o Posto ou o Combustível
  useEffect(() => {
    if (postoSelecionado) {
      buscarHistorico(postoSelecionado.id, tipoCombustivel);
    }
  }, [postoSelecionado, tipoCombustivel]);

  const buscarHistorico = async (posto_id: number, tipo: string) => {
    setLoadingHistorico(true);
    try {
      const response = await api.get(
        `/postos/${posto_id}/historico?tipo_combustivel=${tipo}`,
      );
      setHistorico(response.data);
    } catch (error) {
      console.warn("Erro ao buscar histórico");
    } finally {
      setLoadingHistorico(false);
    }
  };

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

  if (Platform.OS !== "web" || typeof window === "undefined") return null;

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
          iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41]
        });
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
      <iframe title="map" style={styles.iframeMap} srcDoc={mapHtml} />

      <TouchableOpacity style={styles.loginButton} onPress={handleProfileClick}>
        <Ionicons name="person-circle" size={45} color="#d79b00" />
      </TouchableOpacity>

      <TouchableOpacity
        style={styles.fab}
        onPress={() => router.push("/registrar-preco")}
      >
        <Ionicons name="add" size={30} color="#FFF" />
      </TouchableOpacity>

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
            {postoSelecionado.bairro || "João Pessoa - PB"}
          </Text>

          {/* Selecionador de Combustível */}
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            style={styles.scrollCombustivel}
          >
            {TIPOS_COMBUSTIVEL.map((tipo) => (
              <TouchableOpacity
                key={tipo}
                style={[
                  styles.chip,
                  tipoCombustivel === tipo && styles.chipSelecionado,
                ]}
                onPress={() => setTipoCombustivel(tipo)}
              >
                <Text
                  style={[
                    styles.chipTexto,
                    tipoCombustivel === tipo && styles.chipTextoSelecionado,
                  ]}
                >
                  {tipo}
                </Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          {loadingHistorico ? (
            <ActivityIndicator
              size="large"
              color="#d79b00"
              style={{ marginVertical: 20 }}
            />
          ) : historico.length > 0 ? (
            <>
              <View style={styles.precoCard}>
                <Text style={styles.combustivelLabel}>{tipoCombustivel}</Text>
                <Text style={styles.precoDestaque}>
                  R$ {historico[0].preco.toFixed(2).replace(".", ",")}
                </Text>
                <Text style={styles.dataAtualizacao}>
                  Atualizado em: {historico[0].data_formatada}
                </Text>
              </View>

              {historico.length > 1 && (
                <View style={styles.historicoContainer}>
                  <Text style={styles.historicoTitulo}>Histórico Recente:</Text>
                  {historico.slice(1).map((h, index) => (
                    <View key={index} style={styles.historicoRow}>
                      <Text style={styles.historicoData}>
                        {h.data_formatada}
                      </Text>
                      <Text style={styles.historicoPreco}>
                        R$ {h.preco.toFixed(2).replace(".", ",")}
                      </Text>
                    </View>
                  ))}
                </View>
              )}
            </>
          ) : (
            <View style={styles.semPrecoContainer}>
              <Ionicons name="alert-circle-outline" size={30} color="#999" />
              <Text style={styles.semPrecoTexto}>
                Nenhum preço de {tipoCombustivel} registado ainda.
              </Text>
            </View>
          )}

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
  // ✅ COMO DEVE FICAR (Compatível com o TypeScript do React Native):
  iframeMap: {
    width: "100%",
    height: "100%",
    borderWidth: 0,
    position: "absolute",
    zIndex: 0,
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
    alignItems: "center",
    zIndex: 20,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: -5 },
    shadowOpacity: 0.1,
    shadowRadius: 5,
  },
  closeBtn: { position: "absolute", top: 10, right: 15, zIndex: 30 },
  postoNome: { fontSize: 22, fontWeight: "bold", color: "#333", marginTop: 5 },
  distancia: { fontSize: 14, color: "#666", marginBottom: 15 },

  // Estilos da Rolagem de Combustíveis
  scrollCombustivel: { marginBottom: 15, maxHeight: 40, width: "100%" },
  chip: {
    backgroundColor: "#F5F5F5",
    paddingVertical: 8,
    paddingHorizontal: 15,
    borderRadius: 20,
    marginRight: 10,
    borderWidth: 1,
    borderColor: "#E0E0E0",
    height: 36,
    justifyContent: "center",
  },
  chipSelecionado: { backgroundColor: "#FFF9E6", borderColor: "#d79b00" },
  chipTexto: { color: "#666", fontWeight: "600", fontSize: 13 },
  chipTextoSelecionado: { color: "#d79b00", fontWeight: "bold" },

  // Preço Atual
  precoCard: {
    backgroundColor: "#f5f5f5",
    padding: 15,
    borderRadius: 10,
    width: "100%",
    maxWidth: 400,
    alignItems: "center",
    marginBottom: 15,
  },
  combustivelLabel: { fontSize: 16, color: "#555", fontWeight: "bold" },
  precoDestaque: { fontSize: 28, fontWeight: "bold", color: "#82b366" },
  dataAtualizacao: { fontSize: 12, color: "#999", marginTop: 4 },

  // Histórico
  historicoContainer: {
    width: "100%",
    maxWidth: 400,
    marginBottom: 20,
    paddingHorizontal: 10,
  },
  historicoTitulo: {
    fontSize: 14,
    fontWeight: "bold",
    color: "#333",
    marginBottom: 10,
  },
  historicoRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    borderBottomWidth: 1,
    borderColor: "#eee",
    paddingVertical: 8,
  },
  historicoData: { color: "#666", fontSize: 13 },
  historicoPreco: { color: "#82b366", fontWeight: "bold", fontSize: 14 },

  // Sem Preço
  semPrecoContainer: {
    alignItems: "center",
    paddingVertical: 20,
    marginBottom: 15,
  },
  semPrecoTexto: { color: "#999", marginTop: 10 },

  btnRota: {
    backgroundColor: "#333",
    paddingVertical: 12,
    borderRadius: 8,
    width: "100%",
    maxWidth: 400,
    alignItems: "center",
  },
  btnRotaText: { color: "#FFF", fontSize: 16, fontWeight: "bold" },
});
