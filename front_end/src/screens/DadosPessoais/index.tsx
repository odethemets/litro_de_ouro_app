import { useState } from "react";

import {
    AppButton,
    AppField,
    Notice,
    Page,
    Surface,
} from "../../components/design";

import { CampoSenha, emailValido, useAcao } from "../../components/form-auth";

import { useAuth } from "../../contexts/AuthContext";
import { api } from "../../services/API";

export default function DadosPessoais() {
  const { perfil, userToken, signIn, signOut } = useAuth();

  const [nome, setNome] = useState(perfil?.nome ?? "");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [codigo, setCodigo] = useState("");
  const [aguardandoCodigo, setAguardandoCodigo] = useState(false);
  const [mensagem, setMensagem] = useState("");

  const { busy, erro, setErro, run } = useAcao(
    "Não foi possível confirmar a alteração. Atualize os dados antes de repetir.",
  );

  function salvarNome() {
    if (!nome.trim() || Array.from(nome.trim()).length > 100) {
      setErro("Informe um nome com até 100 caracteres.");
      return;
    }

    void run(async (signal) => {
      await api.patch("/conta/nome", { nome: nome.trim() }, { signal });

      if (!signal.aborted && userToken) {
        setMensagem("Nome salvo. Atualizando o perfil...");
        await signIn(userToken);

        if (!signal.aborted) {
          setMensagem("Nome atualizado.");
        }
      }
    });
  }

  function solicitarCodigo() {
    const novoEmail = email.trim().toLowerCase();

    if (!emailValido(novoEmail) || !senha) {
      setErro("Informe o novo e-mail e sua senha atual.");
      return;
    }

    void run(async (signal) => {
      const { data } = await api.post<{ message: string }>(
        "/conta/email/solicitar",
        {
          novo_email: novoEmail,
          senha,
        },
        { signal },
      );

      if (!signal.aborted) {
        setSenha("");
        setCodigo("");
        setEmail(novoEmail);
        setAguardandoCodigo(true);
        setMensagem(data.message);
      }
    });
  }

  function confirmarEmail() {
    if (!/^[0-9]{6}$/.test(codigo)) {
      setErro("Informe os seis dígitos do código.");
      return;
    }

    void run(async (signal) => {
      const { data } = await api.post<{
        sessao_encerrada: boolean;
      }>("/conta/email/confirmar", { codigo }, { signal });

      if (data.sessao_encerrada !== true) {
        throw new Error("Confirmação inválida.");
      }

      if (!signal.aborted) {
        setCodigo("");
        await signOut();
      }
    });
  }

  return (
    <Page
      title="Dados pessoais"
      subtitle="Seu nome público e seu e-mail de acesso."
    >
      {erro ? <Notice error>{erro}</Notice> : null}
      {mensagem ? <Notice>{mensagem}</Notice> : null}

      <Surface>
        <AppField
          label="Nome público"
          value={nome}
          onChangeText={setNome}
          maxLength={100}
          editable={!busy}
          autoComplete="name"
        />

        <Notice>
          Este nome aparece nas contribuições públicas de preços e no ranking.
        </Notice>

        <AppButton label="Salvar nome" busy={busy} onPress={salvarNome} />
      </Surface>

      <Surface>
        <Notice>E-mail atual: {perfil?.email ?? "Indisponível"}</Notice>

        <Notice>
          O endereço atual continua válido até a confirmação. Ao concluir, suas
          sessões serão encerradas e você entrará com o novo e-mail.
        </Notice>

        <AppField
          label="Novo e-mail"
          value={email}
          onChangeText={setEmail}
          editable={!busy && !aguardandoCodigo}
          maxLength={100}
          keyboardType="email-address"
          autoCapitalize="none"
          autoCorrect={false}
        />

        {aguardandoCodigo ? (
          <>
            <AppField
              label="Código recebido no novo e-mail"
              value={codigo}
              onChangeText={(valor) =>
                setCodigo(valor.replace(/[^0-9]/g, "").slice(0, 6))
              }
              maxLength={6}
              editable={!busy}
              keyboardType="number-pad"
              autoComplete="one-time-code"
            />

            <AppButton
              label="Confirmar e-mail e encerrar sessões"
              busy={busy}
              onPress={confirmarEmail}
            />

            <AppButton
              label="Solicitar outro código ou trocar endereço"
              secondary
              disabled={busy}
              onPress={() => {
                setAguardandoCodigo(false);
                setCodigo("");
                setMensagem("");
                setErro("");
              }}
            />
          </>
        ) : (
          <>
            <CampoSenha
              label="Senha atual"
              value={senha}
              onChangeText={setSenha}
              editable={!busy}
              maxLength={1024}
              autoComplete="current-password"
            />

            <AppButton
              label="Enviar código ao novo e-mail"
              busy={busy}
              onPress={solicitarCodigo}
            />
          </>
        )}
      </Surface>
    </Page>
  );
}
