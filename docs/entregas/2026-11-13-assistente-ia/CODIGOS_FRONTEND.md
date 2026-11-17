# CODIGOS FRONTEND

Aplicar conforme INSTRUCOES_CODEX_LOCAL.md. Os caminhos indicam os destinos no projeto.

## front_end/src/screens/Assistente/index.tsx

```tsx
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
```

## front_end/src/services/assistente.ts

```typescript
import { isAxiosError } from "axios";
import type { PosicaoUsuario } from "../components/mapa/tipos";
import { api } from "./API";
import {
  COMBUSTIVEIS, lerCatalogo, type Combustivel,
  type FiltrosPostos, type PostoCatalogo,
} from "./catalogoPostos";

export interface BuscaAssistida {
  filtros: FiltrosPostos;
  postos: PostoCatalogo[];
  total: number;
  interpretacao: "comando" | "gemini";
  localizacao_usada: boolean;
  mensagem: string;
}

const codigos = new Set<string>(COMBUSTIVEIS.map((c) => c.codigo));
// Respostas do provedor precisam passar pelo contrato antes de chegar ao estado global.
function objeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === "object" && valor !== null && !Array.isArray(valor);
}
// Aceita somente os seis produtos do catálogo fixo.
function combustivel(valor: unknown): valor is Combustivel {
  return typeof valor === "string" && codigos.has(valor);
}

// Clona a seleção e mantém uma referência única, sem substituir por outro produto.
export function validarFiltrosBusca(valor: unknown): FiltrosPostos {
  if (!objeto(valor) || !Array.isArray(valor.combustiveis)
    || valor.combustiveis.length > 6 || !valor.combustiveis.every(combustivel)
    || new Set(valor.combustiveis).size !== valor.combustiveis.length
    || !combustivel(valor.referencia)
    || (valor.combustiveis.length > 0 && !valor.combustiveis.includes(valor.referencia))
    || typeof valor.marca !== "string" || valor.marca.length > 120
    || /[\u0000-\u001f\u007f]/.test(valor.marca)
    || (valor.ordenar !== "preco" && valor.ordenar !== "distancia")) {
    throw new Error("A API retornou filtros de busca inválidos.");
  }
  return { combustiveis: [...valor.combustiveis], referencia: valor.referencia,
    marca: valor.marca, ordenar: valor.ordenar };
}

// Confere prévia, referência e distâncias; preços continuam vindo do catálogo.
export function validarBusca(valor: unknown): BuscaAssistida {
  if (!objeto(valor) || !Array.isArray(valor.postos) || valor.postos.length > 20
    || typeof valor.total !== "number" || !Number.isSafeInteger(valor.total)
    || valor.total < valor.postos.length || valor.total > 500
    || valor.postos.length !== Math.min(valor.total, 20)
    || typeof valor.localizacao_usada !== "boolean"
    || (valor.interpretacao !== "comando" && valor.interpretacao !== "gemini")
    || typeof valor.mensagem !== "string" || !valor.mensagem.trim()) {
    throw new Error("A API não retornou uma busca válida.");
  }
  const filtros = validarFiltrosBusca(valor.filtros);
  const postos = lerCatalogo(valor.postos, filtros.referencia, filtros.combustiveis);
  if (new Set(postos.map((p) => p.id)).size !== postos.length
    || postos.some((p) => valor.localizacao_usada
      ? p.distancia_m === undefined : p.distancia_m !== undefined)) {
    throw new Error("A API retornou dados inconsistentes para a busca.");
  }
  return { filtros, postos, total: valor.total, mensagem: valor.mensagem,
    interpretacao: valor.interpretacao, localizacao_usada: valor.localizacao_usada };
}

// Envia um retrato da busca com a sessão capturada; nunca cria coordenadas padrão.
export async function consultarAssistente(
  mensagem: string,
  filtros: FiltrosPostos,
  usuario: PosicaoUsuario | null,
  signal: AbortSignal,
  token?: string,
) {
  const texto = mensagem.trim();
  if (!texto || texto.length > 500) throw new Error("Informe uma busca de até 500 caracteres.");
  if (token !== undefined && !token.trim()) throw new Error("Entre novamente para usar o assistente.");
  if (signal.aborted) throw new Error("Busca cancelada.");
  const selecao = validarFiltrosBusca(filtros);
  if (usuario && (!Number.isFinite(usuario.lat) || Math.abs(usuario.lat) > 90
    || !Number.isFinite(usuario.lon) || Math.abs(usuario.lon) > 180
    || (usuario.lat === 0 && usuario.lon === 0))) {
    throw new Error("Atualize sua localização antes de buscar por proximidade.");
  }
  const { data } = await api.post("/ia/consultar", {
    mensagem: texto, filtros: selecao,
    ...(usuario ? { latitude: usuario.lat, longitude: usuario.lon } : {}),
  }, { signal, timeout: 60000,
    ...(token ? { headers: { Authorization: "Bearer " + token } } : {}),
  });
  return validarBusca(data);
}

// Mantém mensagens de rede/recusa legíveis, sem imprimir payloads ou credenciais.
export function mensagemErroBusca(erro: unknown) {
  if (isAxiosError<{ error?: unknown }>(erro)) {
    if (!erro.response) return "A API não respondeu. Confira a conexão e tente novamente.";
    const detalhe = typeof erro.response.data?.error === "string"
      ? erro.response.data.error : "Não foi possível consultar os postos.";
    return "HTTP " + erro.response.status + ": " + detalhe;
  }
  return erro instanceof Error ? erro.message : "Não foi possível consultar os postos.";
}
```

