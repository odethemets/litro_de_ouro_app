import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { useState } from "react";
import {
  AppButton,
  AuthLayout,
  Notice,
  Surface,
} from "../../components/design";
import { CampoSenha, senhaValida, useAcao } from "../../components/form-auth";
import type { AuthStackParamList } from "../../routes/auth.routes";
import { api } from "../../services/API";

type Props = NativeStackScreenProps<AuthStackParamList, "RedefinirSenha">;

export default function RedefinirSenha({ route, navigation }: Props) {
  const [senha, setSenha] = useState("");
  const [confirmacao, setConfirmacao] = useState("");

  const { busy, erro, setErro, run } = useAcao(
    "Não foi possível confirmar a redefinição. Confira a conexão antes de tentar novamente.",
  );

  const salvar = () => {
    if (busy) return;

    if (!senhaValida(senha)) {
      setErro("A senha deve ter entre 6 e 1024 caracteres.");
      return;
    }

    if (senha !== confirmacao) {
      setErro("As senhas não coincidem.");
      return;
    }

    void run(async (signal) => {
      await api.post(
        "/auth/redefinir-senha",
        {
          email: route.params.email,
          codigo: route.params.codigo,
          nova_senha: senha,
        },
        { signal },
      );

      if (!signal.aborted) {
        navigation.reset({
          index: 0,
          routes: [
            {
              name: "Login",
              params: {
                message: "Senha redefinida. Entre com sua nova senha.",
              },
            },
          ],
        });
      }
    });
  };

  return (
    <AuthLayout
      title="Crie uma nova senha"
      subtitle="Escolha uma senha e confirme abaixo."
    >
      <Surface>
        {erro ? <Notice error>{erro}</Notice> : null}

        <CampoSenha
          label="Nova senha"
          value={senha}
          onChangeText={setSenha}
          editable={!busy}
          autoComplete="new-password"
        />

        <CampoSenha
          label="Confirmar nova senha"
          value={confirmacao}
          onChangeText={setConfirmacao}
          editable={!busy}
          autoComplete="new-password"
          onSubmitEditing={salvar}
        />

        <AppButton label="Salvar nova senha" busy={busy} onPress={salvar} />

        <Notice>Após salvar, entre com sua nova senha.</Notice>
      </Surface>

      <AppButton
        label="Voltar ao código"
        secondary
        disabled={busy}
        onPress={() => navigation.goBack()}
      />

      <AppButton
        label="Voltar ao Login"
        secondary
        disabled={busy}
        onPress={() =>
          navigation.reset({
            index: 0,
            routes: [{ name: "Login" }],
          })
        }
      />
    </AuthLayout>
  );
}
