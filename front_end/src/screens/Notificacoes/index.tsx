import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { Text } from "react-native";
import {
  AppButton,
  Notice,
  Page,
  Surface,
  useAppTheme,
} from "../../components/design";
import { useAcao } from "../../components/form-auth";
import { useConsultaConta } from "../../hooks/useConsultaConta";
import type { ContaPilha } from "../../routes/app.routes";
import * as alertas from "../../services/alertas";
import { precoFormatado, produto } from "../../services/catalogoPostos";
import { dataEvento } from "../../services/participacao";

type Props = NativeStackScreenProps<ContaPilha, "Notificacoes">;

export default function Notificacoes({ navigation }: Props) {
  const { colors } = useAppTheme();
  const consulta = useConsultaConta(alertas.carregarAvisos);

  const { busy, erro, setErro, run } = useAcao(
    "Não foi possível confirmar a leitura. Atualize a central.",
  );

  async function marcarAvisoComoLido(id: number, signal: AbortSignal) {
    const fn =
      (alertas as any).marcarAvisoLido ??
      (alertas as any).marcarAvisoComoLido ??
      (alertas as any).marcarAlertaLido ??
      (alertas as any).marcarAlertaComoLido ??
      (alertas as any).marcarComoLido;

    if (typeof fn !== "function") {
      throw new Error(
        "Função para marcar aviso como lido não está disponível.",
      );
    }

    return fn(id, signal);
  }

  function atualizar() {
    setErro("");
    consulta.atualizar();
  }

  function ler(id: number) {
    void run(async (signal) => {
      await marcarAvisoComoLido(id, signal);

      if (!signal.aborted) consulta.atualizar();
    });
  }

  return (
    <Page
      title="Notificações"
      subtitle={
        consulta.dados
          ? consulta.dados.nao_lidas + " avisos não lidos"
          : "Acompanhe os preços dos seus favoritos."
      }
    >
      <AppButton
        label="Preferências de alertas"
        secondary
        onPress={() => navigation.navigate("PreferenciasAlertas")}
      />

      <AppButton
        label="Atualizar notificações"
        secondary
        disabled={consulta.loading || busy}
        onPress={atualizar}
      />

      {erro ? <Notice error>{erro}</Notice> : null}

      {consulta.erro ? (
        <Notice error>
          Não foi possível atualizar a central. Tente novamente.
        </Notice>
      ) : null}

      {consulta.loading ? <Notice>Atualizando avisos...</Notice> : null}

      {!consulta.loading &&
      !consulta.erro &&
      consulta.dados?.itens.length === 0 ? (
        <Notice>
          Você ainda não recebeu avisos. Favorite um posto, escolha os
          combustíveis e ative os alertas nas preferências.
        </Notice>
      ) : null}

      {consulta.dados?.itens.map((item) => {
        const combustivel = produto(item.combustivel_codigo);

        return (
          <Surface key={item.id}>
            <Notice>{item.lida ? "Lida" : "Nova"}</Notice>

            <Text
              style={{
                color: colors.textPrimary,
                fontSize: 18,
                fontWeight: "700",
              }}
            >
              {item.posto_nome}
            </Text>

            <Notice>{combustivel.nome}</Notice>

            <Text
              style={{
                color: colors.textPrimary,
                fontSize: 24,
                fontWeight: "800",
              }}
            >
              {precoFormatado(item.preco_novo)} / {combustivel.unidade}
            </Text>

            {item.preco_anterior !== null ? (
              <Notice>
                Preço anterior: {precoFormatado(item.preco_anterior)} /{" "}
                {combustivel.unidade}
              </Notice>
            ) : (
              <Notice>Primeiro preço informado.</Notice>
            )}

            <Notice>{dataEvento(item.criado_em)}</Notice>

            {!item.lida ? (
              <AppButton
                label={"Marcar aviso de " + item.posto_nome + " como lido"}
                secondary
                disabled={busy || consulta.loading || consulta.erro}
                onPress={() => ler(item.id)}
              />
            ) : null}
          </Surface>
        );
      })}

      <Notice>Até 100 avisos recentes, disponíveis nesta central.</Notice>
    </Page>
  );
}
