import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useState,
    type ReactNode,
} from "react";
import type { PosicaoUsuario } from "../components/mapa/tipos";
import { api } from "../services/API";
import {
    FILTROS_INICIAIS,
    lerCatalogo,
    parametrosPostos,
    type FiltrosPostos,
    type PostoCatalogo,
} from "../services/catalogoPostos";
import { obterPosicao } from "../utils/localizacao";

interface EstadoFiltros {
  filtros: FiltrosPostos;
  aplicar(filtros: FiltrosPostos): void;
  postos: PostoCatalogo[];
  marcas: string[];
  usuario: PosicaoUsuario | null;
  avisoGps: string;
  carregando: boolean;
  erro: string;
  atualizarLocalizacao(): void;
  recarregar(): void;
}
const Contexto = createContext<EstadoFiltros | null>(null);
export function FiltrosPostosProvider({ children }: { children: ReactNode }) {
  const [filtros, aplicar] = useState<FiltrosPostos>(FILTROS_INICIAIS);
  const [gps, setGps] = useState<{
    pronto: boolean;
    local: PosicaoUsuario | null;
    aviso: string;
  }>({ pronto: false, local: null, aviso: "" });
  const [dados, setDados] = useState<{
    chave: string;
    base: string;
    postos: PostoCatalogo[];
  }>({ chave: "", base: "", postos: [] });
  const [falha, setFalha] = useState({ chave: "", mensagem: "" });
  const [marcas, setMarcas] = useState<string[]>([]);
  const [revisao, setRevisao] = useState(0);
  const [revisaoGps, setRevisaoGps] = useState(0);
  const atualizarLocalizacao = useCallback(() => {
    setGps({ pronto: false, local: null, aviso: "" });
    setRevisaoGps((valor) => valor + 1);
  }, []);
  useEffect(() => {
    let ativo = true;
    void obterPosicao("mapa")
      .then((local) => {
        if (ativo)
          setGps({
            pronto: true,
            local: {
              lat: local.latitude,
              lon: local.longitude,
              precisaoM: local.precisaoM,
            },
            aviso: "",
          });
      })
      .catch((erro: unknown) => {
        if (ativo)
          setGps({
            pronto: true,
            local: null,
            aviso:
              (erro instanceof Error
                ? erro.message
                : "Localização indisponível.") +
              " João Pessoa é a referência do mapa. Distâncias pessoais indisponíveis.",
          });
      });
    return () => {
      ativo = false;
    };
  }, [revisaoGps]);
  const base = JSON.stringify([filtros, gps.local]);
  const chave = JSON.stringify([base, revisao, revisaoGps]);
  useEffect(() => {
    if (!gps.pronto) return;
    const controller = new AbortController();
    let atual = true;
    void api
      .get("/postos", {
        params: parametrosPostos(filtros, gps.local),
        signal: controller.signal,
      })
      .then((resposta) => {
        const postos = lerCatalogo(
          resposta.data,
          filtros.referencia,
          filtros.combustiveis,
        );
        if (!atual) return;
        setDados({ chave, base, postos });
        setMarcas((anteriores) =>
          [
            ...new Set([
              ...anteriores,
              ...postos.flatMap((p) => (p.marca ? [p.marca] : [])),
            ]),
          ].sort(),
        );
      })
      .catch((erro: unknown) => {
        if (atual && !controller.signal.aborted)
          setFalha({
            chave,
            mensagem:
              erro instanceof Error
                ? "Não foi possível atualizar: " + erro.message
                : "Não foi possível atualizar os postos.",
          });
      });
    return () => {
      atual = false;
      controller.abort();
    };
  }, [base, chave, filtros, gps.local, gps.pronto, revisao]);
  const recarregar = useCallback(() => setRevisao((valor) => valor + 1), []);
  const valor = useMemo(
    () => ({
      filtros,
      aplicar,
      postos: dados.base === base && gps.pronto ? dados.postos : [],
      marcas,
      usuario: gps.local,
      avisoGps: gps.aviso,
      carregando:
        !gps.pronto || (dados.chave !== chave && falha.chave !== chave),
      erro: falha.chave === chave ? falha.mensagem : "",
      atualizarLocalizacao,
      recarregar,
    }),
    [
      filtros,
      dados,
      base,
      chave,
      gps,
      marcas,
      falha,
      atualizarLocalizacao,
      recarregar,
    ],
  );
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}
export function useFiltrosPostos() {
  const valor = useContext(Contexto);
  if (!valor) throw new Error("FiltrosPostosProvider ausente.");
  return valor;
}
