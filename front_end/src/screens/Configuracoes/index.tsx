import type { NativeStackScreenProps } from "@react-navigation/native-stack";

import { AvaliacaoApp } from "../../components/avaliacao-app";
import { AppButton, Notice, Page, Surface } from "../../components/design";
import type { ContaPilha } from "../../routes/app.routes";

type Props = NativeStackScreenProps<ContaPilha, "Definicoes">;

export default function Configuracoes({ navigation }: Props) {
  return (
    <Page title="Configurações" subtitle="Conta, aparência e preferências.">
      <Surface>
        <Notice>Dados pessoais</Notice>

        <AppButton
          label="Alterar nome ou e-mail"
          secondary
          onPress={() => navigation.navigate("DadosPessoais")}
        />
      </Surface>

      <Surface>
        <Notice>Senha e acesso</Notice>

        <AppButton
          label="Redefinir senha"
          secondary
          onPress={() => navigation.navigate("RedefinirSenhaConta")}
        />

        <Notice>
          Confirme sua identidade com o código enviado por e-mail.
        </Notice>
      </Surface>

      <Surface>
        <Notice>Postos acompanhados</Notice>

        <AppButton
          label="Favoritos"
          secondary
          onPress={() => navigation.navigate("Favoritos")}
        />

        <Notice>Escolha os postos para salvar neste dispositivo.</Notice>
      </Surface>

      <Surface>
        <Notice>Aparência</Notice>

        <AppButton
          label="Claro, escuro ou seguir o sistema"
          secondary
          onPress={() => navigation.navigate("Aparencia")}
        />
      </Surface>

      <Surface>
        <Notice>Exclusão da conta</Notice>

        <AppButton
          label="Apagar minha conta"
          secondary
          onPress={() => navigation.navigate("ApagarConta")}
        />
      </Surface>

      <Surface>
        <Notice>Avisos de preços</Notice>

        <AppButton
          label="Preferências de alertas"
          secondary
          onPress={() => navigation.navigate("PreferenciasAlertas")}
        />
        <Notice>Seus postos ficam salvos na sua conta.</Notice>
      </Surface>
      <AvaliacaoApp />
    </Page>
  );
}
