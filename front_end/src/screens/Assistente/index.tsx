import { useNavigation, type NavigationProp } from "@react-navigation/native";

import { FormularioBuscaAssistida } from "../../components/busca-assistida";
import { AppButton, Notice, Page, Surface } from "../../components/design";
import { useAuth } from "../../contexts/AuthContext";
import type { Abas } from "../../routes/app.routes";

export default function Assistente() {
  const { token, status, openAuth } = useAuth();
  const navigation = useNavigation<NavigationProp<Abas>>();
  const autenticado = !!token && status === "AUTHENTICATED";

  return (
    <Page
      title="Assistente Ouro"
      subtitle="Diga ou escreva o combustível e a bandeira que procura."
    >
      {autenticado && token ? (
        <FormularioBuscaAssistida
          key={JSON.stringify([token, status])}
          token={token}
          aoAplicar={() => navigation.navigate("Mapa")}
        />
      ) : (
        <Surface>
          <Notice>Entre na sua conta para buscar por texto ou voz.</Notice>
          <AppButton
            label="Entrar para usar o assistente"
            onPress={() => openAuth("Login")}
          />
        </Surface>
      )}
    </Page>
  );
}
