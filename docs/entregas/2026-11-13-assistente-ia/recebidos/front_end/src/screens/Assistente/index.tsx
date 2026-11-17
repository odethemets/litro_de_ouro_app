import { useCallback, useRef, useState } from "react";
import { useFocusEffect, useNavigation, type NavigationProp } from "@react-navigation/native";
import { View } from "react-native";
import { AppButton, AppField, Notice, Page, Surface } from "../../components/design";
import { CartaoPosto } from "../../components/cartao-posto";
import { useAuth } from "../../contexts/AuthContext";
import { useFiltrosPostos } from "../../contexts/FiltrosPostosContext";
import type { Abas } from "../../routes/app.routes";
import { consultarAssistente, mensagemErroBusca, type BuscaAssistida } from "../../services/assistente";
import { produto } from "../../services/catalogoPostos";
import { iniciarVoz, vozDisponivel } from "../../services/voz";

// Resultados e rascunhos pertencem à sessão que iniciou a busca.
export default function Assistente() {
  const { token, status, openAuth } = useAuth();
  if (!token || status !== "AUTHENTICATED") {
    return (
      <Page title="Assistente Ouro" subtitle="Encontre o combustível que você procura.">
        <Surface>
          <Notice>Entre na sua conta para buscar por texto ou voz.</Notice>
          <AppButton label="Entrar para usar o assistente" onPress={() => openAuth("Login")} />
        </Surface>
      </Page>
    );
  }
  return <ConteudoAssistente key={JSON.stringify([token, status])} token={token} />;
}

