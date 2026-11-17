import Ionicons from "@expo/vector-icons/Ionicons";
import { useCallback, useState } from "react";
import { ActivityIndicator, Pressable, Text, View } from "react-native";
import {
  AppButton,
  Notice,
  Page,
  Surface,
  useAppTheme,
} from "../../components/design";
import { useAuth } from "../../contexts/AuthContext";
import { useConsultaConta } from "../../hooks/useConsultaConta";
import { api } from "../../services/API";
import {
  formatarPreco,
  produtoHistorico,
  validarRegistos,
} from "../../services/atividadeConta";
import { obterPostosVistos } from "../../services/historicoVistos";

import { useNavigation, type NavigationProp } from "@react-navigation/native";

import type { ContaPilha } from "../../routes/app.routes";

const carregarRegistos = async (signal: AbortSignal) =>
  validarRegistos((await api.get("/atividade/meus-registos", { signal })).data);

export default function Atividade() {
  const navigation = useNavigation<NavigationProp<ContaPilha>>();
  const { perfil } = useAuth();
  const carregarVistos = useCallback(
    () => obterPostosVistos(perfil?.id),
    [perfil?.id],
  );
  const { colors } = useAppTheme();
  const [aba, setAba] = useState<"registos" | "vistos">("registos");
  const [foco, setFoco] = useState("");

  const registos = useConsultaConta(carregarRegistos, aba === "registos");

  const vistos = useConsultaConta(carregarVistos, aba === "vistos");

  const consulta = aba === "registos" ? registos : vistos;
  const quantidade = consulta.dados?.length;

  return (
    <Page
      title="Seu histórico"
      subtitle="Acompanhe sua participação e os postos consultados."
    >
      <AppButton
        label="Ver Histórico de Karma"
        secondary
        onPress={() => navigation.navigate("HistoricoKarma")}
      />
      <Surface>
        <View
          style={{
            flexDirection: "row",
            gap: 16,
            alignItems: "center",
          }}
        >
          <Ionicons
            name={aba === "registos" ? "receipt-outline" : "time-outline"}
            size={32}
            color={colors.textPrimary}
            accessible={false}
          />

          <View style={{ flex: 1, gap: 4 }}>
            <Text
              accessibilityRole="header"
              style={{
                fontSize: 32,
                fontWeight: "800",
                color: colors.textPrimary,
              }}
            >
              {quantidade === undefined ? "—" : quantidade}
            </Text>

            <Notice>
              {aba === "registos"
                ? "registros carregados"
                : "postos consultados neste dispositivo"}
            </Notice>
          </View>
        </View>

        <Notice>
          {aba === "registos"
            ? "Exibindo até os 50 registros mais recentes, do mais novo ao mais antigo."
            : "Histórico desta conta neste dispositivo. Até 20 postos recentemente consultados."}
        </Notice>
      </Surface>

      <View
        accessibilityRole="tablist"
        style={{
          flexDirection: "row",
          flexWrap: "wrap",
          gap: 8,
        }}
      >
        {(
          [
            ["registos", "Meus preços"],
            ["vistos", "Vistos recentemente"],
          ] as const
        ).map(([id, label]) => (
          <Pressable
            key={id}
            accessibilityRole="tab"
            accessibilityLabel={label}
            accessibilityState={{ selected: aba === id }}
            aria-selected={aba === id}
            onFocus={() => setFoco(id)}
            onBlur={() => setFoco("")}
            onPress={() => setAba(id)}
            style={{
              flexGrow: 1,
              minHeight: 52,
              padding: 14,
              borderRadius: 16,
              borderWidth: 2,
              borderColor: foco === id ? colors.focus : colors.border,
              backgroundColor: aba === id ? colors.selection : colors.surface,
            }}
          >
            <Text
              style={{
                textAlign: "center",
                fontSize: 16,
                fontWeight: "700",
                color: colors.textPrimary,
              }}
            >
              {label}
            </Text>
          </Pressable>
        ))}
      </View>

      <AppButton
        label="Atualizar histórico"
        secondary
        disabled={consulta.loading}
        onPress={consulta.atualizar}
      />

      {consulta.loading ? (
        <View
          accessibilityRole="progressbar"
          accessibilityLabel="Carregando histórico"
          style={{
            flexDirection: "row",
            gap: 12,
            alignItems: "center",
          }}
        >
          <ActivityIndicator color={colors.textSecondary} />
          <Notice>Carregando histórico...</Notice>
        </View>
      ) : null}

      {consulta.erro ? (
        <Surface>
          <Notice error>
            {consulta.dados
              ? "Não foi possível atualizar o histórico. Exibindo os últimos dados recebidos."
              : "Não foi possível carregar o histórico. Tente novamente."}
          </Notice>

          <AppButton
            label="Tentar novamente"
            disabled={consulta.loading}
            onPress={consulta.atualizar}
          />
        </Surface>
      ) : null}

      {!consulta.loading && !consulta.erro && quantidade === 0 ? (
        <Surface>
          <Ionicons
            name={aba === "registos" ? "receipt-outline" : "map-outline"}
            size={40}
            color={colors.textSecondary}
            accessible={false}
          />

          <Text
            style={{
              fontSize: 20,
              fontWeight: "700",
              color: colors.textPrimary,
            }}
          >
            {aba === "registos"
              ? "Você ainda não registrou preços"
              : "Nenhum posto consultado recentemente"}
          </Text>

          <Notice>
            {aba === "registos"
              ? "Seus registros aparecerão aqui após a confirmação do envio."
              : "Os postos que você abrir serão listados aqui."}
          </Notice>
        </Surface>
      ) : null}

      {aba === "registos"
        ? registos.dados?.map((r) => {
            const produto = produtoHistorico(r.tipo_combustivel);

            return (
              <Surface key={r.id}>
                <View
                  style={{
                    flexDirection: "row",
                    alignItems: "center",
                    gap: 12,
                  }}
                >
                  <Ionicons
                    name={
                      produto?.unidade === "kWh"
                        ? "flash-outline"
                        : "receipt-outline"
                    }
                    size={28}
                    color={colors.textPrimary}
                    accessible={false}
                  />

                  <View
                    style={{
                      flex: 1,
                      minWidth: 0,
                      gap: 4,
                    }}
                  >
                    <Text
                      style={{
                        color: colors.textPrimary,
                        fontSize: 20,
                        fontWeight: "700",
                      }}
                    >
                      {r.posto_nome}
                    </Text>

                    <Text
                      style={{
                        color: colors.textSecondary,
                        fontSize: 14,
                      }}
                    >
                      {r.posto_endereco || "Endereço não informado"}
                    </Text>
                  </View>
                </View>

                <View
                  style={{
                    flexDirection: "row",
                    alignItems: "center",
                    gap: 8,
                  }}
                >
                  {produto ? (
                    <View
                      style={{
                        width: 12,
                        height: 12,
                        borderRadius: 6,
                        backgroundColor: produto.cor,
                      }}
                    />
                  ) : null}

                  <Text
                    style={{
                      color: colors.textPrimary,
                      fontSize: 16,
                      flexShrink: 1,
                    }}
                  >
                    {produto?.nome ?? r.tipo_combustivel}
                  </Text>
                </View>

                <View
                  style={{
                    borderTopWidth: 1,
                    borderColor: colors.border,
                    paddingTop: 16,
                    gap: 8,
                  }}
                >
                  <Text
                    style={{
                      color: colors.textPrimary,
                      fontSize: 32,
                      fontWeight: "800",
                    }}
                  >
                    R$ {formatarPreco(r.preco)}
                    {produto ? "/" + produto.unidade : ""}
                  </Text>

                  <Notice>Registrado em {r.data_formatada}</Notice>
                </View>
              </Surface>
            );
          })
        : vistos.dados?.map((p) => (
            <Surface key={p.id}>
              <Text
                style={{
                  color: colors.textPrimary,
                  fontSize: 20,
                  fontWeight: "700",
                }}
              >
                {p.nome}
              </Text>

              <Notice>{p.endereco || "Endereço não informado"}</Notice>

              <Notice>
                Consultado em{" "}
                {new Date(p.dataVisualizacao).toLocaleString("pt-BR", {
                  timeZone: "America/Fortaleza",
                })}
              </Notice>
            </Surface>
          ))}
    </Page>
  );
}
