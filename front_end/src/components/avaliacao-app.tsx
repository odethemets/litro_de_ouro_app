import { Text, View } from "react-native";

import {
  abrirFormularioAvaliacao,
  FORMULARIO_AVALIACAO_URL,
} from "../services/avaliacaoApp";
import { AppButton, Notice, Surface, useAppTheme } from "./design";
import { useAcao } from "./form-auth";

export function AvaliacaoApp({ compacto = false }: { compacto?: boolean }) {
  const { colors } = useAppTheme();

  const { busy, erro, run } = useAcao(
    "Não foi possível abrir o formulário. Tente novamente.",
  );

  if (!FORMULARIO_AVALIACAO_URL) return null;

  const conteudo = (
    <>
      {!compacto ? (
        <>
          <Text
            accessibilityRole="header"
            style={{
              color: colors.textPrimary,
              fontSize: 20,
              fontWeight: "700",
            }}
          >
            Ajude a melhorar o Litro de Ouro
          </Text>

          <Notice>
            Conte como foi usar o aplicativo. A participação é voluntária; o
            formulário abre no Google Forms.
          </Notice>
        </>
      ) : null}

      <AppButton
        label="Avaliar o aplicativo no Google Forms"
        accessibilityLabel="Abrir formulário de avaliação no Google Forms"
        icon="open-outline"
        secondary
        busy={busy}
        onPress={() => void run(abrirFormularioAvaliacao)}
      />

      {erro ? <Notice error>{erro}</Notice> : null}
    </>
  );

  return compacto ? (
    <View style={{ gap: 8 }}>{conteudo}</View>
  ) : (
    <Surface>{conteudo}</Surface>
  );
}
