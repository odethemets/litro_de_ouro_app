// src/screens/Inicio/index.tsx
import BottomSheet, { BottomSheetScrollView } from "@gorhom/bottom-sheet";
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as Location from "expo-location";
import { useContext, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Linking, // <-- IMPORT NOVO PARA ABRIR O GPS
  Modal,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";

import MapaLeaflet from "../../components/mapa/MapaLeaflet";
import type {
  MapaLeafletHandle,
  PosicaoUsuario,
  PostoNoMapa,
} from "../../components/mapa/tipos";
import { ThemeContext } from "../../contexts/ThemeContext";
import { api } from "../../services/API";
import { registrarPostoVisto } from "../../services/historicoVistos";

interface PostoDetalhado extends PostoNoMapa {
  nome: string;
  endereco: string;
  combustivel: string;
  distancia_m?: number;
}

const OPCOES_COMBUSTIVEL = [
  "Gasolina Comum",
  "Gasolina Aditivada",
  "Etanol",
  "Diesel",
  "GNV",
  "Recarga Elétrica (kWh)",
];

// Pode futuramente vir das configurações do utilizador!
const CONSUMO_MEDIO_KM_L = 10;

export default function Inicio() {
  const { colors } = useContext(ThemeContext) as any;

  const mapaRef = useRef<MapaLeafletHandle>(null);
  const bottomSheetRef = useRef<BottomSheet>(null);
  const snapPoints = useMemo(() => ["15%", "45%", "85%"], []);

  // Estados Globais
  const [postos, setPostos] = useState<PostoDetalhado[]>([]);
  const [usuario, setUsuario] = useState<PosicaoUsuario | null>(null);
  const [isLoadingLocalizacao, setIsLoadingLocalizacao] = useState(false);

  // Estados de Detalhe
  const [postoSelecionado, setPostoSelecionado] =
    useState<PostoDetalhado | null>(null);
  const [precosDetalhe, setPrecosDetalhe] = useState<any[]>([]);
  const [isLoadingPrecos, setIsLoadingPrecos] = useState(false);

  // Estados do Modal de Registo de Preço
  const [modalVisivel, setModalVisivel] = useState(false);
  const [combustivelSelecionado, setCombustivelSelecionado] =
    useState("Gasolina Comum");
  const [novoPrecoInput, setNovoPrecoInput] = useState("");
  const [isEnviandoPreco, setIsEnviandoPreco] = useState(false);

  // --- BUSCA DE DADOS ---
  const mapearDadosDoBanco = (dados: any[]): PostoDetalhado[] => {
    return dados.map((p) => {
      const isEletrico = p.tipo_posto === "Eletroposto";
      const temPreco = p.preco_gasolina && p.preco_gasolina > 0;
      const precoFormatado = temPreco
        ? p.preco_gasolina.toFixed(2).replace(".", ",")
        : "---";

      return {
        id: p.id,
        lat: p.latitude,
        lon: p.longitude,
        nome: p.nome,
        endereco: p.bairro ? `${p.endereco}\n${p.bairro}` : p.endereco,
        combustivel: isEletrico ? "Recarga Elétrica (kWh)" : "Gasolina Comum",
        cor: isEletrico ? "#3B82F6" : temPreco ? "#10B981" : "#9CA3AF",
        rotulo: precoFormatado,
        distancia_m: p.distancia_m, // O backend já devolve a distância calculada!
      };
    });
  };

  const buscarLocalizacaoEPostos = async (forcarRequisicao = false) => {
    setIsLoadingLocalizacao(true);
    let latAtual = null;
    let lonAtual = null;

    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status === "granted") {
        const loc = await Location.getCurrentPositionAsync({
          accuracy: Location.Accuracy.Balanced,
        });
        latAtual = loc.coords.latitude;
        lonAtual = loc.coords.longitude;

        setUsuario({
          lat: latAtual,
          lon: lonAtual,
          precisaoM: loc.coords.accuracy,
        });

        if (forcarRequisicao) {
          mapaRef.current?.centralizar(latAtual, lonAtual, 14);
        }
      }
    } catch (error) {
      console.warn("Permissão recusada ou GPS inativo.");
    } finally {
      setIsLoadingLocalizacao(false);
    }

    try {
      const endpoint =
        latAtual && lonAtual
          ? `/postos?lat=${latAtual}&lng=${lonAtual}`
          : `/postos`;

      const response = await api.get(endpoint);
      setPostos(mapearDadosDoBanco(response.data));
    } catch (error: any) {
      console.error("[Inicio] Erro ao buscar postos:", error.message);
    }
  };

  useEffect(() => {
    buscarLocalizacaoEPostos(true);
  }, []);

  // --- INTERAÇÕES DO UTILIZADOR ---
  const focarNoPosto = async (posto: PostoDetalhado) => {
    setPostoSelecionado(posto);
    mapaRef.current?.centralizar(posto.lat, posto.lon, 16);
    bottomSheetRef.current?.snapToIndex(1);

    // Guardar histórico local
    registrarPostoVisto({
      id: posto.id,
      nome: posto.nome,
      endereco: posto.endereco,
    });

    setIsLoadingPrecos(true);
    try {
      const response = await api.get(`/postos/${posto.id}/precos`);
      setPrecosDetalhe(response.data);
    } catch (error) {
      console.error("Erro ao buscar preços:", error);
      setPrecosDetalhe([]);
    } finally {
      setIsLoadingPrecos(false);
    }
  };

  const handlePinoClicado = (id: number) => {
    const posto = postos.find((p) => p.id === id);
    if (posto) focarNoPosto(posto);
  };

  const handleVoltarParaLista = () => {
    setPostoSelecionado(null);
    setPrecosDetalhe([]);
    bottomSheetRef.current?.snapToIndex(1);
    if (usuario) mapaRef.current?.centralizar(usuario.lat, usuario.lon, 14);
  };

  // --- NOVA FUNCIONALIDADE: TRAÇAR ROTA ---
  const abrirRotaMapaApp = () => {
    if (!postoSelecionado) return;
    // URL Universal que funciona e abre a app nativa no Android e iOS
    const url = `https://www.google.com/maps/dir/?api=1&destination=${postoSelecionado.lat},${postoSelecionado.lon}`;
    Linking.openURL(url);
  };

  // --- NOVA FUNCIONALIDADE: EMERGÊNCIA (Mais próximo) ---
  const handleEmergencia = () => {
    if (postos.length === 0) {
      Alert.alert("Aviso", "Ainda não carregamos os postos na sua região.");
      return;
    }
    // Como o backend já ordena por distância, ou garantimos localmente:
    const postosOrdenados = [...postos].sort((a, b) => {
      const distA = a.distancia_m !== undefined ? a.distancia_m : 999999;
      const distB = b.distancia_m !== undefined ? b.distancia_m : 999999;
      return distA - distB;
    });

    const postoMaisProximo = postosOrdenados[0];
    focarNoPosto(postoMaisProximo);
    Alert.alert(
      "Modo Emergência",
      `Focámos no posto mais próximo:\n${postoMaisProximo.nome}`,
    );
  };

  // --- SUBMISSÃO DE PREÇO ---
  const abrirModalPreco = async () => {
    const token = await AsyncStorage.getItem("@LitroDeOuro:token");
    if (!token) {
      Alert.alert(
        "Autenticação Necessária",
        "Precisa de ter sessão iniciada para registrar novos preços.",
        [{ text: "OK" }],
      );
      return;
    }
    setNovoPrecoInput("");
    setModalVisivel(true);
  };

  const handleSalvarPreco = async () => {
    if (!novoPrecoInput.trim() || !postoSelecionado) {
      Alert.alert("Erro", "Por favor, digite o valor do combustível.");
      return;
    }
    const valorNormalizado = parseFloat(novoPrecoInput.replace(",", "."));
    if (isNaN(valorNormalizado) || valorNormalizado <= 0) {
      Alert.alert("Erro", "Introduza um preço válido.");
      return;
    }
    setIsEnviandoPreco(true);
    try {
      const token = await AsyncStorage.getItem("@LitroDeOuro:token");
      await api.post(
        `/postos/${postoSelecionado.id}/precos`,
        { tipo_combustivel: combustivelSelecionado, preco: valorNormalizado },
        { headers: { Authorization: `Bearer ${token}` } },
      );
      Alert.alert("Sucesso", "Preço registrado com sucesso!");
      setModalVisivel(false);
      focarNoPosto(postoSelecionado);
    } catch (error: any) {
      const msg =
        error.response?.data?.error || "Não foi possível salvar o preço.";
      Alert.alert("Erro ao Salvar", msg);
    } finally {
      setIsEnviandoPreco(false);
    }
  };

  // --- GAVETA DESLIZANTE ---
  const renderConteudoGaveta = () => {
    if (postoSelecionado) {
      // Cálculo do Custo de Rota
      let custoDaViagemFormatado = null;
      if (postoSelecionado.distancia_m && precosDetalhe.length > 0) {
        // Pega o preço principal
        const precoItem =
          precosDetalhe.find(
            (p) => p.tipo_combustivel === postoSelecionado.combustivel,
          ) || precosDetalhe[0];
        if (precoItem && precoItem.preco > 0) {
          const distanciaKm = postoSelecionado.distancia_m / 1000;
          const litrosNecessarios = distanciaKm / CONSUMO_MEDIO_KM_L;
          const custo = litrosNecessarios * precoItem.preco;
          custoDaViagemFormatado = `Custo aprox. p/ chegar: R$ ${custo.toFixed(2).replace(".", ",")}`;
        }
      }

      return (
        <View style={styles.sheetContent}>
          <TouchableOpacity
            style={styles.btnVoltar}
            onPress={handleVoltarParaLista}
          >
            <Text
              style={{
                color: colors.primary,
                fontSize: 16,
                fontWeight: "bold",
              }}
            >
              ⬅ Voltar à lista
            </Text>
          </TouchableOpacity>

          <Text
            style={[styles.postoSelecionadoNome, { color: colors.textPrimary }]}
          >
            {postoSelecionado.nome}
          </Text>
          <Text
            style={{
              color: colors.textSecondary,
              marginBottom: 8,
              fontSize: 14,
            }}
          >
            📍 {postoSelecionado.endereco}
          </Text>

          {postoSelecionado.distancia_m && (
            <Text
              style={{
                color: colors.textSecondary,
                marginBottom: 16,
                fontSize: 14,
                fontWeight: "500",
              }}
            >
              🛣️ Distância: {(postoSelecionado.distancia_m / 1000).toFixed(1)}{" "}
              km
            </Text>
          )}

          {/* BOTÃO TRAÇAR ROTA */}
          <TouchableOpacity
            style={[
              styles.btnRota,
              { backgroundColor: colors.surface, borderColor: colors.primary },
            ]}
            onPress={abrirRotaMapaApp}
          >
            <View
              style={{
                flexDirection: "row",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <Text
                style={{
                  color: colors.primary,
                  fontSize: 16,
                  fontWeight: "bold",
                }}
              >
                🧭 Traçar Rota
              </Text>
              {custoDaViagemFormatado && (
                <Text style={{ color: colors.textSecondary, fontSize: 13 }}>
                  {custoDaViagemFormatado}
                </Text>
              )}
            </View>
          </TouchableOpacity>

          <Text style={[styles.secaoTitulo, { color: colors.textPrimary }]}>
            Preços Cadastrados
          </Text>

          {isLoadingPrecos ? (
            <ActivityIndicator
              size="large"
              color={colors.primary}
              style={{ marginVertical: 20 }}
            />
          ) : precosDetalhe.length === 0 ? (
            <Text style={{ color: colors.textSecondary, marginVertical: 10 }}>
              Nenhum preço registrado para este posto recentemente.
            </Text>
          ) : (
            precosDetalhe.map((item, index) => {
              const isMainFuel =
                item.tipo_combustivel === postoSelecionado.combustivel;
              return (
                <View
                  key={index}
                  style={[
                    styles.cardPrecoDetalhe,
                    {
                      backgroundColor: colors.surface,
                      borderColor: colors.border,
                    },
                  ]}
                >
                  <View>
                    <Text
                      style={[
                        styles.combustivelDetalheText,
                        { color: colors.textPrimary },
                      ]}
                    >
                      {item.tipo_combustivel}
                    </Text>
                    <Text
                      style={{
                        color: colors.textSecondary,
                        fontSize: 12,
                        marginTop: 4,
                      }}
                    >
                      Atualizado em: {item.data_formatada}
                    </Text>
                  </View>
                  <View
                    style={[
                      styles.precoContainerGrande,
                      {
                        borderColor: isMainFuel
                          ? postoSelecionado.cor
                          : colors.border,
                        backgroundColor: isMainFuel
                          ? "#121212"
                          : colors.surface,
                      },
                    ]}
                  >
                    <Text
                      style={[
                        styles.precoTextGrande,
                        {
                          color: isMainFuel
                            ? postoSelecionado.cor
                            : colors.textPrimary,
                        },
                      ]}
                    >
                      R$ {item.preco.toFixed(2).replace(".", ",")}
                    </Text>
                  </View>
                </View>
              );
            })
          )}

          <TouchableOpacity
            style={[
              styles.btnAtualizarPreco,
              { backgroundColor: colors.primary },
            ]}
            onPress={abrirModalPreco}
          >
            <Text style={styles.btnAtualizarText}>Registrar Novo Preço</Text>
          </TouchableOpacity>
        </View>
      );
    }

    return (
      <View style={styles.sheetContent}>
        <View style={styles.sheetHeader}>
          <Text style={[styles.sheetTitle, { color: colors.textPrimary }]}>
            Postos na Região
          </Text>
          <Text style={[styles.sheetSubtitle, { color: colors.textSecondary }]}>
            {postos.length} postos encontrados.
          </Text>
        </View>

        {postos.map((posto) => (
          <TouchableOpacity
            key={posto.id}
            style={[styles.postoCard, { borderBottomColor: colors.border }]}
            onPress={() => focarNoPosto(posto)}
          >
            <View style={styles.postoInfo}>
              <Text style={[styles.postoNome, { color: colors.textPrimary }]}>
                {posto.nome}
              </Text>
              <Text
                style={[
                  styles.combustivelText,
                  { color: colors.textSecondary },
                ]}
              >
                ⛽ {posto.combustivel}
              </Text>
              <Text
                style={{ color: colors.textSecondary, fontSize: 12 }}
                numberOfLines={1}
              >
                {posto.distancia_m
                  ? `📍 ${(posto.distancia_m / 1000).toFixed(1)} km - `
                  : `📍 `}
                {posto.endereco}
              </Text>
            </View>
            <View style={styles.precoContainerLista}>
              <Text style={[styles.precoTextLista, { color: posto.cor }]}>
                R$ {posto.rotulo}
              </Text>
            </View>
          </TouchableOpacity>
        ))}
      </View>
    );
  };

  return (
    <GestureHandlerRootView style={styles.container}>
      <MapaLeaflet
        ref={mapaRef}
        postos={postos}
        usuario={usuario}
        onSelecionarPosto={handlePinoClicado}
      />

      <View style={styles.fabContainer}>
        {/* BOTÃO ATUALIZAR GPS */}
        <TouchableOpacity
          style={[
            styles.fab,
            {
              backgroundColor: colors.surface,
              borderColor: colors.border,
              marginBottom: 12,
            },
          ]}
          onPress={() => buscarLocalizacaoEPostos(true)}
          disabled={isLoadingLocalizacao}
        >
          {isLoadingLocalizacao ? (
            <ActivityIndicator size="small" color={colors.primary} />
          ) : (
            <Text style={{ fontSize: 20 }}>📍</Text>
          )}
        </TouchableOpacity>

        {/* NOVO BOTÃO EMERGÊNCIA */}
        <TouchableOpacity
          style={[
            styles.fab,
            { backgroundColor: "#EF4444", borderColor: "#B91C1C" },
          ]} // Vermelho chamativo
          onPress={handleEmergencia}
        >
          <Text style={{ fontSize: 20 }}>⛽</Text>
        </TouchableOpacity>
      </View>

      <BottomSheet
        ref={bottomSheetRef}
        index={0}
        snapPoints={snapPoints}
        backgroundStyle={{ backgroundColor: colors.background }}
        handleIndicatorStyle={{ backgroundColor: colors.textSecondary }}
        style={
          Platform.OS === "web"
            ? { width: "100%", maxWidth: 480, alignSelf: "center" }
            : {}
        }
      >
        <BottomSheetScrollView>{renderConteudoGaveta()}</BottomSheetScrollView>
      </BottomSheet>

      {/* MODAL DE PREÇOS MANTIDO INTACTO */}
      <Modal
        visible={modalVisivel}
        transparent
        animationType="fade"
        onRequestClose={() => setModalVisivel(false)}
      >
        <View style={styles.modalOverlay}>
          <View
            style={[
              styles.modalContent,
              { backgroundColor: colors.surface, borderColor: colors.border },
            ]}
          >
            <Text style={[styles.modalTitle, { color: colors.textPrimary }]}>
              Registrar Preço
            </Text>
            <Text style={{ color: colors.textSecondary, marginBottom: 16 }}>
              {postoSelecionado?.nome}
            </Text>
            <Text style={[styles.labelInput, { color: colors.textPrimary }]}>
              Combustível:
            </Text>
            <View style={styles.optionsContainer}>
              {OPCOES_COMBUSTIVEL.map((item) => (
                <TouchableOpacity
                  key={item}
                  style={[
                    styles.chipOption,
                    {
                      borderColor: colors.border,
                      backgroundColor:
                        combustivelSelecionado === item
                          ? colors.primary
                          : "transparent",
                    },
                  ]}
                  onPress={() => setCombustivelSelecionado(item)}
                >
                  <Text
                    style={{
                      color:
                        combustivelSelecionado === item
                          ? "#121212"
                          : colors.textPrimary,
                      fontSize: 12,
                      fontWeight: "bold",
                    }}
                  >
                    {item}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
            <Text
              style={[
                styles.labelInput,
                { color: colors.textPrimary, marginTop: 16 },
              ]}
            >
              Preço (R$):
            </Text>
            <TextInput
              style={[
                styles.inputPreco,
                {
                  backgroundColor: colors.background,
                  color: colors.textPrimary,
                  borderColor: colors.border,
                },
              ]}
              placeholder="Ex: 5,89"
              placeholderTextColor={colors.textSecondary}
              keyboardType="decimal-pad"
              value={novoPrecoInput}
              onChangeText={setNovoPrecoInput}
            />
            <View style={styles.modalButtonsContainer}>
              <TouchableOpacity
                style={[styles.btnCancel, { borderColor: colors.border }]}
                onPress={() => setModalVisivel(false)}
                disabled={isEnviandoPreco}
              >
                <Text
                  style={{ color: colors.textSecondary, fontWeight: "bold" }}
                >
                  Cancelar
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.btnSave, { backgroundColor: colors.primary }]}
                onPress={handleSalvarPreco}
                disabled={isEnviandoPreco}
              >
                {isEnviandoPreco ? (
                  <ActivityIndicator color="#121212" size="small" />
                ) : (
                  <Text style={{ color: "#121212", fontWeight: "bold" }}>
                    Salvar
                  </Text>
                )}
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  fabContainer: { position: "absolute", top: 60, right: 20, zIndex: 99 },
  fab: {
    width: 48,
    height: 48,
    borderRadius: 24,
    justifyContent: "center",
    alignItems: "center",
    borderWidth: 1,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 3.84,
    elevation: 5,
  },
  sheetContent: {
    paddingHorizontal: 20,
    paddingBottom: 24,
    width: "100%",
    maxWidth: 600,
    alignSelf: "center",
  },
  sheetHeader: { marginBottom: 16 },
  sheetTitle: { fontSize: 22, fontWeight: "bold", marginBottom: 2 },
  sheetSubtitle: { fontSize: 14 },
  postoCard: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 14,
    borderBottomWidth: 1,
  },
  postoInfo: { flex: 1, paddingRight: 12 },
  postoNome: { fontSize: 16, fontWeight: "bold", marginBottom: 4 },
  combustivelText: { fontSize: 13, fontWeight: "600", marginBottom: 4 },
  precoContainerLista: {
    backgroundColor: "#1E1E1E",
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 8,
    minWidth: 85,
    alignItems: "center",
  },
  precoTextLista: { fontSize: 16, fontWeight: "bold" },
  btnVoltar: { paddingVertical: 12, marginBottom: 8 },
  postoSelecionadoNome: { fontSize: 24, fontWeight: "bold", marginBottom: 2 },
  btnRota: {
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 16,
  },
  secaoTitulo: {
    fontSize: 18,
    fontWeight: "bold",
    marginTop: 8,
    marginBottom: 16,
  },
  cardPrecoDetalhe: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 12,
  },
  combustivelDetalheText: { fontSize: 16, fontWeight: "bold" },
  precoContainerGrande: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
    borderWidth: 1.5,
  },
  precoTextGrande: { fontSize: 20, fontWeight: "900" },
  btnAtualizarPreco: {
    marginTop: 24,
    paddingVertical: 16,
    borderRadius: 12,
    alignItems: "center",
  },
  btnAtualizarText: { color: "#121212", fontSize: 16, fontWeight: "bold" },
  modalOverlay: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.6)",
    justifyContent: "center",
    alignItems: "center",
    padding: 20,
  },
  modalContent: {
    width: "100%",
    maxWidth: 450,
    padding: 24,
    borderRadius: 16,
    borderWidth: 1,
  },
  modalTitle: { fontSize: 20, fontWeight: "bold", marginBottom: 4 },
  labelInput: { fontSize: 14, fontWeight: "bold", marginBottom: 8 },
  optionsContainer: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  chipOption: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 16,
    borderWidth: 1,
  },
  inputPreco: {
    height: 48,
    borderRadius: 8,
    borderWidth: 1,
    paddingHorizontal: 16,
    fontSize: 16,
  },
  modalButtonsContainer: {
    flexDirection: "row",
    justifyContent: "flex-end",
    gap: 12,
    marginTop: 24,
  },
  btnCancel: {
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 8,
    borderWidth: 1,
  },
  btnSave: {
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 8,
    justifyContent: "center",
    alignItems: "center",
  },
});
