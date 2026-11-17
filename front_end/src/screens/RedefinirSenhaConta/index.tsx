import { useState } from "react";
import {
    AppButton,
    AppField,
    Notice,
    Page,
    Surface,
} from "../../components/design";
import { CampoSenha, senhaValida, useAcao } from "../../components/form-auth";
import { useAuth } from "../../contexts/AuthContext";
import { api } from "../../services/API";

export default function RedefinirSenhaConta() {
  const { perfil, signOut } = useAuth();
  const email = perfil?.email ?? "";

  const [etapa, setEtapa] = useState<"inicio" | "codigo" | "senha" | "feito">(
    "inicio",
  );

  const [codigo, setCodigo] = useState("");
  const [senha, setSenha] = useState("");
  const [confirmacao, setConfirmacao] = useState("");
  const [mensagem, setMensagem] = useState("");

  const { busy, erro, setErro, run } = useAcao(
    "Não foi possível confirmar a solicitação. Confira a conexão e tente novamente.",
  );

  const solicitar = () => {
    if (!email || busy) return;

    void run(async (signal) => {
      const { data } = await api.post<{ message?: string }>(
        "/auth/recuperar-senha",
        { email },
        { signal },
      );

      if (!signal.aborted) {
        setCodigo("");
        setSenha("");
        setConfirmacao("");
        setEtapa("codigo");

        setMensagem(
          data.message ?? "Solicitação recebida. Confira o e-mail e o spam.",
        );
      }
    });
  };

  const salvar = () => {
    if (busy) return;

    if (!/^[0-9]{6}$/.test(codigo)) {
      setErro("Informe o código de 6 dígitos.");
      return;
    }

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
          email,
          codigo,
          nova_senha: senha,
        },
        { signal },
      );

      if (!signal.aborted) {
        setSenha("");
        setConfirmacao("");
        setCodigo("");
        setEtapa("feito");
      }
    });
  };

  return (
    <Page
      title="Redefinir senha"
      subtitle="Confirme sua identidade por e-mail."
    >
      <Surface>
        {!email ? (
          <Notice error>Não foi possível identificar sua conta.</Notice>
        ) : etapa === "feito" ? (
          <>
            <Notice>
              Senha redefinida. Encerre esta sessão para entrar novamente com a
              nova senha.
            </Notice>

            <AppButton
              label="Encerrar sessão"
              onPress={() => {
                void signOut();
              }}
            />
          </>
        ) : (
          <>
            <Notice>{email}</Notice>

            {mensagem ? <Notice>{mensagem}</Notice> : null}
            {erro ? <Notice error>{erro}</Notice> : null}

            {etapa === "inicio" ? (
              <AppButton
                label="Solicitar código por e-mail"
                busy={busy}
                onPress={solicitar}
              />
            ) : etapa === "codigo" ? (
              <>
                <AppField
                  label="Código de recuperação"
                  placeholder="000000"
                  value={codigo}
                  maxLength={6}
                  keyboardType="number-pad"
                  autoComplete="one-time-code"
                  editable={!busy}
                  onChangeText={(value) =>
                    setCodigo(value.replace(/[^0-9]/g, "").slice(0, 6))
                  }
                />

                <Notice>O código será validado ao salvar a nova senha.</Notice>

                <AppButton
                  label="Continuar"
                  disabled={busy || !/^[0-9]{6}$/.test(codigo)}
                  onPress={() => {
                    setErro("");
                    setEtapa("senha");
                  }}
                />

                <AppButton
                  label="Solicitar outro código"
                  secondary
                  disabled={busy}
                  onPress={solicitar}
                />
              </>
            ) : (
              <>
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
                />

                <AppButton
                  label="Salvar nova senha"
                  busy={busy}
                  onPress={salvar}
                />

                <AppButton
                  label="Voltar ao código"
                  secondary
                  disabled={busy}
                  onPress={() => {
                    setErro("");
                    setEtapa("codigo");
                  }}
                />
              </>
            )}
          </>
        )}
      </Surface>
    </Page>
  );
}
