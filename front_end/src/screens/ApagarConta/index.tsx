import AsyncStorage from "@react-native-async-storage/async-storage";
import { useState } from "react";

import {
    AppButton,
    AppField,
    Notice,
    Page,
    Surface,
} from "../../components/design";

import { CampoSenha, useAcao } from "../../components/form-auth";

import { useAuth } from "../../contexts/AuthContext";
import { api } from "../../services/API";
import { chaveFavoritos } from "../../services/favoritos";
import { limparPostosVistos } from "../../services/historicoVistos";

export default function ApagarConta() {
  const { perfil, signOut } = useAuth();

  const [senha, setSenha] = useState("");
  const [confirmacao, setConfirmacao] = useState("");
  const [excluida, setExcluida] = useState(false);

  const { busy, erro, run } = useAcao(
    "A exclusão não foi confirmada. Confira a conexão e tente acessar sua conta antes de repetir.",
  );

  function apagar() {
    if (confirmacao !== "APAGAR" || !senha || busy || !perfil) {
      return;
    }

    const chave = chaveFavoritos(perfil.email);

    void run(async (signal) => {
      const { data } = await api.delete<{
        conta_excluida: boolean;
      }>("/conta", {
        data: {
          senha,
          confirmacao,
        },
        signal,
      });

      if (data.conta_excluida !== true) {
        throw new Error("Confirmação inválida.");
      }

      if (!signal.aborted) {
        setExcluida(true);
        setSenha("");
        setConfirmacao("");

        try {
          await AsyncStorage.removeItem(chave);

          if (perfil.id) {
            await limparPostosVistos(perfil.id);
          }
        } finally {
          await signOut();
        }
      }
    });
  }

  return (
    <Page
      title="Apagar conta"
      subtitle="Confirme sua identidade para excluir a conta."
    >
      <Surface>
        {excluida ? (
          <>
            <Notice>O servidor confirmou a exclusão da conta.</Notice>

            <AppButton
              label="Voltar à entrada"
              onPress={() => {
                void signOut();
              }}
            />
          </>
        ) : (
          <>
            <Notice error>
              Esta ação remove sua conta, seus preços e seus votos do banco
              ativo. Você perderá o acesso e o saldo de Karma desta conta.
            </Notice>

            <Notice>
              Imagens e cópias de segurança precisam seguir o procedimento de
              privacidade do projeto. A exclusão da conta não comprova, por si
              só, a remoção dessas cópias.
            </Notice>

            {erro ? <Notice error>{erro}</Notice> : null}

            <CampoSenha
              label="Senha atual"
              value={senha}
              onChangeText={setSenha}
              editable={!busy}
              maxLength={1024}
              autoComplete="current-password"
            />

            <AppField
              label="Digite APAGAR para confirmar"
              value={confirmacao}
              onChangeText={setConfirmacao}
              editable={!busy}
              maxLength={6}
              autoCapitalize="characters"
              autoCorrect={false}
            />

            <AppButton
              label="Confirmar exclusão da minha conta"
              busy={busy}
              disabled={confirmacao !== "APAGAR" || !senha}
              onPress={apagar}
            />
          </>
        )}
      </Surface>
    </Page>
  );
}
