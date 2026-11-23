import {
  useNavigation,
  useRoute,
  type NavigationProp,
  type RouteProp,
} from "@react-navigation/native";
import { useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import {
  CamposPrecos,
  RevisaoPrecos,
  SugestoesPrecos,
  TextoPrecos,
} from "../../components/cadastro/campos-precos";
import { SeletorPosto } from "../../components/cadastro/seletor-posto";
import {
  AppButton,
  Notice,
  Page,
  Surface,
  useAppTheme,
} from "../../components/design";
import { LeitorTotem } from "../../components/leitor-totem";
import { useAuth } from "../../contexts/AuthContext";
import { useFiltrosPostos } from "../../contexts/FiltrosPostosContext";
import { useConsultaConta } from "../../hooks/useConsultaConta";
import type { Abas } from "../../routes/app.routes";
import { api } from "../../services/API";
import { produtosCadastro } from "../../services/cadastroPreco";
import {
  lerCatalogo,
  precoFormatado,
  produto,
} from "../../services/catalogoPostos";
import { design } from "../../theme/design";
import { useCadastroLote } from "./useCadastroLote";

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
  const { token, status, openAuth } = useAuth();

  if (!token || status !== "AUTHENTICATED") {
    return (
      <Page title="Informar preços">
        <Surface>
          <Notice>
            Entre na sua conta para registrar os preços que observou no posto.
          </Notice>

          <AppButton
            label="Entrar para informar preços"
            onPress={() => openAuth("Login")}
          />
        </Surface>
      </Page>
    );
  }

  return (
    <FormularioPreco
      key={JSON.stringify([token, status, route.params?.solicitacao ?? "aba"])}
      parametros={route.params}
      token={token}
    />
  );
}

