// src/screens/Inicio/index.tsx
import BottomSheet, { BottomSheetScrollView } from "@gorhom/bottom-sheet";
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as Location from "expo-location";
import {
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ActivityIndicator,
  Linking,
  Modal,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";

import { FeedbackAcao } from "../../components/feedback-acao";
import MapaLeaflet from "../../components/mapa/MapaLeaflet";
import type {
  MapaLeafletHandle,
  PosicaoUsuario,
  PostoNoMapa,
} from "../../components/mapa/tipos";
import { ThemeContext } from "../../contexts/ThemeContext";
import { api } from "../../services/API";
import { registrarPostoVisto } from "../../services/historicoVistos";
import {
  falhaCadastroPreco,
  type MensagemAcao,
} from "../../utils/feedbackPostos";

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

const CONSUMO_MEDIO_KM_L = 10;

function normalizarPrecoCadastro(texto: string): number | null {
  const limpo = texto.trim();

  // Aceita vírgula ou ponto e até duas casas decimais.
  if (!/^\d+(?:[.,]\d{1,2})?$/.test(limpo)) return null;

  const numero = Number(limpo.replace(",", "."));

  return Number.isFinite(numero) && numero >= 0.01 && numero <= 25
    ? numero
    : null;
}

async function obterLocalizacaoParaCadastro() {
  const { status } = await Location.requestForegroundPermissionsAsync();

  if (status !== "granted") {
    throw new Error("Permita o acesso à localização para registrar um preço.");
  }

  let temporizador: ReturnType<typeof setTimeout> | undefined;

  try {
    return await Promise.race([
      Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.High,
      }),
      new Promise<never>((_, rejeitar) => {
        temporizador = setTimeout(() => {
          rejeitar(
            new Error(
              "A localização demorou a responder. Ative o GPS e tente novamente.",
            ),
          );
        }, 20000);
      }),
    ]);
  } finally {
    if (temporizador !== undefined) {
      clearTimeout(temporizador);
    }
  }
}

