import Ionicons from "@expo/vector-icons/Ionicons";
import {
    useNavigation,
    useRoute,
    type NavigationProp,
    type RouteProp,
} from "@react-navigation/native";
import { useEffect, useRef, useState } from "react";
import {
    ActivityIndicator,
    KeyboardAvoidingView,
    Modal,
    Platform,
    Pressable,
    ScrollView,
    Text,
    useWindowDimensions,
    View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { LeitorTotem } from "../../components/leitor-totem";
import { CartaoPosto } from "../../components/cartao-posto";
import {
    AppButton,
    AppField,
    Notice,
    Surface,
    useAppTheme,
} from "../../components/design";
import { useAuth } from "../../contexts/AuthContext";
import { useFiltrosPostos } from "../../contexts/FiltrosPostosContext";
import { useConsultaConta } from "../../hooks/useConsultaConta";
import type { Abas } from "../../routes/app.routes";
import { api } from "../../services/API";
import {
    criarEnvioPreco,
    FalhaCadastro,
    precoCadastro,
    produtoInicialCadastro,
    produtosCadastro,
    type ConfirmacaoPreco,
} from "../../services/cadastroPreco";
import {
    COMBUSTIVEIS,
    dataPublicacao,
    lerCatalogo,
    precoFormatado,
    type Combustivel,
    type PostoCatalogo,
} from "../../services/catalogoPostos";
import { lerTokenAtivo } from "../../services/sessao";
import { design } from "../../theme/design";
import { obterPosicao, type PosicaoGps } from "../../utils/localizacao";

const carregarCatalogo = async (signal: AbortSignal) =>
  lerCatalogo(
    (
      await api.get("/postos", {
        params: { referencia: "gasolina_comum" },
        signal,
      })
    ).data,
    "gasolina_comum",
  );

export default function AdicionarPreco() {
  const route = useRoute<RouteProp<Abas, "Adicionar">>();
  const { token, status } = useAuth();

  return (
    <FormularioPreco
      key={JSON.stringify([token, status, route.params?.solicitacao ?? "aba"])}
      parametros={route.params}
    />
  );
}

function FormularioPreco({ parametros }: { parametros: Abas["Adicionar"] }) {
  const navigation = useNavigation<NavigationProp<Abas>>();
  const { colors } = useAppTheme();
  const { userToken } = useAuth();
  const { filtros, recarregar } = useFiltrosPostos();
  const desktop = useWindowDimensions().width >= design.desktop;
  const consulta = useConsultaConta(carregarCatalogo);

  const [postoId, selecionarPosto] = useState<number | null>(
    parametros?.postoId ?? null,
  );

  const [codigo, selecionarCodigo] = useState<Combustivel | null>(
    parametros?.combustivel ?? filtros.referencia,
  );

  // A associação da foto pertence ao posto/produto e à sessão deste formulário.
  const [fotoUrl, definirFotoUrl] = useState<string | null>(null);
  const [textoPreco, definirPreco] = useState("");
  const [busca, definirBusca] = useState("");
  const [seletorAberto, abrirSeletor] = useState(false);
  const [enviando, definirEnvio] = useState(false);
  const [falha, definirFalha] = useState<FalhaCadastro | null>(null);
  const [confirmacao, definirConfirmacao] = useState<ConfirmacaoPreco | null>(
    null,
  );
  const [local, definirLocal] = useState<PosicaoGps | null>(null);
  const [checandoGps, definirChecagem] = useState(false);
  const [avisoGps, definirAvisoGps] = useState("");

  const montado = useRef(true);
  const emEnvio = useRef(false);
  const configurado = useRef<number | null>(null);

  const posto = consulta.dados?.find((p) => p.id === postoId);
  const opcoes = posto ? produtosCadastro(posto) : [];
  const info = COMBUSTIVEIS.find((p) => p.codigo === codigo);
  const oferta = posto?.combustiveis.find((o) => o.codigo === codigo);

  const incerto = falha?.tipo === "incerto";
  const bloqueado = enviando || incerto || confirmacao !== null;

  useEffect(() => {
    montado.current = true;

    return () => {
      montado.current = false;
    };
  }, []);

  useEffect(() => {
    if (posto && configurado.current !== posto.id) {
      configurado.current = posto.id;
      definirFotoUrl(null);

      selecionarCodigo((atual) =>
        produtoInicialCadastro(posto, atual ?? filtros.referencia),
      );
    }
  }, [posto, filtros.referencia]);

  function escolher(p: PostoCatalogo) {
    if (bloqueado) return;

    definirFotoUrl(null);
    selecionarPosto(p.id);
    selecionarCodigo(
      produtoInicialCadastro(p, parametros?.combustivel ?? filtros.referencia),
    );

    definirPreco("");
    definirFalha(null);
    definirLocal(null);
    definirAvisoGps("");
    abrirSeletor(false);
  }

  function atividade() {
    navigation.navigate("Perfil", {
      screen: "AtividadePessoal",
      initial: false,
    });
  }

  async function enviar() {
    if (emEnvio.current || bloqueado || !posto || !codigo || !userToken) {
      return;
    }

    emEnvio.current = true;

    const envio = criarEnvioPreco({
      tokenAtual: () => (montado.current ? lerTokenAtivo() : null),

      obterGps: async () => {
        const gps = await obterPosicao("registro");

        if (montado.current) {
          definirLocal(gps);
        }

        return gps;
      },

      postar: (payload, token) =>
        api.post("/precos", payload, {
          headers: {
            Authorization: "Bearer " + token,
          },
        }),
    });

    definirEnvio(true);
    definirFalha(null);
    definirAvisoGps("");

    const token = userToken;

    try {
      const resultado = await envio.enviar({
        posto,
        combustivel: codigo,
        textoPreco,
        fotoUrl,
        token,
      });

      recarregar();

      if (montado.current && lerTokenAtivo() === token) {
        definirConfirmacao(resultado);
        definirFotoUrl(null);
        definirPreco("");
        consulta.atualizar();
      }
    } catch (erro) {
      if (montado.current && lerTokenAtivo() === token) {
        definirFalha(
          erro instanceof FalhaCadastro
            ? erro
            : new FalhaCadastro(
                "incerto",
                "Não foi possível confirmar o registro. Confira sua atividade antes de tentar novamente.",
              ),
        );
      }
    } finally {
      emEnvio.current = false;

      if (montado.current) {
        definirEnvio(false);
      }
    }
  }

  async function verificarGps() {
    if (checandoGps || bloqueado) return;

    definirChecagem(true);
    definirAvisoGps("");

    try {
      const gps = await obterPosicao("registro");

      if (montado.current) {
        definirLocal(gps);
      }
    } catch (erro) {
      if (montado.current) {
        definirLocal(null);
        definirAvisoGps(
          erro instanceof Error ? erro.message : "Localização indisponível.",
        );
      }
    } finally {
      if (montado.current) {
        definirChecagem(false);
      }
    }
  }

  const encontrados = (consulta.dados ?? []).filter((p) =>
    (p.nome + " " + p.endereco + " " + (p.marca ?? ""))
      .toLocaleLowerCase("pt-BR")
      .includes(busca.trim().toLocaleLowerCase("pt-BR")),
  );

  return (
    <SafeAreaView
      edges={["top", "left", "right"]}
      style={{
        flex: 1,
        backgroundColor: colors.background,
      }}
    >
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={{
            padding: 20,
            flexGrow: 1,
          }}
        >
          <View
            style={{
              width: "100%",
              maxWidth: 1060,
              alignSelf: "center",
              gap: 20,
            }}
          >
            <Text
              accessibilityRole="header"
              style={{
                color: colors.textPrimary,
                fontSize: 28,
                fontWeight: "800",
              }}
            >
              Informar preço
            </Text>

            <Notice>
              Compartilhe o valor que você encontrou no posto, por unidade do
              combustível escolhido.
            </Notice>

            {confirmacao ? (
              <Surface>
                <Ionicons
                  name="checkmark-circle-outline"
                  size={48}
                  color={colors.success}
                  accessible={false}
                />

                <Text
                  accessibilityRole="header"
                  style={{
                    color: colors.textPrimary,
                    fontSize: 24,
                    fontWeight: "800",
                  }}
                >
                  Preço registrado
                </Text>

                <Notice>
                  Registro #{confirmacao.registoId} confirmado pelo servidor.
                </Notice>

                {oferta?.disponivel === null ? (
                  <Notice>
                    O preço fica disponível nos detalhes do posto. A oferta
                    deste combustível ainda precisa de confirmação para aparecer
                    no filtro.
                  </Notice>
                ) : null}

                <Text
                  style={{
                    color: colors.textPrimary,
                    fontSize: 24,
                    fontWeight: "800",
                  }}
                >
                  +{confirmacao.karmaGanho} Karma
                </Text>

                <AppButton label="Ver minha atividade" onPress={atividade} />

                <AppButton
                  label="Voltar ao Feed"
                  secondary
                  onPress={() => navigation.navigate("Feed")}
                />

                <AppButton
                  label="Informar outro preço"
                  secondary
                  onPress={() => {
                    definirConfirmacao(null);
                    definirFalha(null);
                  }}
                />
              </Surface>
            ) : (
              <View
                style={{
                  flexDirection: desktop ? "row" : "column",
                  alignItems: "stretch",
                  gap: 20,
                }}
              >
                <View
                  style={{
                    flex: 1,
                    minWidth: 0,
                    gap: 16,
                  }}
                >
                  <Surface>
                    <Text
                      style={{
                        color: colors.textPrimary,
                        fontSize: 20,
                        fontWeight: "800",
                      }}
                    >
                      1. Escolha o posto
                    </Text>

                    {posto ? (
                      <>
                        <Text
                          testID="posto-cadastro-selecionado"
                          style={{
                            color: colors.textPrimary,
                            fontSize: 19,
                            fontWeight: "700",
                          }}
                        >
                          {posto.nome}
                        </Text>

                        <Notice>
                          {posto.marca ?? "Marca não informada"}
                          {" · "}
                          {posto.endereco}
                        </Notice>
                      </>
                    ) : (
                      <Notice>
                        {consulta.loading
                          ? "Carregando catálogo..."
                          : postoId
                            ? "O posto solicitado não está no catálogo carregado. Atualize ou escolha outro posto."
                            : "Selecione o estabelecimento onde você está."}
                      </Notice>
                    )}

                    {consulta.erro ? (
                      <>
                        <Notice error>
                          Não foi possível atualizar o catálogo. Tente novamente
                          antes de enviar.
                        </Notice>

                        <AppButton
                          label="Atualizar catálogo"
                          secondary
                          onPress={consulta.atualizar}
                        />
                      </>
                    ) : null}

                    <AppButton
                      label={posto ? "Trocar posto" : "Escolher um posto"}
                      secondary
                      disabled={
                        bloqueado || consulta.loading || !!consulta.erro
                      }
                      onPress={() => abrirSeletor(true)}
                    />
                  </Surface>

                  <Surface>
                    <Text
                      style={{
                        color: colors.textPrimary,
                        fontSize: 20,
                        fontWeight: "800",
                      }}
                    >
                      2. Confira o combustível
                    </Text>

                    {!posto ? (
                      <Notice>
                        Escolha um posto para ver os produtos deste cadastro.
                      </Notice>
                    ) : !opcoes.length ? (
                      <Notice>
                        Nenhum produto está disponível para registro neste
                        cadastro.
                      </Notice>
                    ) : (
                      <View accessibilityRole="radiogroup" style={{ gap: 8 }}>
                        {opcoes.map((p) => (
                          <OpcaoCombustivel
                            key={p.codigo}
                            nome={p.nome}
                            cor={p.cor}
                            selecionado={codigo === p.codigo}
                            disabled={bloqueado}
                            onPress={() => {
                              definirFotoUrl(null);
                              selecionarCodigo(p.codigo);
                              definirPreco("");
                              definirFalha(null);
                            }}
                          />
                        ))}
                      </View>
                    )}

                    {oferta?.disponivel === null ? (
                      <Notice>
                        A disponibilidade deste produto ainda não foi confirmada
                        no catálogo. Informe apenas um preço que você observou
                        neste posto.
                      </Notice>
                    ) : null}

                    {oferta?.disponivel === false ? (
                      <Notice error>
                        A oferta deste combustível mudou. Selecione um produto
                        disponível.
                      </Notice>
                    ) : null}
                  </Surface>
                </View>

                <View
                  style={{
                    flex: 1,
                    minWidth: 0,
                    gap: 16,
                  }}
                >
                  {posto && posto.tipo_posto !== "Eletroposto" ? (
                    <LeitorTotem
                      key={posto.id}
                      postoId={posto.id}
                      bloqueado={bloqueado}
                      permitidos={produtosCadastro(posto).map((item) => item.codigo)}
                      limparComprovante={() => definirFotoUrl(null)}
                      usar={(combustivel, valor, comprovante) => {
                        // A sugestão só preenche o formulário; cadastrar exige outra ação.
                        if (!produtosCadastro(posto).some((item) => item.codigo === combustivel)) {
                          definirFalha(new FalhaCadastro("validacao", "O produto lido não está disponível para este posto."));
                          return;
                        }
                        selecionarCodigo(combustivel);
                        definirPreco(valor);
                        definirFotoUrl(comprovante);
                        definirFalha(null);
                      }}
                    />
                  ) : null}
                  {fotoUrl ? (
                    <Surface>
                      <Notice>Comprovante associado ao formulário. Remover não exclui a cópia do Dropbox.</Notice>
                      <AppButton label="Remover comprovante" secondary disabled={bloqueado}
                        onPress={() => definirFotoUrl(null)} />
                    </Surface>
                  ) : null}
                  <Surface>
                    <Text
                      style={{
                        color: colors.textPrimary,
                        fontSize: 20,
                        fontWeight: "800",
                      }}
                    >
                      3. Informe o valor
                    </Text>

                    <Text
                      style={{
                        color: colors.textPrimary,
                        fontWeight: "700",
                      }}
                    >
                      {info
                        ? info.nome + " · R$/" + info.unidade
                        : "Escolha o combustível"}
                    </Text>

                    <AppField
                      label="Preço observado"
                      value={textoPreco}
                      onChangeText={(valor) => {
                        definirPreco(valor);
                        definirFalha(null);
                      }}
                      editable={!!posto && !!codigo && !bloqueado}
                      keyboardType="decimal-pad"
                      inputMode="decimal"
                      placeholder="0,00"
                      maxLength={8}
                      style={{
                        fontSize: desktop ? 64 : 52,
                        fontWeight: "800",
                        textAlign: "center",
                        minHeight: 112,
                      }}
                    />

                    <Notice>
                      De R$ 0,01 a R$ 25,00 por unidade, com até duas casas
                      decimais.
                    </Notice>

                    {oferta?.preco !== null && oferta?.preco !== undefined ? (
                      <>
                        <Notice>
                          Último valor informado: {precoFormatado(oferta.preco)}{" "}
                          / {info?.unidade}
                        </Notice>

                        <Notice>
                          {oferta.autor_nome
                            ? "Por " + oferta.autor_nome + " · "
                            : ""}
                          {dataPublicacao(oferta.atualizado_em)}
                        </Notice>
                      </>
                    ) : posto && info ? (
                      <Notice>
                        Ainda não há preço informado para este produto.
                      </Notice>
                    ) : null}
                  </Surface>

                  <Surface>
                    <View
                      style={{
                        flexDirection: "row",
                        alignItems: "center",
                        gap: 8,
                      }}
                    >
                      <Ionicons
                        name="location-outline"
                        size={24}
                        color={colors.textPrimary}
                        accessible={false}
                      />

                      <Text
                        style={{
                          color: colors.textPrimary,
                          fontSize: 18,
                          fontWeight: "700",
                        }}
                      >
                        Localização do aparelho
                      </Text>
                    </View>

                    <Notice>
                      Esteja no posto. Ao enviar, consultaremos uma posição
                      atual e o servidor verificará sua proximidade.
                    </Notice>

                    {local ? (
                      <Notice>
                        Última leitura: precisão aproximada de ±
                        {Math.round(local.precisaoM)} m. A posição será
                        consultada novamente no envio.
                      </Notice>
                    ) : null}

                    {avisoGps ? <Notice error>{avisoGps}</Notice> : null}

                    <AppButton
                      label="Verificar minha localização"
                      secondary
                      busy={checandoGps}
                      disabled={bloqueado}
                      onPress={() => {
                        void verificarGps();
                      }}
                    />
                  </Surface>
                </View>
              </View>
            )}
          </View>
        </ScrollView>

        {!confirmacao ? (
          <View
            style={{
              borderTopWidth: 1,
              borderTopColor: colors.border,
              backgroundColor: colors.surface,
              padding: 12,
            }}
          >
            <View
              style={{
                width: "100%",
                maxWidth: 1060,
                alignSelf: "center",
                gap: 6,
              }}
            >
              {falha ? (
                <View style={{ gap: 8 }}>
                  <Notice error>{falha.message}</Notice>

                  {incerto ? (
                    <>
                      <AppButton
                        label="Conferir meus preços"
                        onPress={atividade}
                      />

                      <AppButton
                        label="Já conferi, preparar novo registro"
                        secondary
                        onPress={() => {
                          definirFalha(null);
                          definirPreco("");
                          consulta.atualizar();
                        }}
                      />
                    </>
                  ) : null}
                </View>
              ) : null}

              <AppButton
                label="Confirmar preço"
                busy={enviando}
                disabled={
                  !posto ||
                  !codigo ||
                  !opcoes.some((p) => p.codigo === codigo) ||
                  precoCadastro(textoPreco) === null ||
                  incerto ||
                  checandoGps ||
                  consulta.loading ||
                  consulta.erro
                }
                onPress={() => {
                  void enviar();
                }}
              />

              <Text
                style={{
                  color: colors.textSecondary,
                  fontSize: 12,
                  textAlign: "center",
                }}
              >
                O envio só é concluído após a confirmação do servidor.
              </Text>
            </View>
          </View>
        ) : null}
      </KeyboardAvoidingView>

      <Modal
        visible={seletorAberto}
        transparent
        animationType="slide"
        onRequestClose={() => abrirSeletor(false)}
      >
        <View
          style={{
            flex: 1,
            backgroundColor: "rgba(0,0,0,.45)",
            justifyContent: "flex-end",
            alignItems: "center",
          }}
        >
          <SafeAreaView
            edges={["left", "right", "bottom"]}
            style={{
              width: "100%",
              maxWidth: 780,
              maxHeight: "92%",
              backgroundColor: colors.background,
              borderTopLeftRadius: 24,
              borderTopRightRadius: 24,
            }}
          >
            <View style={{ padding: 16, gap: 12 }}>
              <Text
                accessibilityRole="header"
                style={{
                  color: colors.textPrimary,
                  fontSize: 23,
                  fontWeight: "800",
                }}
              >
                Escolher posto
              </Text>

              <AppField
                label="Buscar posto, endereço ou bandeira"
                value={busca}
                onChangeText={definirBusca}
                placeholder="Digite para buscar"
              />

              <Notice>
                {encontrados.length} postos no catálogo carregado. A seleção não
                altera os filtros do Mapa e do Feed.
              </Notice>
            </View>

            <ScrollView
              keyboardShouldPersistTaps="handled"
              contentContainerStyle={{
                paddingHorizontal: 16,
                gap: 12,
                paddingBottom: 16,
              }}
            >
              {consulta.loading ? (
                <ActivityIndicator
                  accessibilityLabel="Carregando postos para cadastro"
                  color={colors.textPrimary}
                />
              ) : null}

              {!encontrados.length ? (
                <Notice>Nenhum posto corresponde à busca.</Notice>
              ) : (
                encontrados.map((p) => (
                  <CartaoPosto
                    key={p.id}
                    posto={p}
                    selecionado={p.id === postoId}
                    rotuloAcao={"Selecionar " + p.nome}
                    onPress={() => escolher(p)}
                  />
                ))
              )}
            </ScrollView>

            <View style={{ padding: 16 }}>
              <AppButton
                label="Fechar seleção de posto"
                secondary
                onPress={() => abrirSeletor(false)}
              />
            </View>
          </SafeAreaView>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

function OpcaoCombustivel({
  nome,
  cor,
  selecionado,
  disabled,
  onPress,
}: {
  nome: string;
  cor: string;
  selecionado: boolean;
  disabled: boolean;
  onPress(): void;
}) {
  const { colors } = useAppTheme();
  const [foco, definirFoco] = useState(false);

  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityLabel={"Cadastrar " + nome}
      accessibilityState={{
        checked: selecionado,
        disabled,
      }}
      aria-checked={selecionado}
      aria-disabled={disabled}
      disabled={disabled}
      onPress={onPress}
      onFocus={() => definirFoco(true)}
      onBlur={() => definirFoco(false)}
      style={{
        minHeight: 52,
        borderRadius: 14,
        padding: 12,
        borderWidth: 2,
        borderColor: foco ? colors.focus : colors.border,
        backgroundColor: selecionado ? colors.selection : colors.surface,
        flexDirection: "row",
        gap: 10,
        alignItems: "center",
        opacity: disabled ? 0.6 : 1,
      }}
    >
      <View
        style={{
          height: 20,
          width: 6,
          borderRadius: 3,
          backgroundColor: cor,
        }}
      />

      <Text
        style={{
          color: colors.textPrimary,
          flex: 1,
          fontWeight: selecionado ? "700" : "500",
        }}
      >
        {nome}
      </Text>

      <Ionicons
        name={selecionado ? "radio-button-on" : "radio-button-off"}
        size={22}
        color={colors.textPrimary}
        accessible={false}
      />
    </Pressable>
  );
}