function FormularioPreco({
  parametros,
  token,
}: {
  parametros: Abas["Adicionar"];
  token: string;
}) {
  const navigation = useNavigation<NavigationProp<Abas>>();
  const { colors } = useAppTheme();
  const { filtros, recarregar } = useFiltrosPostos();
  const desktop = useWindowDimensions().width >= design.desktop;
  const consulta = useConsultaConta(carregarCatalogo);

  const [postoId, selecionarPosto] = useState<number | null>(
    parametros?.postoId ?? null,
  );
  const [seletorAberto, abrirSeletor] = useState(false);

  const posto = consulta.dados?.find((p) => p.id === postoId);

  const form = useCadastroLote(
    posto,
    parametros?.combustivel ?? filtros.referencia,
    token,
    async () => {
      await Promise.all([
        Promise.resolve(recarregar()),
        Promise.resolve(consulta.atualizar()),
      ]);
    },
  );

  const atividade = () =>
    navigation.navigate("Perfil", {
      screen: "AtividadePessoal",
      initial: false,
    });

  const selecionados = form.itens.filter((i) => i.selecionado).length;

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
              Informar preços
            </Text>

            {form.confirmacao ? (
              <Surface>
                <Text
                  accessibilityRole="header"
                  style={{
                    color: colors.success,
                    fontSize: 24,
                    fontWeight: "800",
                  }}
                >
                  Preços registrados
                </Text>

                {form.confirmacao.registros.map((r) => (
                  <Notice key={r.registoId}>
                    {produto(r.codigo).nome}: {precoFormatado(Number(r.preco))}{" "}
                    / {produto(r.codigo).unidade} · Registro #{r.registoId}
                  </Notice>
                ))}

                <Notice>
                  +{form.confirmacao.karmaGanho} Karma confirmado pelo servidor.
                </Notice>

                {posto?.combustiveis.some(
                  (o) =>
                    o.disponivel === null &&
                    form.confirmacao?.registros.some(
                      (r) => r.codigo === o.codigo,
                    ),
                ) ? (
                  <Notice>
                    Produtos com disponibilidade ainda não confirmada aparecem
                    nos detalhes do posto e aguardam confirmação para os
                    filtros.
                  </Notice>
                ) : null}

                <AppButton label="Ver minha atividade" onPress={atividade} />

                <AppButton
                  label="Voltar ao Feed"
                  secondary
                  onPress={() => navigation.navigate("Feed")}
                />

                <AppButton
                  label="Informar outros preços"
                  secondary
                  disabled={form.enviando}
                  onPress={form.novo}
                />
              </Surface>
            ) : (
              <>
                <Notice>
                  Registre um ou vários preços do mesmo posto. Você revisará a
                  seleção antes de confirmar.
                </Notice>

                <View
                  style={{
                    flexDirection: desktop ? "row" : "column",
                    gap: 20,
                    alignItems: "flex-start",
                  }}
                >
                  <View
                    style={{
                      flex: 1,
                      minWidth: 0,
                      width: "100%",
                      gap: 16,
                    }}
                  >
                    <Surface>
                      <Text
                        accessibilityRole="header"
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
                            : "Escolha o posto onde você observou os preços."}
                        </Notice>
                      )}

                      {consulta.erro ? (
                        <>
                          <Notice error>
                            Não foi possível atualizar o catálogo. Atualize
                            antes de confirmar.
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
                          form.bloqueado ||
                          consulta.loading ||
                          !!consulta.erro ||
                          form.checandoGps
                        }
                        onPress={() => abrirSeletor(true)}
                      />
                    </Surface>

                    {posto ? (
                      <>
                        {posto.tipo_posto !== "Eletroposto" ? (
                          <LeitorTotem
                            key={posto.id}
                            postoId={posto.id}
                            bloqueado={form.bloqueado}
                            permitidos={produtosCadastro(posto).map(
                              (i) => i.codigo,
                            )}
                            limparComprovante={form.limparComprovante}
                            usarVarios={form.receberFoto}
                            usar={(codigo, textoPreco, fotoUrl) =>
                              form.receberFoto([
                                {
                                  codigo,
                                  textoPreco,
                                  fotoUrl,
                                },
                              ])
                            }
                          />
                        ) : null}

                        <TextoPrecos form={form} />
                        <SugestoesPrecos form={form} />
                      </>
                    ) : null}
                  </View>

                  <View
                    style={{
                      flex: 1,
                      minWidth: 0,
                      width: "100%",
                      gap: 16,
                    }}
                  >
                    {posto ? <CamposPrecos posto={posto} form={form} /> : null}

                    <Surface>
                      <Notice>
                        Esteja no posto. Uma localização atual será consultada
                        ao confirmar os preços.
                      </Notice>

                      {form.local ? (
                        <Notice>
                          Última leitura: precisão aproximada de ±
                          {Math.round(form.local.precisaoM)} m. A posição será
                          consultada novamente no envio.
                        </Notice>
                      ) : null}

                      <AppButton
                        label="Verificar minha localização"
                        secondary
                        busy={form.checandoGps}
                        disabled={form.bloqueado}
                        onPress={() => void form.verificarGps()}
                      />
                    </Surface>

                    <RevisaoPrecos form={form} />
                  </View>
                </View>
              </>
            )}

            {form.aviso ? <Notice>{form.aviso}</Notice> : null}

            {form.falha ? (
              <Surface>
                <Notice error>{form.falha.message}</Notice>

                {form.falha.tipo === "sessao" ? (
                  <AppButton
                    label="Entrar novamente"
                    onPress={() => navigation.navigate("Perfil")}
                  />
                ) : null}

                {form.incerto ? (
                  <>
                    <AppButton
                      label="Conferir meus preços"
                      onPress={atividade}
                    />

                    <AppButton
                      label="Já conferi, preparar novo registro"
                      secondary
                      onPress={() => {
                        form.novo();
                        consulta.atualizar();
                      }}
                    />
                  </>
                ) : null}
              </Surface>
            ) : null}
          </View>
        </ScrollView>

        {!form.confirmacao && !form.revisao ? (
          <View
            style={{
              padding: 12,
              borderTopWidth: 1,
              borderTopColor: colors.border,
              backgroundColor: colors.surface,
            }}
          >
            <AppButton
              label={
                "Revisar " +
                selecionados +
                (selecionados === 1 ? " preço" : " preços")
              }
              disabled={
                !posto ||
                !selecionados ||
                form.bloqueado ||
                form.checandoGps ||
                consulta.loading ||
                !!consulta.erro
              }
              onPress={form.revisar}
            />
          </View>
        ) : null}
      </KeyboardAvoidingView>

      <SeletorPosto
        aberto={seletorAberto}
        postos={consulta.dados ?? []}
        postoId={postoId}
        carregando={consulta.loading}
        fechar={() => abrirSeletor(false)}
        escolher={(p) => {
          if (form.bloqueado) return;

          form.novo();
          selecionarPosto(p.id);
          abrirSeletor(false);
        }}
      />
    </SafeAreaView>
  );
}
