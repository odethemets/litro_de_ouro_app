import { useEffect, useRef, useState } from "react";
import { Text, View } from "react-native";

import { useAuth } from "../contexts/AuthContext";
import { api } from "../services/API";
import { lerAvaliacao, type AvaliacaoPreco, type Voto } from "../services/votos";
import { AppButton, Notice, useAppTheme } from "./design";

interface Props {
  registoId: number;
  nome: string;
}

// Vincula o estado à sessão e ao registro exato, sem depender da chave do pai.
export function VotarPreco(props: Props) {
  const { token, status } = useAuth();
  return <ControlesVoto key={JSON.stringify([token, status, props.registoId])} {...props} />;
}

// Carrega sob demanda e exige nova consulta quando uma gravação fica incerta.
function ControlesVoto({ registoId, nome }: Props) {
  const { token, status, openAuth } = useAuth();
  const { colors } = useAppTheme();
  const [avaliacao, setAvaliacao] = useState<AvaliacaoPreco | null>(null);
  const [acao, setAcao] = useState<"consulta" | Voto | null>(null);
  const [erro, setErro] = useState("");
  const [mensagem, setMensagem] = useState("");
  const pedido = useRef<AbortController | null>(null);

  useEffect(() => () => pedido.current?.abort(), []);

  // Aplica somente a resposta do registro atual; abortar não desfaz escrita no servidor.
  async function consultar(voto?: Voto) {
    if (!token || status !== "AUTHENTICATED" || pedido.current) return;
    if (voto && (!avaliacao?.pode_votar || avaliacao.meu_voto === voto)) return;
    const controller = new AbortController();
    pedido.current = controller;
    setAcao(voto ?? "consulta");
    setErro("");
    setMensagem("");

    try {
      const config = {
        headers: { Authorization: "Bearer " + token },
        signal: controller.signal,
      };
      const resposta = voto
        ? await api.post(`/precos/${registoId}/votar`, { voto }, config)
        : await api.get(`/precos/${registoId}/votos`, config);
      if (controller.signal.aborted) return;
      setAvaliacao(lerAvaliacao(resposta.data, registoId));
      if (voto) setMensagem("Seu voto foi registrado para este preço.");
    } catch {
      if (controller.signal.aborted) return;
      setAvaliacao(null);
      setErro(voto
        ? "A confirmação do voto não chegou. Consulte as avaliações antes de votar novamente."
        : "Não foi possível consultar as avaliações. Tente novamente.");
    } finally {
      if (pedido.current === controller) pedido.current = null;
      if (!controller.signal.aborted) setAcao(null);
    }
  }

  const busy = acao !== null;
  return (
    <View style={{ gap: 10 }}>
      <AppButton
        label={status !== "AUTHENTICATED" ? "Entrar para avaliar preço"
          : avaliacao ? "Atualizar avaliações" : "Consultar avaliações"}
        secondary
        busy={acao === "consulta"}
        disabled={busy}
        onPress={() => status === "AUTHENTICATED" ? void consultar() : openAuth("Login")}
      />

      {avaliacao ? (
        <>
          <Text style={{ color: colors.textSecondary, lineHeight: 22 }}>
            {avaliacao.positivos} confirmações · {avaliacao.negativos} contestações
          </Text>
          <Notice>
            Pontuação: {avaliacao.confianca_score}. Começa em 1 e não representa um selo de validação.
          </Notice>
          {avaliacao.pode_votar ? (
            <>
              <Notice>O valor de {nome} confere com o que você encontrou?</Notice>
              <AppButton
                label="Preço confere"
                secondary
                busy={acao === "positivo"}
                disabled={busy || avaliacao.meu_voto === "positivo"}
                selected={avaliacao.meu_voto === "positivo"}
                onPress={() => void consultar("positivo")}
              />
              <AppButton
                label="Preço está diferente"
                secondary
                busy={acao === "negativo"}
                disabled={busy || avaliacao.meu_voto === "negativo"}
                selected={avaliacao.meu_voto === "negativo"}
                onPress={() => void consultar("negativo")}
              />
              {avaliacao.meu_voto ? (
                <Notice>{avaliacao.meu_voto === "positivo"
                  ? "Seu voto atual confirma este preço."
                  : "Seu voto atual contesta este preço."} Você pode trocar o voto.</Notice>
              ) : null}
            </>
          ) : <Notice>Você é o autor deste preço e não pode votar nele.</Notice>}
        </>
      ) : null}

      {mensagem ? <View accessibilityLiveRegion="polite"><Notice>{mensagem}</Notice></View> : null}
      {erro ? <Notice error>{erro}</Notice> : null}
    </View>
  );
}