export default function Inicio() {
  const { colors } = useContext(ThemeContext);

  const mapaRef = useRef<MapaLeafletHandle>(null);
  const bottomSheetRef = useRef<BottomSheet>(null);
  const snapPoints = useMemo(() => ["15%", "45%", "85%"], []);

  const [feedback, setFeedback] = useState<MensagemAcao | null>(null);
  const [feedbackFormulario, setFeedbackFormulario] =
    useState<MensagemAcao | null>(null);
  const [isLoadingPostos, setIsLoadingPostos] = useState(true);
  const [erroPostos, setErroPostos] = useState("");
  const [erroPrecos, setErroPrecos] = useState("");

  const buscaEmAndamento = useRef(false);
  const envioEmAndamento = useRef(false);
  const postoSelecionadoId = useRef<number | null>(null);
  const requisicaoPrecos = useRef(0);

  // Estados da lista e localização.
  const [postos, setPostos] = useState<PostoDetalhado[]>([]);
  const [usuario, setUsuario] = useState<PosicaoUsuario | null>(null);
  const [isLoadingLocalizacao, setIsLoadingLocalizacao] = useState(false);

  // Estados dos detalhes.
  const [postoSelecionado, setPostoSelecionado] =
    useState<PostoDetalhado | null>(null);
  const [precosDetalhe, setPrecosDetalhe] = useState<any[]>([]);
  const [isLoadingPrecos, setIsLoadingPrecos] = useState(false);

  // Estados do formulário.
  const [modalVisivel, setModalVisivel] = useState(false);
  const [combustivelSelecionado, setCombustivelSelecionado] =
    useState("Gasolina Comum");
  const [novoPrecoInput, setNovoPrecoInput] = useState("");
  const [isEnviandoPreco, setIsEnviandoPreco] = useState(false);

  const combustiveisDoPosto =
    postoSelecionado?.combustivel === "Recarga Elétrica (kWh)"
      ? ["Recarga Elétrica (kWh)"]
      : OPCOES_COMBUSTIVEL.filter((item) => item !== "Recarga Elétrica (kWh)");

  const telaAtiva = useRef(true);

  const mapearDadosDoBanco = useCallback((dados: any[]): PostoDetalhado[] => {
    return dados.map((posto) => {
      const eletrico = posto.tipo_posto === "Eletroposto";

      const temPreco = posto.preco_gasolina && posto.preco_gasolina > 0;

      return {
        id: posto.id,
        lat: posto.latitude,
        lon: posto.longitude,
        nome: posto.nome,
        endereco: posto.bairro
          ? `${posto.endereco}\n${posto.bairro}`
          : posto.endereco,
        combustivel: eletrico ? "Recarga Elétrica (kWh)" : "Gasolina Comum",
        cor: eletrico ? "#3B82F6" : temPreco ? "#10B981" : "#9CA3AF",
        rotulo: temPreco
          ? posto.preco_gasolina.toFixed(2).replace(".", ",")
          : "---",
        distancia_m: posto.distancia_m,
      };
    });
  }, []);

  const buscarLocalizacaoEPostos = useCallback(
    (forcarRequisicao = false) => {
      if (buscaEmAndamento.current) return;

      buscaEmAndamento.current = true;

      // Esta operação obtém dados sem alterar estados React.
      const obterDados = async () => {
        let posicao: PosicaoUsuario | null = null;

        try {
          const { status } = await Location.requestForegroundPermissionsAsync();

          if (status === "granted") {
            const localizacao = await Location.getCurrentPositionAsync({
              accuracy: Location.Accuracy.Balanced,
            });

            posicao = {
              lat: localizacao.coords.latitude,
              lon: localizacao.coords.longitude,
              precisaoM: localizacao.coords.accuracy,
            };
          }
        } catch {
          posicao = null;
        }

        const endpoint = posicao
          ? `/postos?lat=${posicao.lat}&lng=${posicao.lon}`
          : "/postos";

        const response = await api.get(endpoint);

        return {
          posicao,
          resultado: mapearDadosDoBanco(response.data),
        };
      };

      // Atualizações de estado acontecem após a resposta assíncrona.
      return obterDados()
        .then(({ posicao, resultado }) => {
          if (!telaAtiva.current) return;

          setUsuario(posicao);
          setPostos(resultado);
          setErroPostos("");

          if (forcarRequisicao && posicao) {
            mapaRef.current?.centralizar(posicao.lat, posicao.lon, 14);
          }

          setFeedback(
            posicao
              ? {
                  tipo: "sucesso",
                  titulo: "Postos atualizados",
                  mensagem: resultado.length
                    ? `${resultado.length} postos encontrados na sua região.`
                    : "Nenhum posto encontrado nesta região.",
                }
              : {
                  tipo: "aviso",
                  titulo: "Localização indisponível",
                  mensagem:
                    "A lista foi carregada, mas as distâncias dependem da localização. Permita o acesso e atualize pelo botão de localização.",
                },
          );
        })
        .catch(() => {
          if (!telaAtiva.current) return;

          setErroPostos(
            "Não foi possível atualizar os postos. Os dados já carregados foram mantidos.",
          );

          setFeedback({
            tipo: "erro",
            titulo: "Falha ao buscar postos",
            mensagem:
              "Confira sua conexão e tente atualizar novamente pelo botão de localização.",
          });
        })
        .finally(() => {
          buscaEmAndamento.current = false;

          if (!telaAtiva.current) return;

          setIsLoadingPostos(false);
          setIsLoadingLocalizacao(false);
        });
    },
    [mapearDadosDoBanco],
  );

  // Os botões iniciam os indicadores de carregamento.
  const atualizarPostos = () => {
    if (buscaEmAndamento.current) return;

    setIsLoadingLocalizacao(true);
    setIsLoadingPostos(true);
    setErroPostos("");

    void buscarLocalizacaoEPostos(true);
  };

  useEffect(() => {
    telaAtiva.current = true;

    void buscarLocalizacaoEPostos(true);

    return () => {
      telaAtiva.current = false;
    };
  }, [buscarLocalizacaoEPostos]);
  const carregarPrecos = async (postoId: number, aposCadastro = false) => {
    const pedido = ++requisicaoPrecos.current;

    setIsLoadingPrecos(true);
    setErroPrecos("");

    try {
      const response = await api.get(`/postos/${postoId}/precos`);

      if (
        postoSelecionadoId.current === postoId &&
        pedido === requisicaoPrecos.current
      ) {
        setPrecosDetalhe(response.data);
      }
    } catch {
      if (
        postoSelecionadoId.current === postoId &&
        pedido === requisicaoPrecos.current
      ) {
        setErroPrecos(
          aposCadastro
            ? "O preço foi cadastrado, mas a consulta não foi atualizada. Tente consultar novamente."
            : "Não foi possível carregar os preços deste posto. Tente novamente.",
        );
      }
    } finally {
      if (
        postoSelecionadoId.current === postoId &&
        pedido === requisicaoPrecos.current
      ) {
        setIsLoadingPrecos(false);
      }
    }
  };

  const focarNoPosto = (posto: PostoDetalhado) => {
    postoSelecionadoId.current = posto.id;
    setPostoSelecionado(posto);
    setPrecosDetalhe([]);
    setErroPrecos("");

    mapaRef.current?.centralizar(posto.lat, posto.lon, 16);
    bottomSheetRef.current?.snapToIndex(1);

    void registrarPostoVisto({
      id: posto.id,
      nome: posto.nome,
      endereco: posto.endereco,
    });

    void carregarPrecos(posto.id);
  };

  const handlePinoClicado = (id: number) => {
    const posto = postos.find((p) => p.id === id);

    if (posto) {
      focarNoPosto(posto);
    }
  };

  const handleVoltarParaLista = () => {
    postoSelecionadoId.current = null;
    requisicaoPrecos.current += 1;

    setPostoSelecionado(null);
    setPrecosDetalhe([]);
    setErroPrecos("");
    setIsLoadingPrecos(false);

    bottomSheetRef.current?.snapToIndex(1);

    if (usuario) {
      mapaRef.current?.centralizar(usuario.lat, usuario.lon, 14);
    }
  };

  const abrirRotaMapaApp = async () => {
    if (!postoSelecionado) return;

    try {
      await Linking.openURL(
        `https://www.google.com/maps/dir/?api=1&destination=${postoSelecionado.lat},${postoSelecionado.lon}`,
      );

      setFeedback({
        tipo: "info",
        titulo: "Rota solicitada",
        mensagem: `Destino: ${postoSelecionado.nome}.`,
      });
    } catch {
      setFeedback({
        tipo: "erro",
        titulo: "Não foi possível abrir a rota",
        mensagem: "Confira sua conexão e tente novamente.",
      });
    }
  };

  const handleEmergencia = () => {
    if (postos.length === 0) {
      setFeedback({
        tipo: "aviso",
        titulo: "Nenhum posto disponível",
        mensagem: "Atualize a lista antes de buscar o posto mais próximo.",
      });
      return;
    }

    const candidatos = postos.filter((p) => Number.isFinite(p.distancia_m));

    if (!candidatos.length) {
      setFeedback({
        tipo: "aviso",
        titulo: "Precisamos da sua localização",
        mensagem:
          "Permita o acesso à localização e atualize a lista para encontrar o posto mais próximo.",
      });
      return;
    }

    candidatos.sort((a, b) => a.distancia_m! - b.distancia_m!);

    const maisProximo = candidatos[0];

    focarNoPosto(maisProximo);

    setFeedback({
      tipo: "info",
      titulo: "Posto mais próximo selecionado",
      mensagem: maisProximo.nome,
    });
  };

  const abrirModalPreco = async () => {
    if (envioEmAndamento.current || !postoSelecionado) return;

    try {
      const token = await AsyncStorage.getItem("@LitroDeOuro:token");

      if (!token) {
        setFeedback({
          tipo: "aviso",
          titulo: "Faça login para cadastrar",
          mensagem:
            "Sua sessão não está disponível. Entre novamente para registrar um preço.",
        });
        return;
      }

      setNovoPrecoInput("");
      setCombustivelSelecionado(postoSelecionado.combustivel);
      setFeedbackFormulario(null);
      setFeedback(null);
      setModalVisivel(true);
    } catch {
      setFeedback({
        tipo: "erro",
        titulo: "Não foi possível verificar a sessão",
        mensagem: "Tente novamente antes de cadastrar o preço.",
      });
    }
  };

  const handleSalvarPreco = async () => {
    if (envioEmAndamento.current) return;

    const posto = postoSelecionado;
    if (!posto) return;

    const valor = normalizarPrecoCadastro(novoPrecoInput);

    if (valor === null) {
      setFeedbackFormulario({
        tipo: "erro",
        titulo: "Confira o preço",
        mensagem:
          "Informe um valor entre R$ 0,01 e R$ 25,00, com até duas casas decimais. Exemplo: 5,89.",
      });
      return;
    }

    const combustivel = combustivelSelecionado;

    envioEmAndamento.current = true;
    setIsEnviandoPreco(true);
    setFeedbackFormulario(null);

    try {
      const token = await AsyncStorage.getItem("@LitroDeOuro:token");

      if (!token) {
        setFeedbackFormulario({
          tipo: "erro",
          titulo: "Sessão indisponível",
          mensagem: "Entre novamente para cadastrar este preço.",
        });
        return;
      }

      // Solicita uma posição nova no momento do cadastro.
      const localizacao = await obterLocalizacaoParaCadastro().catch(
        (erro: unknown) => {
          setFeedbackFormulario({
            tipo: "aviso",
            titulo: "Precisamos da sua localização",
            mensagem:
              erro instanceof Error
                ? erro.message
                : "Não foi possível obter sua localização. Ative o GPS e tente novamente.",
          });

          return null;
        },
      );

      if (!localizacao) return;

      const { latitude, longitude, accuracy } = localizacao.coords;

      const simulada = "mocked" in localizacao && localizacao.mocked === true;

      setUsuario({
        lat: latitude,
        lon: longitude,
        precisaoM: accuracy,
      });

      await api.post(
        `/postos/${posto.id}/precos`,
        {
          tipo_combustivel: combustivel,
          preco: valor,
          latitude,
          longitude,
          precisao_m: accuracy,
          simulada,
        },
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        },
      );

      // Exibe sucesso somente depois da confirmação da API.
      const formatado = valor.toFixed(2).replace(".", ",");

      setModalVisivel(false);

      setFeedback({
        tipo: "sucesso",
        titulo: "Preço cadastrado",
        mensagem: `${combustivel}: R$ ${formatado} em ${posto.nome}. Você ganhou +5 pontos de Karma!`,
      });

      const atualizar = (p: PostoDetalhado) =>
        p.id === posto.id && p.combustivel === combustivel
          ? {
              ...p,
              rotulo: formatado,
              cor:
                combustivel === "Recarga Elétrica (kWh)"
                  ? "#3B82F6"
                  : "#10B981",
            }
          : p;

      setPostos((anteriores) => anteriores.map(atualizar));

      if (postoSelecionadoId.current === posto.id) {
        setPostoSelecionado((atual) => (atual ? atualizar(atual) : atual));

        setPrecosDetalhe((anteriores) => [
          ...anteriores.filter((p) => p.tipo_combustivel !== combustivel),
          {
            tipo_combustivel: combustivel,
            preco: valor,
            data_formatada: "Agora",
          },
        ]);

        // Falha na leitura posterior não desfaz o cadastro confirmado.
        void carregarPrecos(posto.id, true);
      }
    } catch (erro: unknown) {
      setFeedbackFormulario(falhaCadastroPreco(erro));
    } finally {
      envioEmAndamento.current = false;
      setIsEnviandoPreco(false);
    }
  };

  const renderConteudoGaveta = () => {
    if (postoSelecionado) {
      let custoDaViagemFormatado = null;

      if (postoSelecionado.distancia_m && precosDetalhe.length > 0) {
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

          <TouchableOpacity
            style={[
              styles.btnRota,
              {
                backgroundColor: colors.surface,
                borderColor: colors.primary,
              },
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
                <Text
                  style={{
                    color: colors.textSecondary,
                    fontSize: 13,
                  }}
                >
                  {custoDaViagemFormatado}
                </Text>
              )}
            </View>
          </TouchableOpacity>

          <Text style={[styles.secaoTitulo, { color: colors.textPrimary }]}>
            Preços Cadastrados
          </Text>

          {erroPrecos ? (
            <View style={{ marginBottom: 12 }}>
              <FeedbackAcao
                feedback={{
                  tipo: "aviso",
                  titulo: "Consulta não atualizada",
                  mensagem: erroPrecos,
                }}
                acao={{
                  rotulo: "Consultar novamente",
                  executar: () => {
                    void carregarPrecos(postoSelecionado.id);
                  },
                }}
              />
            </View>
          ) : null}

          {isLoadingPrecos ? (
            <ActivityIndicator
              size="large"
              color={colors.primary}
              style={{ marginVertical: 20 }}
            />
          ) : precosDetalhe.length === 0 && !erroPrecos ? (
            <Text
              style={{
                color: colors.textSecondary,
                marginVertical: 10,
              }}
            >
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
            {isLoadingPostos
              ? "Buscando postos…"
              : `${postos.length} postos encontrados.`}
          </Text>
        </View>

        {isLoadingPostos && (
          <ActivityIndicator
            color={colors.primary}
            style={{ marginVertical: 16 }}
          />
        )}

        {erroPostos ? (
          <FeedbackAcao
            feedback={{
              tipo: "erro",
              titulo: "Lista não atualizada",
              mensagem: erroPostos,
            }}
            acao={{
              rotulo: "Tentar novamente",
              executar: () => {
                atualizarPostos();
              },
            }}
          />
        ) : !isLoadingPostos && postos.length === 0 ? (
          <Text
            style={{
              color: colors.textSecondary,
              marginVertical: 16,
            }}
          >
            Nenhum posto encontrado. Tente atualizar a localização.
          </Text>
        ) : null}

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
                style={{
                  color: colors.textSecondary,
                  fontSize: 12,
                }}
                numberOfLines={1}
              >
                {posto.distancia_m
                  ? `📍 ${(posto.distancia_m / 1000).toFixed(1)} km - `
                  : "📍 "}
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
        <TouchableOpacity
          style={[
            styles.fab,
            {
              backgroundColor: colors.surface,
              borderColor: colors.border,
              marginBottom: 12,
            },
          ]}
          onPress={atualizarPostos}
          disabled={isLoadingLocalizacao || isLoadingPostos}
        >
          {isLoadingLocalizacao || isLoadingPostos ? (
            <ActivityIndicator size="small" color={colors.primary} />
          ) : (
            <Text style={{ fontSize: 20 }}>📍</Text>
          )}
        </TouchableOpacity>

        <TouchableOpacity
          style={[
            styles.fab,
            {
              backgroundColor: "#EF4444",
              borderColor: "#B91C1C",
            },
          ]}
          onPress={handleEmergencia}
        >
          <Text style={{ fontSize: 20 }}>⛽</Text>
        </TouchableOpacity>
      </View>

      <BottomSheet
        ref={bottomSheetRef}
        index={0}
        snapPoints={snapPoints}
        backgroundStyle={{
          backgroundColor: colors.background,
        }}
        handleIndicatorStyle={{
          backgroundColor: colors.textSecondary,
        }}
        style={
          Platform.OS === "web"
            ? {
                width: "100%",
                maxWidth: 480,
                alignSelf: "center",
              }
            : {}
        }
      >
        <BottomSheetScrollView>{renderConteudoGaveta()}</BottomSheetScrollView>
      </BottomSheet>

      {!modalVisivel && feedback && (
        <View style={styles.feedbackOverlay}>
          <FeedbackAcao feedback={feedback} onClose={() => setFeedback(null)} />
        </View>
      )}

      <Modal
        visible={modalVisivel}
        transparent
        animationType="fade"
        onRequestClose={() => {
          if (!envioEmAndamento.current) {
            setModalVisivel(false);
          }
        }}
      >
        <View style={styles.modalOverlay}>
          <View
            style={[
              styles.modalContent,
              {
                backgroundColor: colors.surface,
                borderColor: colors.border,
              },
            ]}
          >
            <Text style={[styles.modalTitle, { color: colors.textPrimary }]}>
              Registrar Preço
            </Text>

            <Text
              style={{
                color: colors.textSecondary,
                marginBottom: 16,
              }}
            >
              {postoSelecionado?.nome}
            </Text>

            {feedbackFormulario && (
              <View style={{ marginBottom: 16 }}>
                <FeedbackAcao
                  feedback={feedbackFormulario}
                  onClose={() => setFeedbackFormulario(null)}
                />
              </View>
            )}

            <Text style={[styles.labelInput, { color: colors.textPrimary }]}>
              Combustível:
            </Text>

            <View style={styles.optionsContainer}>
              {combustiveisDoPosto.map((item) => (
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
                  disabled={isEnviandoPreco}
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
                {
                  color: colors.textPrimary,
                  marginTop: 16,
                },
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
              editable={!isEnviandoPreco}
            />

            <View style={styles.modalButtonsContainer}>
              <TouchableOpacity
                style={[styles.btnCancel, { borderColor: colors.border }]}
                onPress={() => {
                  if (!envioEmAndamento.current) {
                    setModalVisivel(false);
                  }
                }}
                disabled={isEnviandoPreco}
              >
                <Text
                  style={{
                    color: colors.textSecondary,
                    fontWeight: "bold",
                  }}
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
                  <View
                    style={{
                      flexDirection: "row",
                      alignItems: "center",
                      gap: 8,
                    }}
                  >
                    <ActivityIndicator color="#121212" size="small" />
                    <Text
                      style={{
                        color: "#121212",
                        fontWeight: "bold",
                      }}
                    >
                      Cadastrando…
                    </Text>
                  </View>
                ) : (
                  <Text
                    style={{
                      color: "#121212",
                      fontWeight: "bold",
                    }}
                  >
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
  feedbackOverlay: {
    position: "absolute",
    top: 16,
    left: 16,
    right: 84,
    zIndex: 100,
    elevation: 8,
  },
  fabContainer: {
    position: "absolute",
    top: 60,
    right: 20,
    zIndex: 99,
  },
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
  sheetTitle: {
    fontSize: 22,
    fontWeight: "bold",
    marginBottom: 2,
  },
  sheetSubtitle: { fontSize: 14 },
  postoCard: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 14,
    borderBottomWidth: 1,
  },
  postoInfo: { flex: 1, paddingRight: 12 },
  postoNome: {
    fontSize: 16,
    fontWeight: "bold",
    marginBottom: 4,
  },
  combustivelText: {
    fontSize: 13,
    fontWeight: "600",
    marginBottom: 4,
  },
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
  postoSelecionadoNome: {
    fontSize: 24,
    fontWeight: "bold",
    marginBottom: 2,
  },
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
  combustivelDetalheText: {
    fontSize: 16,
    fontWeight: "bold",
  },
  precoContainerGrande: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
    borderWidth: 1.5,
  },
  precoTextGrande: {
    fontSize: 20,
    fontWeight: "900",
  },
  btnAtualizarPreco: {
    marginTop: 24,
    paddingVertical: 16,
    borderRadius: 12,
    alignItems: "center",
  },
  btnAtualizarText: {
    color: "#121212",
    fontSize: 16,
    fontWeight: "bold",
  },
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
  modalTitle: {
    fontSize: 20,
    fontWeight: "bold",
    marginBottom: 4,
  },
  labelInput: {
    fontSize: 14,
    fontWeight: "bold",
    marginBottom: 8,
  },
  optionsContainer: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 6,
  },
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
