import { useCallback, useEffect, useRef, useState } from "react";
import type {
    ComandoParaMapa,
    EstadoMapa,
    MensagemDoMapa,
    PosicaoUsuario,
    PostoNoMapa,
    RegiaoMapa,
} from "./tipos";

interface Opcoes {
  postos: PostoNoMapa[];
  usuario?: PosicaoUsuario | null;
  /** Transporte: entrega a string JSON ao mapa (WebView nativo ou iframe na web). */
  enviarBruto: (json: string) => void;
  onSelecionarPosto?: (id: number) => void;
  onRegiaoMudou?: (regiao: RegiaoMapa) => void;
  onAbrirLink?: (url: string) => void;
  timeoutCargaMs?: number;
}

const eNumero = (v: unknown): v is number =>
  typeof v === "number" && Number.isFinite(v);

/**
 * Máquina de estados e protocolo do mapa, compartilhada por nativo e web.
 *  - Só envia comandos depois do "pronto" do mapa.
 *  - Não reenvia o que não mudou (compara o JSON), mesmo que o pai recrie arrays a cada render.
 *  - Ao reiniciar (retry, processo do WebView morto), reenvia todo o estado atual.
 *  - Callbacks ficam em refs: mudar uma função do pai nunca provoca reenvio nem remontagem.
 */
export function useMapaBridge(opcoes: Opcoes) {
  const { postos, usuario, timeoutCargaMs = 15000 } = opcoes;

  const [estado, setEstado] = useState<EstadoMapa>("carregando");
  const [tentativa, setTentativa] = useState(0);

  const prontoRef = useRef(false);
  const enviadoRef = useRef<Record<string, string>>({});
  const pendenteRef = useRef<ComandoParaMapa | null>(null);

  const opcoesRef = useRef(opcoes);
  opcoesRef.current = opcoes;

  const despachar = useCallback((chave: string, cmd: ComandoParaMapa) => {
    if (!prontoRef.current) return; // será reenviado quando o mapa avisar "pronto"
    const json = JSON.stringify(cmd);
    if (enviadoRef.current[chave] === json) return;
    enviadoRef.current[chave] = json;
    opcoesRef.current.enviarBruto(json);
  }, []);

  // `estado` nas dependências: ao virar "pronto", os dois efeitos reenviam o estado atual.
  useEffect(() => {
    despachar("postos", { tipo: "postos", postos });
  }, [postos, estado, despachar]);

  useEffect(() => {
    despachar("usuario", { tipo: "usuario", usuario: usuario ?? null });
  }, [usuario, estado, despachar]);

  // Se o mapa nunca avisar "pronto" (CDN fora, sem rede), mostra erro com retry.
  useEffect(() => {
    if (estado !== "carregando") return;
    const t = setTimeout(
      () => setEstado((e) => (e === "carregando" ? "erro" : e)),
      timeoutCargaMs,
    );
    return () => clearTimeout(t);
  }, [estado, tentativa, timeoutCargaMs]);

  const reiniciar = useCallback(() => {
    prontoRef.current = false;
    enviadoRef.current = {};
    setEstado("carregando");
    setTentativa((t) => t + 1); // o componente usa isto como `key` para remontar a vista
  }, []);

  const aoFalhar = useCallback(() => {
    // No Android, onHttpError também dispara para sub-recursos (ex.: um tile 404). Com o mapa
    // já no ar isso não é falha de carga: ignora.
    if (prontoRef.current) return;
    setEstado("erro");
  }, []);

  const centralizar = useCallback((lat: number, lon: number, zoom?: number) => {
    const cmd: ComandoParaMapa = { tipo: "centralizar", lat, lon, zoom };
    if (prontoRef.current) opcoesRef.current.enviarBruto(JSON.stringify(cmd));
    else pendenteRef.current = cmd;
  }, []);

  const aoReceberMensagem = useCallback((bruto: unknown) => {
    if (typeof bruto !== "string") return;
    let msg: MensagemDoMapa;
    try {
      msg = JSON.parse(bruto);
    } catch {
      return;
    }
    if (
      !msg ||
      typeof msg !== "object" ||
      typeof (msg as { tipo?: unknown }).tipo !== "string"
    )
      return;

    const o = opcoesRef.current;
    switch (msg.tipo) {
      case "pronto":
        prontoRef.current = true;
        enviadoRef.current = {};
        setEstado("pronto");
        if (pendenteRef.current) {
          o.enviarBruto(JSON.stringify(pendenteRef.current));
          pendenteRef.current = null;
        }
        break;
      case "erro":
        // Erro de JS depois do mapa já estar no ar não derruba a tela.
        if (!prontoRef.current) setEstado("erro");
        else console.warn("[mapa] erro no WebView:", msg.motivo);
        break;
      case "posto_selecionado":
        if (eNumero(msg.id)) o.onSelecionarPosto?.(msg.id);
        break;
      case "regiao":
        if (
          eNumero(msg.lat) &&
          eNumero(msg.lon) &&
          eNumero(msg.zoom) &&
          Array.isArray(msg.bbox)
        ) {
          o.onRegiaoMudou?.({
            lat: msg.lat,
            lon: msg.lon,
            zoom: msg.zoom,
            bbox: msg.bbox,
          });
        }
        break;
      case "abrir_link":
        // Só https: o conteúdo vem de uma página web e não é confiável.
        if (typeof msg.url === "string" && /^https:\/\//i.test(msg.url))
          o.onAbrirLink?.(msg.url);
        break;
    }
  }, []);

  return {
    estado,
    tentativa,
    aoReceberMensagem,
    reiniciar,
    aoFalhar,
    centralizar,
  };
}
