import { Text } from "react-native";
import { Notice, Surface, useAppTheme } from "../../components/design";
import { ListaConta } from "../../components/lista-conta";
import { useConsultaConta } from "../../hooks/useConsultaConta";
import { carregarKarma, pontosFormatados } from "../../services/karma";
import { dataEvento, type EventoKarma } from "../../services/participacao";

export default function HistoricoKarma() {
  const { colors } = useAppTheme();
  const consulta = useConsultaConta(carregarKarma);

  return (
    <ListaConta<EventoKarma>
      titulo="Histórico de Karma"
      subtitulo="Acompanhe os pontos registrados na sua conta."
      itens={consulta.dados?.itens ?? null}
      carregando={consulta.loading}
      erro={consulta.erro}
      atualizar={consulta.atualizar}
      atualizarLabel="Atualizar Karma"
      vazio="Nenhum evento de Karma registrado para esta conta."
      rodape="Até 100 eventos recentes. O saldo anterior reúne os pontos que já existiam quando o histórico foi ativado."
      keyExtractor={(item) => String(item.id)}
      renderItem={({ item }) => (
        <Surface>
          <Text
            style={{
              color: colors.textPrimary,
              fontSize: 18,
              fontWeight: "700",
            }}
          >
            {item.motivo}
          </Text>

          <Text
            style={{
              fontSize: 28,
              fontWeight: "800",
              color: item.pontos < 0 ? colors.danger : colors.textPrimary,
            }}
          >
            {pontosFormatados(item.pontos)} pontos
          </Text>

          <Notice>
            Saldo após o evento: {item.saldo_apos.toLocaleString("pt-BR")}
          </Notice>

          <Notice>{dataEvento(item.criado_em)}</Notice>

          {item.registo_id !== null ? (
            <Notice>Registro de preço #{item.registo_id}</Notice>
          ) : null}
        </Surface>
      )}
    >
      {consulta.dados ? (
        <Surface>
          <Notice>Saldo atual</Notice>

          <Text
            style={{
              color: colors.textPrimary,
              fontSize: 36,
              fontWeight: "800",
            }}
          >
            {consulta.dados.saldo.toLocaleString("pt-BR")}
          </Text>

          <Notice>pontos de Karma</Notice>
        </Surface>
      ) : null}
    </ListaConta>
  );
}