## front_end/src/services/voz.web.ts

```typescript
interface Reconhecimento {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((evento: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: ((evento: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  abort(): void;
}

// A captura direta exige suporte do navegador e contexto seguro (HTTPS ou localhost).
function construtor() {
  const navegador = globalThis as unknown as {
    SpeechRecognition?: new () => Reconhecimento;
    webkitSpeechRecognition?: new () => Reconhecimento;
    isSecureContext?: boolean;
  };
  return navegador.isSecureContext
    ? navegador.SpeechRecognition ?? navegador.webkitSpeechRecognition : undefined;
}

export const vozDisponivel = () => Boolean(construtor());

// Entrega uma transcrição revisável; a função retornada encerra a escuta uma só vez.
export function iniciarVoz(
  texto: (texto: string) => void,
  fim: () => void,
  erro: (mensagem: string) => void,
): () => void {
  const Criar = construtor();
  if (!Criar) throw new Error("Reconhecimento de voz indisponível. Use o ditado do teclado ou digite.");
  const voz = new Criar();
  let encerrado = false;
  let recebeuEvento = false;
  let tempo: ReturnType<typeof setTimeout> | null = null;

  // Remove handlers e temporizador antes de abortar, evitando callbacks duplicados.
  const encerrar = () => {
    if (encerrado) return;
    encerrado = true;
    if (tempo !== null) clearTimeout(tempo);
    voz.onresult = null;
    voz.onerror = null;
    voz.onend = null;
    try { voz.abort(); } catch { /* O navegador pode já ter encerrado. */ }
    fim();
  };

  voz.lang = "pt-BR";
  voz.interimResults = false;
  voz.continuous = false;
  voz.onresult = (evento) => {
    if (encerrado) return;
    recebeuEvento = true;
    try {
      const resultado = evento.results[0]?.[0]?.transcript;
      if (typeof resultado !== "string" || !resultado.trim()) {
        erro("Nenhuma fala foi reconhecida. Tente novamente ou digite.");
      } else if (resultado.trim().length > 500) {
        erro("A fala ficou muito longa. Faça uma busca de até 500 caracteres.");
      } else texto(resultado.trim());
    } finally { encerrar(); }
  };
  voz.onerror = (evento) => {
    if (encerrado) return;
    recebeuEvento = true;
    try {
      erro(evento.error === "not-allowed" || evento.error === "service-not-allowed"
        ? "Permita o microfone no navegador ou digite sua busca."
        : evento.error === "no-speech"
          ? "Nenhuma fala foi reconhecida. Tente novamente ou digite."
          : "Não foi possível reconhecer a fala. Tente novamente ou digite.");
    } finally { encerrar(); }
  };
  voz.onend = () => {
    if (encerrado) return;
    try {
      if (!recebeuEvento) erro("A escuta terminou sem reconhecer uma fala. Tente novamente ou digite.");
    } finally { encerrar(); }
  };
  tempo = setTimeout(() => {
    if (encerrado) return;
    try { erro("O tempo de escuta terminou. Tente novamente ou digite."); }
    finally { encerrar(); }
  }, 12000);
  try { voz.start(); }
  catch {
    encerrar();
    throw new Error("Não foi possível iniciar o microfone. Confira a permissão ou digite.");
  }
  return encerrar;
}
```
