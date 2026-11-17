import { useEffect, useRef, useState } from "react";
import { View } from "react-native";

import { useAuth } from "../contexts/AuthContext";
import { api } from "../services/API";
import type { Combustivel } from "../services/catalogoPostos";
import { payloadOferta, validarConfirmacaoOferta } from "../services/ofertas";
import { obterPosicao } from "../utils/localizacao";
import { AppButton, Notice } from "./design";

export function ConfirmarOferta({ postoId, codigo, nome, onAtualizar }: {
  postoId: number; codigo: Combustivel; nome: string; onAtualizar(): void;
}) {
  const { token } = useAuth();
  return <ControlesOferta key={token ?? "visitante"} postoId={postoId} codigo={codigo} nome={nome} onAtualizar={onAtualizar} />;
}

function ControlesOferta({ postoId, codigo, nome, onAtualizar }: {
  postoId: number; codigo: Combustivel; nome: string; onAtualizar(): void;
}) {
  const { token, status, openAuth } = useAuth();
  const atual = useRef(token);
  const ocupado = useRef(false);
  const [busy, setBusy] = useState(false);
  const [revisando, setRevisando] = useState(false);
  const [mensagem, setMensagem] = useState("");
  useEffect(() => {
    atual.current = token;
    return () => { atual.current = null; };
  }, [token]);

  async function confirmar() {
    if (!token || ocupado.current) return;
    const sessao = token;
    ocupado.current = true;
    setBusy(true);
    setMensagem("");
    try {
      const payload = payloadOferta(await obterPosicao("registro"));
      if (atual.current !== sessao) return;
      const r = await api.post(`/postos/${postoId}/ofertas/${codigo}/confirmar`, payload,
        { headers: { Authorization: "Bearer " + sessao } });
      if (atual.current !== sessao) return;
      validarConfirmacaoOferta(r.data, postoId, codigo);
      onAtualizar();
      setRevisando(false);
      setMensagem("Oferta confirmada. Atualizando o catálogo.");
    } catch (e) {
      if (atual.current !== sessao) return;
      const resposta = (e as { response?: { data?: { error?: string } } }).response;
      setMensagem(resposta?.data?.error ?? (e instanceof Error && !resposta
        ? e.message : "A confirmação não chegou. Atualize o catálogo antes de repetir."));
    } finally {
      ocupado.current = false;
      if (atual.current === sessao) setBusy(false);
    }
  }

  return <View style={{ gap: 8 }}>
    {revisando ? <>
      <Notice>Confirme somente se verificou neste local a oferta de {nome}. A localização atual será usada para verificar a proximidade.</Notice>
      <AppButton label={"Verifiquei: este local oferece " + nome} busy={busy} onPress={() => void confirmar()} />
      <AppButton label="Cancelar confirmação" secondary disabled={busy} onPress={() => setRevisando(false)} />
    </> : <AppButton label={status === "AUTHENTICATED" ? "Confirmar oferta de " + nome : "Entrar para confirmar oferta"}
      secondary onPress={() => status === "AUTHENTICATED" ? setRevisando(true) : openAuth("Login")} />}
    {mensagem ? <Notice>{mensagem}</Notice> : null}
  </View>;
}
