import { Ionicons } from "@expo/vector-icons";
import BottomSheet, { BottomSheetView } from "@gorhom/bottom-sheet";
import * as Location from "expo-location";
import { useRouter } from "expo-router";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Platform,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import MapView, { Marker } from "react-native-maps";

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
  const snapPoints = useMemo(() => ["25%", "40%"], []);

  const [location, setLocation] = useState<Location.LocationObject | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [postos, setPostos] = useState<Posto[]>([]);
  const [postoSelecionado, setPostoSelecionado] = useState<Posto | null>(null);

  useEffect(() => {
    (async () => {
      if (Platform.OS === "web") {
        setLoading(false);
        return;
      }

      let { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== "granted") {
        Alert.alert(
          "Permissão negada",
          "Precisamos da sua localização para mostrar os postos.",
        );
        setLoading(false);
        return;
      }

      let currentLocation = await Location.getCurrentPositionAsync({});
      setLocation(currentLocation);

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

  const handleMarkerPress = (posto: Posto) => {
    setPostoSelecionado(posto);
    bottomSheetRef.current?.expand();
  };

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#d79b00" />
        <Text style={{ marginTop: 10 }}>A carregar mapa...</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {Platform.OS === "web" ? (
        <View style={styles.webFallback}>
          <Ionicons name="map-outline" size={64} color="#999" />
          <Text style={styles.webFallbackTitle}>Mapa Indisponível na Web</Text>
          <Text style={styles.webFallbackText}>
            Por favor, teste este ecrã utilizando o aplicativo Expo Go no seu
            telemóvel.
          </Text>
        </View>
      ) : (
        location && (
          <MapView
            style={styles.map}
            userInterfaceStyle="light"
            customMapStyle={[]}
            initialRegion={{
              latitude: location.coords.latitude,
              longitude: location.coords.longitude,
              latitudeDelta: 0.015,
              longitudeDelta: 0.015,
            }}
            showsUserLocation={true}
            showsMyLocationButton={true}
          >
            {postos.map((posto) => (
              <Marker
                key={posto.id}
                coordinate={{
                  latitude: posto.latitude,
                  longitude: posto.longitude,
                }}
                onPress={() => handleMarkerPress(posto)}
              >
                <Ionicons name="location-sharp" size={40} color="#d79b00" />
              </Marker>
            ))}
          </MapView>
        )
      )}

      {/* NOVO: Botão de Login/Perfil no topo da tela */}
      <TouchableOpacity
        style={styles.loginButton}
        activeOpacity={0.8}
        onPress={() => router.push("/login")}
      >
        <Ionicons name="person-circle-outline" size={34} color="#333" />
      </TouchableOpacity>

      {/* Botão de Registar Preço (+) no canto inferior direito */}
      <TouchableOpacity
        style={styles.fab}
        activeOpacity={0.8}
        onPress={() => router.push("/registar-preco")}
      >
        <Ionicons name="add" size={30} color="#FFF" />
      </TouchableOpacity>

      {Platform.OS !== "web" && (
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
                  {postoSelecionado.distancia} de si
                </Text>
                <View style={styles.precoCard}>
                  <Text style={styles.combustivelLabel}>Gasolina Comum</Text>
                  <Text style={styles.precoDestaque}>
                    R${" "}
                    {postoSelecionado.preco_gasolina
                      .toFixed(2)
                      .replace(".", ",")}
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
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  loadingContainer: { flex: 1, justifyContent: "center", alignItems: "center" },
  map: {
    position: "absolute",
    top: 0,
    bottom: 0,
    left: 0,
    right: 0,
  },
  webFallback: {
    flex: 1,
    backgroundColor: "#f5f5f5",
    justifyContent: "center",
    alignItems: "center",
    padding: 20,
  },
  webFallbackTitle: {
    fontSize: 20,
    fontWeight: "bold",
    color: "#555",
    marginTop: 10,
  },
  webFallbackText: {
    fontSize: 14,
    color: "#888",
    textAlign: "center",
    marginTop: 5,
  },

  /* ESTILO DO NOVO BOTÃO DE LOGIN */
  loginButton: {
    position: "absolute",
    top: 50, // Afastado do topo para não bater no relógio/bateria do telemóvel
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
  },

  /* ESTILO DO BOTÃO DE REGISTO (+) */
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
  },

  sheetContainer: { flex: 1, padding: 20, alignItems: "center" },
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
