# Códigos completos — controles de oferta, votos e detalhes

Substituir somente os três arquivos abaixo após conferir alterações posteriores. Os contratos de API e os serviços recebidos são preservados.

## front_end/src/components/confirmar-oferta.tsx

```tsx
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
```

## front_end/src/components/votar-preco.tsx

```tsx
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
```

## front_end/src/screens/ConsultaPostos/detalhes.tsx

```tsx
import Ionicons from "@expo/vector-icons/Ionicons";
import { useState } from "react";
import { Linking, Pressable, Text, View } from "react-native";

import { AppButton, Notice, useAppTheme } from "../../components/design";
import { BotaoFavorito } from "../../components/favoritos";
import { ConfirmarOferta } from "../../components/confirmar-oferta";
import { VotarPreco } from "../../components/votar-preco";
import type { PosicaoUsuario } from "../../components/mapa/tipos";
import { produtosCadastro } from "../../services/cadastroPreco";
import {
  dataPublicacao,
  precoFormatado,
  produto,
  type Combustivel,
  type PostoCatalogo,
} from "../../services/catalogoPostos";
import { styles } from "./layout";

interface Props {
  posto: PostoCatalogo;
  referencia: Combustivel;
  usuario: PosicaoUsuario | null;
  erroRota: string;
  onErroRota(mensagem: string): void;
  onRegistrar(combustivel: Combustivel): void;
  onVoltar(): void;
  onAtualizar(): void;
}

// Mantém a referência em destaque, com os demais combustíveis disponíveis para expansão.
export function DetalhesPostoConsulta({
  posto, referencia, usuario, erroRota, onErroRota, onRegistrar, onVoltar, onAtualizar,
}: Props) {
  const { colors } = useAppTheme();
  const permitidos = produtosCadastro(posto);
  const ofertas = [...posto.combustiveis].sort(
    (a, b) => Number(b.codigo === referencia) - Number(a.codigo === referencia),
  );

  // Abre a navegação externa usando a posição pessoal somente quando ela existe.
  function tracarRota() {
    onErroRota("");
    const origem = usuario
      ? "&origin=" + encodeURIComponent(usuario.lat + "," + usuario.lon) : "";
    const destino = encodeURIComponent(posto.latitude + "," + posto.longitude);
    void Linking.openURL(
      "https://www.google.com/maps/dir/?api=1&destination=" + destino + origem + "&travelmode=driving",
    ).catch(() => onErroRota("Não foi possível abrir o aplicativo de mapas."));
  }

  return (
    <View style={{ padding: 20, gap: 16, minWidth: 0 }}>
      <Text accessibilityRole="header" style={[styles.titulo, { color: colors.textPrimary }]}>
        {posto.nome}
      </Text>
      <BotaoFavorito postoId={posto.id} nome={posto.nome} />
      <Text style={{ color: colors.textSecondary, lineHeight: 22 }}>
        {posto.marca ?? "Marca não informada"}{" · "}{posto.endereco}
      </Text>
      {posto.bairro ? <Text style={{ color: colors.textSecondary }}>{posto.bairro}</Text> : null}

      <AppButton label="Traçar rota" secondary onPress={tracarRota} />
      {erroRota ? <Notice error>{erroRota}</Notice> : null}

      <View style={{ gap: 6 }}>
        <Text accessibilityRole="header" style={{ color: colors.textPrimary, fontSize: 19, fontWeight: "700" }}>
          Combustíveis e preços
        </Text>
        <Notice>Referência do mapa: {produto(referencia).nome}. Cada valor mantém sua própria unidade.</Notice>
      </View>

      {ofertas.map((oferta) => (
        <CartaoCombustivel
          key={JSON.stringify([posto.id, oferta.codigo, oferta.codigo === referencia])}
          postoId={posto.id}
          oferta={oferta}
          referencia={oferta.codigo === referencia}
          podeRegistrar={permitidos.some((item) => item.codigo === oferta.codigo)}
          onAtualizar={onAtualizar}
          onRegistrar={() => onRegistrar(oferta.codigo)}
        />
      ))}

      <AppButton label="Voltar à lista de postos" secondary onPress={onVoltar} />
    </View>
  );
}

interface PropsCartao {
  postoId: number;
  oferta: PostoCatalogo["combustiveis"][number];
  referencia: boolean;
  podeRegistrar: boolean;
  onAtualizar(): void;
  onRegistrar(): void;
}

// A faixa identifica o combustível; os controles secundários só montam ao expandir.
function CartaoCombustivel({ postoId, oferta, referencia, podeRegistrar, onAtualizar, onRegistrar }: PropsCartao) {
  const { colors } = useAppTheme();
  const [aberto, setAberto] = useState(referencia);
  const [focado, setFocado] = useState(false);
  const info = produto(oferta.codigo);
  const disponibilidade = oferta.disponivel === null ? "Oferta não confirmada"
    : oferta.disponivel ? "Disponibilidade confirmada" : "Não disponível";

  return (
    <View style={[styles.cartao, {
      backgroundColor: colors.surface,
      borderColor: colors.border,
      gap: 12,
      minWidth: 0,
    }]}>
      <View style={{ flexDirection: "row", gap: 10, alignItems: "center" }}>
        <View accessible={false} style={{ width: 6, height: 32, borderRadius: 3, backgroundColor: info.cor }} />
        <Text style={[styles.nome, { color: colors.textPrimary, flex: 1 }]}>
          {oferta.codigo === "recarga_eletrica" ? "⚡ " : ""}{info.nome}
        </Text>
      </View>
      {referencia ? <Text style={{ color: colors.textSecondary, fontWeight: "700" }}>Referência do mapa</Text> : null}
      <Text style={[styles.preco, { color: colors.textPrimary }]}>
        {oferta.preco === null ? "Sem preço informado" : precoFormatado(oferta.preco) + " / " + info.unidade}
      </Text>
      <Text style={{ color: colors.textSecondary }}>{disponibilidade}</Text>
      {oferta.preco !== null ? (
        <Text style={{ color: colors.textSecondary, lineHeight: 22 }}>
          {oferta.autor_nome ? "Informado por " + oferta.autor_nome + " · " : ""}
          {dataPublicacao(oferta.atualizado_em)}
        </Text>
      ) : null}

      <Pressable
        accessibilityRole="button"
        accessibilityLabel={(aberto ? "Ocultar" : "Ver") + " detalhes de " + info.nome}
        accessibilityState={{ expanded: aberto }}
        onPress={() => setAberto((valor) => !valor)}
        onFocus={() => setFocado(true)}
        onBlur={() => setFocado(false)}
        style={({ pressed }) => ({
          minHeight: 48,
          borderWidth: 1,
          borderColor: focado ? colors.textPrimary : colors.border,
          borderRadius: 14,
          padding: 12,
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          backgroundColor: colors.surface,
          opacity: pressed ? 0.75 : 1,
        })}
      >
        <Text style={{ color: colors.textPrimary, fontWeight: "600", flexShrink: 1 }}>
          {aberto ? "Ocultar detalhes" : "Ver detalhes e contribuir"}
        </Text>
        <Ionicons name={aberto ? "chevron-up" : "chevron-down"} size={20} color={colors.textPrimary} accessible={false} />
      </Pressable>

      {aberto ? (
        <View style={{ gap: 12 }}>
          {podeRegistrar ? (
            <AppButton label="Informar novo preço" secondary={!referencia} onPress={onRegistrar} />
          ) : null}
          {podeRegistrar && oferta.disponivel === null ? (
            <ConfirmarOferta postoId={postoId} codigo={oferta.codigo} nome={info.nome} onAtualizar={onAtualizar} />
          ) : null}
          {oferta.preco !== null && oferta.registo_id ? (
            <VotarPreco registoId={oferta.registo_id} nome={info.nome} />
          ) : null}
        </View>
      ) : null}
    </View>
  );
}
```