// A busca produz uma prévia; somente a confirmação aplica os filtros no mapa/feed.
function ConteudoAssistente({ token }: { token: string }) {
  const navigation = useNavigation<NavigationProp<Abas>>();
  const { filtros, usuario, aplicar } = useFiltrosPostos();
  const contexto = JSON.stringify([filtros, usuario]);
  const [mensagem, setMensagem] = useState("");
  const [resultado, setResultado] = useState<{ dados: BuscaAssistida; contexto: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState("");
  const [aviso, setAviso] = useState("");
  const [ouvindo, setOuvindo] = useState(false);
  const voz = useRef<{ parar(): void } | null>(null);
  const consulta = useRef<AbortController | null>(null);
  const ativo = useRef(false);

  // Sair interrompe a escuta e descarta respostas, sem alegar cancelamento no servidor.
  useFocusEffect(useCallback(() => {
    ativo.current = true;
    setBusy(false);
    setOuvindo(false);
    return () => {
      ativo.current = false;
      const escuta = voz.current;
      voz.current = null;
      escuta?.parar();
      consulta.current?.abort();
      consulta.current = null;
    };
  }, []));

  // Desvincula o pedido antes do abort, protegendo também uma nova busca imediata.
  function cancelarBusca() {
    const atual = consulta.current;
    consulta.current = null;
    atual?.abort();
    setBusy(false);
  }

  // Texto revisado invalida a prévia anterior e qualquer resposta ainda pendente.
  function editar(texto: string) {
    cancelarBusca();
    setMensagem(texto);
    setResultado(null);
    setErro("");
    setAviso("");
  }

  // Encerra a escuta local; callbacks tardios perdem sua identidade antes do abort.
  function pararVoz() {
    const atual = voz.current;
    voz.current = null;
    atual?.parar();
    setOuvindo(false);
  }

  // A fala só preenche o campo: o usuário revisa antes de consultar e aplicar.
  function falar() {
    if (busy || !ativo.current) return;
    if (voz.current) { pararVoz(); return; }
    setErro("");
    setAviso("");
    const atual = { parar: () => {} };
    voz.current = atual;
    setOuvindo(true);
    try {
      const cancelar = iniciarVoz(
        (texto) => {
          if (ativo.current && voz.current === atual) editar(texto);
        },
        () => {
          if (ativo.current && voz.current === atual) {
            voz.current = null;
            setOuvindo(false);
          }
        },
        (texto) => {
          if (ativo.current && voz.current === atual) setErro(texto);
        },
      );
      if (voz.current === atual) atual.parar = cancelar;
      else cancelar();
    } catch (falha) {
      pararVoz();
      setErro(falha instanceof Error ? falha.message : "Não foi possível iniciar a escuta.");
    }
  }

  // Captura sessão e contexto; resultado de pedido cancelado não pode publicar estado.
  async function buscar() {
    if (consulta.current || voz.current || !ativo.current) return;
    if (!mensagem.trim() || mensagem.trim().length > 500) {
      setErro("Informe uma busca de até 500 caracteres, com combustível ou bandeira.");
      return;
    }
    const atual = new AbortController();
    consulta.current = atual;
    setBusy(true);
    setErro("");
    setAviso("");
    setResultado(null);
    try {
      const dados = await consultarAssistente(mensagem, filtros, usuario, atual.signal, token);
      if (ativo.current && consulta.current === atual && !atual.signal.aborted) {
        setResultado({ dados, contexto });
      }
    } catch (falha) {
      if (ativo.current && consulta.current === atual && !atual.signal.aborted) {
        setErro(mensagemErroBusca(falha));
      }
    } finally {
      if (ativo.current && consulta.current === atual) {
        consulta.current = null;
        setBusy(false);
      }
    }
  }

  const dados = resultado?.dados;
  const contextoMudou = !!resultado && resultado.contexto !== contexto;

  // Impede sobrescrever mudanças de filtro/GPS com uma interpretação anterior.
  function abrirMapa() {
    if (!resultado || contextoMudou || busy || !ativo.current) return;
    aplicar({ ...resultado.dados.filtros, combustiveis: [...resultado.dados.filtros.combustiveis] });
    navigation.navigate("Mapa");
  }

  return (
    <Page title="Assistente Ouro" subtitle="Diga ou escreva o combustível e a bandeira que procura.">
      <Surface>
        <AppField label="O que você procura?" value={mensagem} onChangeText={editar}
          placeholder="Ex.: diesel e etanol Shell mais barato" maxLength={500}
          multiline numberOfLines={3} style={{ minHeight: 100, textAlignVertical: "top" }}
          editable={!busy && !ouvindo} />
        {vozDisponivel() ? (
          <>
            <AppButton label={ouvindo ? "Parar escuta" : "Falar busca"} secondary disabled={busy} onPress={falar} />
            <Notice>{ouvindo ? "Ouvindo... Diga o que deseja procurar." : "Revise a transcrição antes de buscar."}</Notice>
            <Notice>O reconhecimento da fala é realizado pelo serviço do navegador.</Notice>
          </>
        ) : <Notice>Para falar, use o microfone do teclado. Você também pode digitar sua busca.</Notice>}
        {erro ? <Notice error>{erro}</Notice> : null}
        {aviso ? <View accessibilityLiveRegion="polite"><Notice>{aviso}</Notice></View> : null}
        <AppButton label="Buscar postos" busy={busy} disabled={ouvindo || !mensagem.trim()} onPress={() => void buscar()} />
        {busy ? <AppButton label="Cancelar busca" secondary onPress={() => {
          cancelarBusca();
          setAviso("Busca cancelada nesta tela. Você pode editar o texto e buscar novamente.");
        }} /> : null}
        <Notice>Frases que precisem de interpretação podem ser enviadas à IA. Os preços vêm do catálogo de postos.</Notice>
      </Surface>

      {dados ? (
        <>
          <Surface>
            <View accessibilityLiveRegion="polite"><Notice>{dados.mensagem}</Notice></View>
            <Notice>Combustíveis: {dados.filtros.combustiveis.length
              ? dados.filtros.combustiveis.map((c) => produto(c).nome).join(", ") : "Todos"}</Notice>
            <Notice>Preço de referência: {produto(dados.filtros.referencia).nome}</Notice>
            <Notice>Bandeira: {dados.filtros.marca === "nao_informada" ? "Não informada" : dados.filtros.marca || "Qualquer"}</Notice>
            <Notice>Ordenação: {dados.filtros.ordenar === "preco" ? "Menor preço"
              : dados.localizacao_usada ? "Mais próximos" : "Distância pessoal indisponível"}</Notice>
            {!dados.total ? <Notice>Nenhum posto corresponde a esta busca. Tente outra bandeira ou combustível.</Notice> : null}
            {contextoMudou ? <Notice error>Seus filtros ou sua posição mudaram. Busque novamente antes de aplicar.</Notice> : null}
            <AppButton label="Aplicar esta busca no mapa" disabled={contextoMudou || busy} onPress={abrirMapa} />
          </Surface>
          <Notice>Prévia de até 20 postos. Os filtros escolhidos serão compartilhados pelo Mapa e pelo Feed.</Notice>
          {!contextoMudou ? dados.postos.map((posto) => (
            <CartaoPosto key={posto.id} posto={posto} selecionados={dados.filtros.combustiveis}
              comparacao={dados.postos} rotuloAcao={"Aplicar busca no mapa: " + posto.nome} onPress={abrirMapa} />
          )) : null}
        </>
      ) : null}
    </Page>
  );
}
