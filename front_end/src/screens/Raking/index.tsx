import { Text } from "react-native";
import { Notice, Surface, useAppTheme } from "../../components/design";
import { ListaConta } from "../../components/lista-conta";
import { useConsultaConta } from "../../hooks/useConsultaConta";
import {
    carregarRanking,
    type ParticipanteRanking,
} from "../../services/karma";

export default function Ranking() {
  const { colors } = useAppTheme();
  const consulta = useConsultaConta(carregarRanking);

  return (
    <ListaConta<ParticipanteRanking>
      titulo="Ranking"
      subtitulo="Contribuições da comunidade, ordenadas por Karma."
      itens={consulta.dados}
      carregando={consulta.loading}
      erro={consulta.erro}
      atualizar={consulta.atualizar}
      atualizarLabel="Atualizar ranking"
      vazio="Nenhum participante disponível no ranking."
      rodape="Até 50 participantes com e-mail confirmado. Em caso de empate, vale a ordem de cadastro."
      keyExtractor={(_, indice) => String(indice)}
      renderItem={({ item, index }) => (
        <Surface>
          <Notice>{index + 1}º lugar</Notice>

          <Text
            style={{
              color: colors.textPrimary,
              fontSize: 20,
              fontWeight: "700",
            }}
          >
            {item.nome}
          </Text>

          <Text
            style={{
              color: colors.textPrimary,
              fontSize: 28,
              fontWeight: "800",
            }}
          >
            {item.karma.toLocaleString("pt-BR")}
          </Text>

          <Notice>pontos de Karma</Notice>
        </Surface>
      )}
    />
  );
}
