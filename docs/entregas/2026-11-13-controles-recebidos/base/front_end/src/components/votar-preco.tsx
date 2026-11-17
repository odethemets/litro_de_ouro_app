import { useEffect, useRef, useState } from "react";
import { Text, View } from "react-native";

import { useAuth } from "../contexts/AuthContext";
import { api } from "../services/API";
import { lerAvaliacao, type AvaliacaoPreco, type Voto } from "../services/votos";
import { AppButton, Notice, useAppTheme } from "./design";

// Isola o estado por sessão; o componente pai fornece a chave do registro de preço.
export function VotarPreco({ registoId, nome }: { registoId: number; nome: string }) {
  const { token } = useAuth();
  return <ControlesVoto key={token ?? "visitante"} registoId={registoId} nome={nome} />;
}

// Mostra avaliações sob demanda e ações permitidas para a conta atual.
function ControlesVoto({ registoId, nome }: { registoId: number; nome: string }) {
  const { token, status, openAuth } = useAuth();
  const { colors } = useAppTheme();
  const [avaliacao, setAvaliacao] = useState<AvaliacaoPreco | null>(null);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState("");
  const atual = useRef(token);
  const ocupado = useRef(false);
  useEffect(() => {
    atual.current = token;
    return () => { atual.current = null; };
  }, [token]);

  // Sem argumento consulta; com voto grava e reconcilia a resposta do registro exato.
  async function consultar(voto?: Voto) {
    if (!token || ocupado.current) return;
    const sessao = token;
    ocupado.current = true;
    setBusy(true);
    setErro("");
    try {
      const config = { headers: { Authorization: "Bearer " + sessao } };
      const r = voto
        ? await api.post(`/precos/${registoId}/votar`, { voto }, config)
        : await api.get(`/precos/${registoId}/votos`, config);
      if (atual.current === sessao) setAvaliacao(lerAvaliacao(r.data, registoId));
    } catch {
      if (atual.current === sessao) {
        setAvaliacao(null);
        setErro("Não recebemos a confirmação. Consulte as avaliações antes de repetir o voto.");
      }
    } finally {
      ocupado.current = false;
      if (atual.current === sessao) setBusy(false);
    }
  }

  return <View style={{ gap: 8 }}>
    <AppButton label={status === "AUTHENTICATED" ? "Consultar avaliações de " + nome : "Entrar para avaliar preço"}
      secondary busy={busy} onPress={() => status === "AUTHENTICATED" ? void consultar() : openAuth("Login")} />
    {avaliacao ? <>
      <Text style={{ color: colors.textSecondary }}>
        {avaliacao.positivos} confirmações · {avaliacao.negativos} contestações · Pontuação {avaliacao.confianca_score}.
        {" A pontuação começa em 1; não representa um selo de validação."}
      </Text>
      {avaliacao.pode_votar ? <>
        <AppButton label="Confirmar este preço" secondary busy={busy} selected={avaliacao.meu_voto === "positivo"}
          onPress={() => void consultar("positivo")} />
        <AppButton label="Contestar este preço" secondary busy={busy} selected={avaliacao.meu_voto === "negativo"}
          onPress={() => void consultar("negativo")} />
      </> : <Notice>Você é o autor deste preço e não pode votar nele.</Notice>}
    </> : null}
    {erro ? <Notice error>{erro}</Notice> : null}
  </View>;
}
