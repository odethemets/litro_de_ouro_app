import { Ionicons } from "@expo/vector-icons";
import { Stack, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { api } from "../services/API";

interface Posto {
  id: number;
  nome: string;
  bairro?: string;
  endereco?: string;
  latitude: number;
  longitude: number;
  tipo_posto?: "Convencional" | "Eletroposto"; // Adicionado para identificar no frontend
}

// Arrays separados para manter a organização
const TIPOS_COMBUSTIVEL_CONVENCIONAL = [
  "Gasolina Comum",
  "Gasolina Aditivada",
  "Etanol",
  "Diesel",
];
const TIPOS_RECARGA_ELETRICA = ["Recarga Elétrica (kWh)"];

export default function RegistrarPrecoScreen() {
  const router = useRouter();

  const [postos, setPostos] = useState<Posto[]>([]);
  const [postoSelecionado, setPostoSelecionado] = useState<Posto | null>(null);
  const [tipoCombustivel, setTipoCombustivel] = useState("Gasolina Comum");
  const [precoInformado, setPrecoInformado] = useState("");
  const [busca, setBusca] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    carregarPostos();
  }, []);

  // Inteligência de troca automática: Se mudar o posto, adapta o tipo selecionado
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
      const response = await api.get("/postos/");
      setPostos(response.data);
      if (response.data.length > 0) {
        setPostoSelecionado(response.data[0]);
      }
    } catch (error: any) {
      Alert.alert("Erro", "Não foi possível carregar a lista de postos.");
    } finally {
      setLoading(false);
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
      const payload = {
        posto_id: Number(postoSelecionado.id),
        tipo_combustivel: tipoCombustivel,
        preco: precoFormatado,
        latitude: Number(postoSelecionado.latitude),
        longitude: Number(postoSelecionado.longitude),
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

  const postosFiltrados = postos.filter((p) => {
    const termo = busca.toLowerCase();
    return (
      p.nome.toLowerCase().includes(termo) ||
      (p.bairro && p.bairro.toLowerCase().includes(termo)) ||
      (p.endereco && p.endereco.toLowerCase().includes(termo))
    );
  });

  // Decide qual lista mostrar no ecrã com base no posto clicado
  const opcoesCombustivel =
    postoSelecionado?.tipo_posto === "Eletroposto"
      ? TIPOS_RECARGA_ELETRICA
      : TIPOS_COMBUSTIVEL_CONVENCIONAL;

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
          {/* Mapeamento Dinâmico */}
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
        </View>

        <TouchableOpacity
          style={styles.btnSalvar}
          activeOpacity={0.8}
          onPress={handleSalvarPreco}
          disabled={submitting}
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
    paddingHorizontal: 15,
    marginBottom: 30,
  },
  cifrao: { fontSize: 20, fontWeight: "bold", color: "#333", marginRight: 8 },
  inputPreco: {
    flex: 1,
    height: 50,
    fontSize: 22,
    fontWeight: "bold",
    color: "#333",
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
