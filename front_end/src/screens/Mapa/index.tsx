// src/screens/Inicio/index.tsx
import BottomSheet, { BottomSheetScrollView } from "@gorhom/bottom-sheet";
import { useContext, useMemo, useRef, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";

import { ThemeContext } from "../../contexts/ThemeContext";
// Importamos o SEU super-componente de mapa cruzado
import MapaLeaflet from "../../components/mapa/MapaLeaflet";
import type { PosicaoUsuario, PostoNoMapa } from "../../components/mapa/tipos";

// Dados de teste baseados na sua configuração (João Pessoa)
const MOCK_POSTOS: PostoNoMapa[] = [
  { id: 1, lat: -7.115, lon: -34.861, cor: "#10B981", rotulo: "5,79" }, // Verde (Barato)
  { id: 2, lat: -7.118, lon: -34.858, cor: "#F59E0B", rotulo: "5,89" }, // Amarelo (Médio)
  { id: 3, lat: -7.112, lon: -34.865, cor: "#EF4444", rotulo: "6,10" }, // Vermelho (Caro)
];

const MOCK_USUARIO: PosicaoUsuario = {
  lat: -7.11532,
  lon: -34.86105,
  precisaoM: 150,
};

export default function Inicio() {
  const { colors } = useContext(ThemeContext);

  // Controlo da Gaveta
  const bottomSheetRef = useRef<BottomSheet>(null);
  const snapPoints = useMemo(() => ["15%", "45%", "80%"], []);

  // Estado que futuramente será alimentado pela API do Flask
  const [postos, setPostos] = useState<PostoNoMapa[]>(MOCK_POSTOS);
  const [usuario, setUsuario] = useState<PosicaoUsuario>(MOCK_USUARIO);

  const handlePostoSelecionado = (id: number) => {
    console.log(`[Mapa] Posto clicado: ID ${id}`);
    // Se clicar num pino do mapa, a gaveta expande para mostrar os detalhes
    bottomSheetRef.current?.snapToIndex(1);
  };

  return (
    // Raiz de Gestos OBRIGATÓRIA para a gaveta funcionar
    <GestureHandlerRootView style={styles.container}>
      {/* 1. O SEU MAPA NO FUNDO */}
      <MapaLeaflet
        postos={postos}
        usuario={usuario}
        onSelecionarPosto={handlePostoSelecionado}
        onRegiaoMudou={(regiao) =>
          console.log("Região alterada. Novo zoom:", regiao.zoom)
        }
      />

      {/* 2. A GAVETA DE PREÇOS POR CIMA */}
      <BottomSheet
        ref={bottomSheetRef}
        index={0} // Começa recolhida nos 15%
        snapPoints={snapPoints}
        backgroundStyle={{ backgroundColor: colors.background }}
        handleIndicatorStyle={{ backgroundColor: colors.textSecondary }}
      >
        <BottomSheetScrollView contentContainerStyle={styles.sheetContent}>
          <Text style={[styles.sheetTitle, { color: colors.textPrimary }]}>
            Combustível na Região
          </Text>
          <Text style={[styles.sheetSubtitle, { color: colors.textSecondary }]}>
            Deslize para ver os preços atualizados.
          </Text>

          {/* Lista de postos (mockados por agora) */}
          {postos.map((posto) => (
            <View
              key={posto.id}
              style={[styles.postoCard, { borderBottomColor: colors.border }]}
            >
              <View>
                <Text style={[styles.postoNome, { color: colors.textPrimary }]}>
                  Posto ID #{posto.id}
                </Text>
                <Text style={{ color: colors.textSecondary }}>
                  Atualizado hoje
                </Text>
              </View>
              <View style={styles.precoContainer}>
                <Text style={[styles.precoText, { color: posto.cor }]}>
                  R$ {posto.rotulo}
                </Text>
              </View>
            </View>
          ))}
        </BottomSheetScrollView>
      </BottomSheet>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  sheetContent: {
    paddingHorizontal: 24,
    paddingBottom: 24,
  },
  sheetTitle: {
    fontSize: 22,
    fontWeight: "bold",
    marginBottom: 4,
  },
  sheetSubtitle: {
    fontSize: 14,
    marginBottom: 24,
  },
  postoCard: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 16,
    borderBottomWidth: 1,
  },
  postoNome: {
    fontSize: 16,
    fontWeight: "600",
    marginBottom: 4,
  },
  precoContainer: {
    backgroundColor: "#1E1E1E",
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
  },
  precoText: {
    fontSize: 16,
    fontWeight: "bold",
  },
});
