import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
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
  enviarBruto: (json: string) => void;
  onSelecionarPosto?: (id: number) => void;
  onRegiaoMudou?: (regiao: RegiaoMapa) => void;
  onAbrirLink?: (url: string) => void;
  timeoutCargaMs?: number;
}

const eNumero = (valor: unknown): valor is number =>
  typeof valor === "number" && Number.isFinite(valor);

export function useMapaBridge(opcoes: Opcoes) {
  const { postos, usuario, timeoutCargaMs = 15000 } = opcoes;

  const [estado, setEstado] = useState<EstadoMapa>("carregando");
  const [tentativa, setTentativa] = useState(0);

  const prontoRef = useRef(false);
  const enviadoRef = useRef<Record<string, string>>({});
  const pendenteRef = useRef<ComandoParaMapa | null>(null);
  const opcoesRef = useRef(opcoes);

  // Atualiza as opções depois da renderização confirmada.
  // Os callbacks continuam estáveis sem modificar refs durante o render.
  useLayoutEffect(() => {
    opcoesRef.current = opcoes;
  }, [opcoes]);

  const despachar = useCallback((chave: string, comando: ComandoParaMapa) => {
    if (!prontoRef.current) return;

    const json = JSON.stringify(comando);

    if (enviadoRef.current[chave] === json) return;

    enviadoRef.current[chave] = json;
    opcoesRef.current.enviarBruto(json);
  }, []);

  useEffect(() => {
    despachar("postos", {
      tipo: "postos",
      postos,
    });
  }, [postos, estado, despachar]);

  useEffect(() => {
    despachar("usuario", {
      tipo: "usuario",
      usuario: usuario ?? null,
    });
  }, [usuario, estado, despachar]);

  useEffect(() => {
    if (estado !== "carregando") return;

    const temporizador = setTimeout(() => {
      setEstado((atual) => (atual === "carregando" ? "erro" : atual));
    }, timeoutCargaMs);

    return () => clearTimeout(temporizador);
  }, [estado, tentativa, timeoutCargaMs]);

  const reiniciar = useCallback(() => {
    prontoRef.current = false;
    enviadoRef.current = {};
    setEstado("carregando");
    setTentativa((atual) => atual + 1);
  }, []);

  const aoFalhar = useCallback(() => {
    if (prontoRef.current) return;
    setEstado("erro");
  }, []);

  const centralizar = useCallback((lat: number, lon: number, zoom?: number) => {
    const comando: ComandoParaMapa = {
      tipo: "centralizar",
      lat,
      lon,
      zoom,
    };

    if (prontoRef.current) {
      opcoesRef.current.enviarBruto(JSON.stringify(comando));
    } else {
      pendenteRef.current = comando;
    }
  }, []);

  const aoReceberMensagem = useCallback((bruto: unknown) => {
    if (typeof bruto !== "string") return;

    let mensagem: MensagemDoMapa;

    try {
      mensagem = JSON.parse(bruto);
    } catch {
      return;
    }

    if (
      !mensagem ||
      typeof mensagem !== "object" ||
      typeof (mensagem as { tipo?: unknown }).tipo !== "string"
    ) {
      return;
    }

    const atuais = opcoesRef.current;

    switch (mensagem.tipo) {
      case "pronto":
        prontoRef.current = true;
        enviadoRef.current = {};
        setEstado("pronto");

        if (pendenteRef.current) {
          atuais.enviarBruto(JSON.stringify(pendenteRef.current));
          pendenteRef.current = null;
        }
        break;

      case "erro":
        if (!prontoRef.current) {
          setEstado("erro");
        } else {
          console.warn("[mapa] erro no WebView:", mensagem.motivo);
        }
        break;

      case "posto_selecionado":
        if (eNumero(mensagem.id)) {
          atuais.onSelecionarPosto?.(mensagem.id);
        }
        break;

      case "regiao":
        if (
          eNumero(mensagem.lat) &&
          eNumero(mensagem.lon) &&
          eNumero(mensagem.zoom) &&
          Array.isArray(mensagem.bbox)
        ) {
          atuais.onRegiaoMudou?.({
            lat: mensagem.lat,
            lon: mensagem.lon,
            zoom: mensagem.zoom,
            bbox: mensagem.bbox,
          });
        }
        break;

      case "abrir_link":
        if (
          typeof mensagem.url === "string" &&
          /^https:\/\//i.test(mensagem.url)
        ) {
          atuais.onAbrirLink?.(mensagem.url);
        }
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
