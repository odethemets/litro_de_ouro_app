import { useEffect, useRef, useState } from "react";
import { View } from "react-native";

import { useAuth } from "../contexts/AuthContext";
import { api } from "../services/API";
import type { Combustivel } from "../services/catalogoPostos";
import { payloadOferta, validarConfirmacaoOferta } from "../services/ofertas";
import { obterPosicao } from "../utils/localizacao";
import { AppButton, Notice } from "./design";

interface Props {
  postoId: number;
  codigo: Combustivel;
  nome: string;
  onAtualizar(): void;
}

type Etapa = "inicio" | "revisao" | "confirmada" | "incerta";

// Isola a revisão por conta, posto e produto, mesmo se o pai reutilizar o componente.
export function ConfirmarOferta(props: Props) {
  const { token, status } = useAuth();
  return (
    <ControlesOferta
      key={JSON.stringify([token, status, props.postoId, props.codigo])}
      {...props}
    />
  );
}

// Confirma somente disponibilidade; sucesso da escrita e recarga são independentes.
function ControlesOferta({ postoId, codigo, nome, onAtualizar }: Props) {
  const { token, status, openAuth } = useAuth();
  const pedido = useRef<AbortController | null>(null);
  const [etapa, setEtapa] = useState<Etapa>("inicio");
  const [busy, setBusy] = useState(false);
  const [mensagem, setMensagem] = useState("");
  const [erro, setErro] = useState("");

  useEffect(() => () => pedido.current?.abort(), []);

  // Solicita a recarga sem transformar falha de interface em falha da confirmação.
  function atualizar() {
    try {
      onAtualizar();
    } catch {
      setErro("Não foi possível iniciar a atualização do catálogo. Tente atualizar novamente.");
    }
  }

  // GPS ocorre após a revisão; uma resposta perdida nunca autoriza reenvio automático.
  async function confirmar() {
    if (!token || status !== "AUTHENTICATED" || pedido.current) return;
    const controller = new AbortController();
    pedido.current = controller;
    setBusy(true);
    setErro("");
    setMensagem("");
    let enviou = false;

    try {
      const payload = payloadOferta(await obterPosicao("registro"));
      if (controller.signal.aborted) return;
      enviou = true;
      const resposta = await api.post(
        `/postos/${postoId}/ofertas/${codigo}/confirmar`,
        payload,
        { headers: { Authorization: "Bearer " + token }, signal: controller.signal },
      );
      if (controller.signal.aborted) return;
      validarConfirmacaoOferta(resposta.data, postoId, codigo);
      setEtapa("confirmada");
      setMensagem("Oferta confirmada. Atualizando os combustíveis deste posto.");
      atualizar();
    } catch (falha) {
      if (controller.signal.aborted) return;
      if (!enviou) {
        setErro(falha instanceof Error ? falha.message : "Não foi possível verificar sua localização.");
        return;
      }
      const resposta = (falha as {
        response?: { status?: number; data?: { error?: unknown } };
      } | null)?.response;
      const statusHttp = resposta?.status ?? 0;
      if (statusHttp >= 400 && statusHttp < 500 && statusHttp !== 408) {
        setErro(typeof resposta?.data?.error === "string"
          ? resposta.data.error : "A confirmação foi recusada. Confira os dados antes de tentar novamente.");
      } else {
        setEtapa("incerta");
        setErro("A confirmação não chegou. A oferta pode ter sido confirmada. Atualize o catálogo antes de tentar novamente.");
      }
    } finally {
      if (pedido.current === controller) pedido.current = null;
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return (
    <View style={{ gap: 10 }}>
      {etapa === "inicio" ? (
        <AppButton
          label={status === "AUTHENTICATED" ? "Confirmar disponibilidade" : "Entrar para confirmar oferta"}
          secondary
          onPress={() => {
            setErro("");
            if (status === "AUTHENTICATED") setEtapa("revisao");
            else openAuth("Login");
          }}
        />
      ) : null}

      {etapa === "revisao" ? (
        <>
          <Notice>
            Você verificou que este local oferece {nome}? Usaremos sua localização
            atual para conferir a proximidade. Isso não cadastra um preço.
          </Notice>
          <AppButton label="Sim, verifiquei neste local" busy={busy} onPress={() => void confirmar()} />
          <AppButton label="Cancelar" secondary disabled={busy} onPress={() => {
            setEtapa("inicio");
            setErro("");
          }} />
        </>
      ) : null}

      {busy ? <Notice>Verificando localização e enviando confirmação...</Notice> : null}
      {mensagem ? <View accessibilityLiveRegion="polite"><Notice>{mensagem}</Notice></View> : null}
      {erro ? <Notice error>{erro}</Notice> : null}

      {etapa === "confirmada" || etapa === "incerta" ? (
        <AppButton label="Atualizar catálogo" secondary onPress={atualizar} />
      ) : null}
    </View>
  );
}
