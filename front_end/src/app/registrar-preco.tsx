import { Ionicons } from "@expo/vector-icons";
import * as ImagePicker from "expo-image-picker";
import { Stack, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Linking,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { api } from "../services/API";
import { ErroGps, obterPosicao, type PosicaoGps } from "../utils/localizacao";

interface Posto {
  id: number;
  nome: string;
  bairro?: string;
  endereco?: string;
  latitude: number;
  longitude: number;
  tipo_posto?: "Convencional" | "Eletroposto";
  distancia_m?: number;
}

/** Foto devolvida por POST /ia/ler-totem e o que a IA leu nela. */
interface FotoProva {
  url: string;
  postoId: number;
  /** Preços lidos na foto, por combustível. Ex.: { "Gasolina Comum": 6.29 } */
  precos: Record<string, number>;
}

/** Resposta de POST /ia/ler-totem. */
interface RespostaLerTotem {
  sucesso: boolean;
  precos?: Record<string, number>;
  foto_url?: string | null; // null/ausente se o Dropbox falhou
}

/** Corpo de POST /precos. `foto_url` é omitido nos registros manuais. */
interface PrecoPayload {
  posto_id: number;
  tipo_combustivel: string;
  preco: number;
  latitude: number;
  longitude: number;
  precisao_m: number | null;
  simulada: boolean;
  foto_url?: string;
}

const TIPOS_COMBUSTIVEL_CONVENCIONAL = [
  "Gasolina Comum",
  "Gasolina Aditivada",
  "Etanol",
  "Diesel",
];
const TIPOS_RECARGA_ELETRICA = ["Recarga Elétrica (kWh)"];
const TIMEOUT_IA_MS = 60000;

const formatarDistancia = (metros: number) =>
  metros < 1000
    ? `${metros} m`
    : `${(metros / 1000).toFixed(1).replace(".", ",")} km`;

/**
 * A foto só vale como prova do que ela realmente mostra: mesmo posto e o MESMO preço que a IA leu
 * para o combustível escolhido. Se o utilizador mudou de posto ou editou o valor, é registro manual.
 */
const fotoProvaValida = (
  prova: FotoProva | null,
  postoId: number,
  tipoCombustivel: string,
  preco: number,
): string | null => {
  if (!prova || prova.postoId !== postoId) return null;
  const lido = prova.precos[tipoCombustivel];
  return typeof lido === "number" && Math.abs(lido - preco) < 0.005
    ? prova.url
    : null;
};

export default function RegistrarPrecoScreen() {
  const router = useRouter();

  const [postos, setPostos] = useState<Posto[]>([]);
  const [postoSelecionado, setPostoSelecionado] = useState<Posto | null>(null);
  const [tipoCombustivel, setTipoCombustivel] = useState("Gasolina Comum");
  const [precoInformado, setPrecoInformado] = useState("");
  const [busca, setBusca] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [analisandoIA, setAnalisandoIA] = useState(false);
  const [fotoProva, setFotoProva] = useState<FotoProva | null>(null); // prova da última leitura por IA

  useEffect(() => {
    carregarPostos();
  }, []);

  useEffect(() => {
    if (postoSelecionado) {
      if (postoSelecionado.tipo_posto === "Eletroposto") {
        setTipoCombustivel(TIPOS_RECARGA_ELETRICA[0]);
      } else if (tipoCombustivel === TIPOS_RECARGA_ELETRICA[0]) {
        setTipoCombustivel(TIPOS_COMBUSTIVEL_CONVENCIONAL[0]);
      }
    }
  }, [postoSelecionado]);

  const carregarPostos = async () => {
    try {
      setLoading(true);
      let params: { lat?: number; lng?: number } = {};
      try {
        const pos = await obterPosicao("mapa");
        params = { lat: pos.latitude, lng: pos.longitude };
      } catch {
        // segue sem coordenadas
      }
      const response = await api.get("/postos/", { params });
      const lista: Posto[] = Array.isArray(response.data) ? response.data : [];
      setPostos(lista);
      if (lista.length > 0) {
        setPostoSelecionado(lista[0]);
      }
    } catch (error: any) {
      Alert.alert("Erro", "Não foi possível carregar a lista de postos.");
    } finally {
      setLoading(false);
    }
  };

  const obterGpsOuAvisar = async (): Promise<PosicaoGps | null> => {
    try {
      return await obterPosicao("registro");
    } catch (e) {
      if (e instanceof ErroGps) {
        Alert.alert(
          "Localização necessária",
          e.message,
          e.codigo === "PERMISSAO_NEGADA" && !e.podePedirNovamente
            ? [
                {
                  text: "Abrir configurações",
                  onPress: () => Linking.openSettings(),
                },
                { text: "Cancelar", style: "cancel" },
              ]
            : undefined,
        );
        return null;
      }
      throw e;
    }
  };

  const handleSalvarPreco = async () => {
    if (!postoSelecionado) return Alert.alert("Atenção", "Selecione um posto.");
    if (!precoInformado.trim())
      return Alert.alert("Atenção", "Informe o preço.");

    const precoFormatado = parseFloat(precoInformado.replace(",", "."));
    if (isNaN(precoFormatado) || precoFormatado <= 0) {
      return Alert.alert("Atenção", "Informe um valor numérico válido.");
    }

    try {
      setSubmitting(true);

      const pos = await obterGpsOuAvisar();
      if (!pos) return;

      // Só anexa a foto se ela ainda corresponde a este posto e a este preço (senão, registro manual).
      const foto_url = fotoProvaValida(
        fotoProva,
        postoSelecionado.id,
        tipoCombustivel,
        precoFormatado,
      );

      const payload: PrecoPayload = {
        posto_id: Number(postoSelecionado.id),
        tipo_combustivel: tipoCombustivel,
        preco: precoFormatado,
        latitude: pos.latitude,
        longitude: pos.longitude,
        precisao_m: pos.precisaoM,
        simulada: pos.simulada,
        ...(foto_url ? { foto_url } : {}),
      };

      await api.post("/precos/", payload);
      Alert.alert("Sucesso!", `Preço do ${tipoCombustivel} registado!`, [
        { text: "OK", onPress: () => router.replace("/") },
      ]);
    } catch (error: any) {
      const erroServidor =
        error.response?.data?.error || "Erro ao salvar o preço.";
      Alert.alert("Aviso", erroServidor);
    } finally {
      setSubmitting(false);
    }
  };

  const handleLerTotemComIA = async () => {
    if (!postoSelecionado) {
      Alert.alert("Atenção", "Selecione o posto antes de ler o totem.");
      return;
    }

    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== "granted") {
      Alert.alert(
        "Permissão Necessária",
        "Precisamos de acesso à câmara para ler o totem com Inteligência Artificial.",
      );
      return;
    }

    let result = await ImagePicker.launchCameraAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      allowsEditing: true,
      quality: 0.5,
    });

    if (!result.canceled && result.assets && result.assets.length > 0) {
      const uri = result.assets[0].uri;
      enviarParaIA(uri, postoSelecionado);
    }
  };

  const enviarParaIA = async (imagemUri: string, posto: Posto) => {
    try {
      setAnalisandoIA(true);

      const pos = await obterGpsOuAvisar();
      if (!pos) return;

      const formData = new FormData();
      formData.append("foto", {
        uri: imagemUri,
        type: "image/jpeg",
        name: "totem.jpg",
      } as any);
      formData.append("posto_id", String(posto.id));
      formData.append("latitude", String(pos.latitude));
      formData.append("longitude", String(pos.longitude));
      if (pos.precisaoM !== null)
        formData.append("precisao_m", String(pos.precisaoM));
      formData.append("simulada", pos.simulada ? "true" : "false");

      const response = await api.post<RespostaLerTotem>(
        "/ia/ler-totem",
        formData,
        {
          headers: {
            "Content-Type": "multipart/form-data",
          },
          timeout: TIMEOUT_IA_MS,
        },
      );

      const { sucesso, precos, foto_url } = response.data;

      if (sucesso && precos) {
        // Guarda a prova junto do que a IA leu; a leitura mais recente substitui a anterior.
        setFotoProva(
          foto_url ? { url: foto_url, postoId: posto.id, precos } : null,
        );

        if (precos[tipoCombustivel]) {
          setPrecoInformado(precos[tipoCombustivel].toString());
          Alert.alert(
            "Magia da IA ✨",
            `Preço lido automaticamente: R$ ${precos[tipoCombustivel]}`,
          );
        } else {
          Alert.alert(
            "Aviso",
            `A IA leu o totem, mas não encontrou explicitamente "${tipoCombustivel}". Valores encontrados: \n${JSON.stringify(precos, null, 2)}`,
          );
        }
      }
    } catch (error: any) {
      console.error("Erro na IA:", error);
      Alert.alert(
        "Erro",
        error.response?.data?.error ||
          "A IA não conseguiu ler a imagem. Tente tirar a foto mais perto e focada nos números.",
      );
    } finally {
      setAnalisandoIA(false);
    }
  };

  const listaSeguraDePostos = Array.isArray(postos) ? postos : [];

  const postosFiltrados = listaSeguraDePostos.filter((p) => {
    const termo = busca.toLowerCase();
    return (
      p.nome.toLowerCase().includes(termo) ||
      (p.bairro && p.bairro.toLowerCase().includes(termo)) ||
      (p.endereco && p.endereco.toLowerCase().includes(termo))
    );
  });

  const opcoesCombustivel =
    postoSelecionado?.tipo_posto === "Eletroposto"
      ? TIPOS_RECARGA_ELETRICA
      : TIPOS_COMBUSTIVEL_CONVENCIONAL;

  // Mostra ao utilizador se a foto vai seguir como prova (mesma regra do envio).
  const fotoAnexada =
    postoSelecionado !== null &&
    fotoProvaValida(
      fotoProva,
      postoSelecionado.id,
      tipoCombustivel,
      parseFloat(precoInformado.replace(",", ".")),
    ) !== null;

  return (
    <>
      <Stack.Screen options={{ headerShown: false }} />

      <ScrollView
        style={styles.container}
        contentContainerStyle={styles.content}
      >
        <TouchableOpacity
          style={styles.btnVoltar}
          onPress={() => {
            if (router.canGoBack()) {
              router.back();
            } else {
              router.replace("/");
            }
          }}
        >
          <Ionicons name="arrow-back" size={24} color="#333" />
          <Text style={styles.btnVoltarTexto}>Voltar</Text>
        </TouchableOpacity>

        <Text style={styles.titulo}>Registrar Preço</Text>
        <Text style={styles.subtitulo}>
          Ajude a comunidade atualizando o valor.
        </Text>

        <Text style={styles.label}>1. Selecione o Posto:</Text>

        <View style={styles.buscaContainer}>
          <Ionicons
            name="search"
            size={20}
            color="#666"
            style={{ marginRight: 8 }}
          />
          <TextInput
            style={styles.inputBusca}
            placeholder="Buscar por nome ou bairro..."
            placeholderTextColor="#999"
            value={busca}
            onChangeText={setBusca}
          />
          {busca.length > 0 && (
            <TouchableOpacity onPress={() => setBusca("")}>
              <Ionicons name="close-circle" size={18} color="#999" />
            </TouchableOpacity>
          )}
        </View>

        <View style={styles.listaPostos}>
          {postosFiltrados.map((item) => {
            const isSelected = postoSelecionado?.id === item.id;
            return (
              <TouchableOpacity
                key={item.id}
                style={[
                  styles.cardPosto,
                  isSelected && styles.cardPostoSelecionado,
                ]}
                activeOpacity={0.7}
                onPress={() => setPostoSelecionado(item)}
              >
                <Ionicons
                  name={isSelected ? "checkmark-circle" : "location-outline"}
                  size={22}
                  color={isSelected ? "#d79b00" : "#666"}
                />
                <View style={styles.infoPosto}>
                  <Text
                    style={[
                      styles.nomePosto,
                      isSelected && styles.nomePostoSelecionado,
                    ]}
                  >
                    {item.nome}
                  </Text>
                  <Text style={styles.enderecoPosto}>
                    {item.bairro || item.endereco || "João Pessoa - PB"}
                    {item.distancia_m !== undefined
                      ? ` • a ${formatarDistancia(item.distancia_m)}`
                      : ""}
                  </Text>
                </View>
              </TouchableOpacity>
            );
          })}
        </View>

        <Text style={styles.label}>2. Qual o Combustível?</Text>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={styles.scrollCombustivel}
        >
          {opcoesCombustivel.map((tipo) => (
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

        <Text style={styles.label}>3. Preço Atual (R$):</Text>
        <View style={styles.inputContainer}>
          <Text style={styles.cifrao}>R$</Text>
          <TextInput
            style={styles.inputPreco}
            placeholder="0,00"
            keyboardType="decimal-pad"
            value={precoInformado}
            onChangeText={setPrecoInformado}
          />

          {postoSelecionado?.tipo_posto !== "Eletroposto" && (
            <TouchableOpacity
              style={styles.btnIA}
              onPress={handleLerTotemComIA}
              disabled={analisandoIA}
            >
              {analisandoIA ? (
                <ActivityIndicator size="small" color="#FFF" />
              ) : (
                <Ionicons name="camera" size={24} color="#FFF" />
              )}
            </TouchableOpacity>
          )}
        </View>

        {fotoAnexada && (
          <Text
            style={[
              styles.subtitulo,
              { marginTop: -20, marginBottom: 20, color: "#10B981" },
            ]}
          >
            📷 Foto do totem anexada como prova
          </Text>
        )}

        <TouchableOpacity
          style={styles.btnSalvar}
          activeOpacity={0.8}
          onPress={handleSalvarPreco}
          disabled={submitting || analisandoIA}
        >
          {submitting ? (
            <ActivityIndicator color="#FFF" />
          ) : (
            <Text style={styles.btnSalvarTexto}>Confirmar e Salvar</Text>
          )}
        </TouchableOpacity>
      </ScrollView>
    </>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#F8F9FA" },
  content: { padding: 20, paddingTop: 50, paddingBottom: 100 },
  btnVoltar: { flexDirection: "row", alignItems: "center", marginBottom: 20 },
  btnVoltarTexto: {
    marginLeft: 8,
    fontSize: 16,
    color: "#333",
    fontWeight: "600",
  },
  titulo: { fontSize: 26, fontWeight: "bold", color: "#111" },
  subtitulo: { fontSize: 14, color: "#666", marginBottom: 25 },
  label: {
    fontSize: 16,
    fontWeight: "bold",
    color: "#333",
    marginBottom: 10,
    marginTop: 10,
  },
  buscaContainer: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#FFF",
    borderWidth: 1,
    borderColor: "#E2E8F0",
    borderRadius: 10,
    paddingHorizontal: 12,
    height: 44,
    marginBottom: 15,
  },
  inputBusca: {
    flex: 1,
    fontSize: 14,
    color: "#333",
  },
  listaPostos: { marginBottom: 15 },
  cardPosto: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#FFF",
    padding: 14,
    borderRadius: 12,
    marginBottom: 10,
    borderWidth: 1.5,
    borderColor: "#E2E8F0",
  },
  cardPostoSelecionado: { borderColor: "#d79b00", backgroundColor: "#FFF9E6" },
  infoPosto: { marginLeft: 12, flex: 1 },
  nomePosto: { fontSize: 16, fontWeight: "bold", color: "#333" },
  nomePostoSelecionado: { color: "#d79b00" },
  enderecoPosto: { fontSize: 13, color: "#777", marginTop: 2 },
  scrollCombustivel: { marginBottom: 25, maxHeight: 50 },
  chip: {
    backgroundColor: "#FFF",
    borderWidth: 1,
    borderColor: "#CCC",
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 20,
    marginRight: 10,
    height: 42,
  },
  chipSelecionado: { backgroundColor: "#d79b00", borderColor: "#d79b00" },
  chipTexto: { color: "#666", fontWeight: "bold" },
  chipTextoSelecionado: { color: "#FFF" },
  inputContainer: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#FFF",
    borderWidth: 1.5,
    borderColor: "#E2E8F0",
    borderRadius: 12,
    paddingLeft: 15,
    paddingRight: 5,
    marginBottom: 30,
    height: 60,
  },
  cifrao: { fontSize: 20, fontWeight: "bold", color: "#333", marginRight: 8 },
  inputPreco: {
    flex: 1,
    height: 50,
    fontSize: 22,
    fontWeight: "bold",
    color: "#333",
  },
  btnIA: {
    backgroundColor: "#10B981",
    width: 45,
    height: 45,
    borderRadius: 10,
    justifyContent: "center",
    alignItems: "center",
    elevation: 2,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 2,
  },
  btnSalvar: {
    backgroundColor: "#d79b00",
    paddingVertical: 15,
    borderRadius: 12,
    alignItems: "center",
    shadowColor: "#d79b00",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 5,
    elevation: 4,
  },
  btnSalvarTexto: { color: "#FFF", fontSize: 18, fontWeight: "bold" },
});
