import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../services/API";
import { FalhaCadastro, produtosCadastro } from "../../services/cadastroPreco";
import type { Combustivel, PostoCatalogo } from "../../services/catalogoPostos";
import {
  criarEnvioPrecosLote,
  validarPedidoLote,
  type ConfirmacaoPrecosLote,
  type PedidoPrecosLote,
} from "../../services/precosLote";
import {
  lerTextoPrecos,
  mesclarSugestoes,
  type RascunhoPreco,
  type SugestaoPreco,
} from "../../services/rascunhoPrecos";
import { lerTokenAtivo } from "../../services/sessao";
import { obterPosicao, type PosicaoGps } from "../../utils/localizacao";

export function useCadastroLote(
  posto: PostoCatalogo | undefined,
  preferido: Combustivel,
  token: string,
  atualizar: () => void | Promise<unknown>,
) {
  const [itens, setItens] = useState<RascunhoPreco[]>([]);
  const [texto, setTexto] = useState("");

  const [sugestoes, setSugestoes] = useState<SugestaoPreco[] | null>(null);

  const [revisao, setRevisao] = useState<PedidoPrecosLote | null>(null);

  const [confirmacao, setConfirmacao] = useState<ConfirmacaoPrecosLote | null>(
    null,
  );

  const [falha, setFalha] = useState<FalhaCadastro | null>(null);

  const [aviso, setAviso] = useState("");
  const [local, setLocal] = useState<PosicaoGps | null>(null);
  const [checandoGps, setChecandoGps] = useState(false);
  const [enviando, setEnviando] = useState(false);

  const montado = useRef(true);
  const configurado = useRef<number | null>(null);
  const gpsOcupado = useRef(false);
  const emEnvio = useRef(false);

  const envio = useRef<ReturnType<typeof criarEnvioPrecosLote> | null>(null);

  const incerto = falha?.tipo === "incerto";

  const bloqueado = enviando || incerto || !!confirmacao || !!revisao;

  useEffect(() => {
    montado.current = true;

    return () => {
      montado.current = false;
    };
  }, []);

  useEffect(() => {
    if (!posto) {
      return;
    }

    if (configurado.current === posto.id) {
      // Uma aprovação pode liberar produto novo com o rascunho aberto.
      // Preserva edições e produtos removidos para a revisão.
      setItens((atuais) => {
        const novos = produtosCadastro(posto).filter(
          (p) => !atuais.some((i) => i.codigo === p.codigo),
        );

        return novos.length
          ? [
              ...atuais,
              ...novos.map((p) => ({
                codigo: p.codigo,
                textoPreco: "",
                fotoUrl: null,
                selecionado: false,
              })),
            ]
          : atuais;
      });

      return;
    }

    configurado.current = posto.id;

    setItens(
      produtosCadastro(posto).map((p) => ({
        codigo: p.codigo,
        textoPreco: "",
        fotoUrl: null,
        selecionado: p.codigo === preferido,
      })),
    );

    setTexto("");
    setSugestoes(null);
    setRevisao(null);
    setConfirmacao(null);
    setFalha(null);
    setAviso("");
    setLocal(null);
  }, [posto, preferido]);

  useEffect(() => {
    envio.current = criarEnvioPrecosLote({
      tokenAtual: () => (montado.current ? lerTokenAtivo() : null),

      obterGps: async () => {
        const gps = await obterPosicao("registro");

        if (montado.current) {
          setLocal(gps);
        }

        return gps;
      },

      postar: (payload, sessao) =>
        api.post("/precos/lote", payload, {
          timeout: 45000,
          headers: {
            Authorization: "Bearer " + sessao,
          },
        }),
    });

    return () => {
      envio.current = null;
    };
  }, []);

  const limparComprovante = useCallback(() => {
    setItens((atuais) =>
      atuais.map((i) => ({
        ...i,
        fotoUrl: null,
      })),
    );

    setSugestoes(null);
  }, []);

  function alterar(codigo: Combustivel, mudanca: Partial<RascunhoPreco>) {
    if (bloqueado) {
      return;
    }

    setItens((atuais) =>
      atuais.map((i) =>
        i.codigo === codigo ? { ...i, ...mudanca, codigo } : i,
      ),
    );

    setFalha(null);
    setAviso("");
  }

  function receberFoto(valores: SugestaoPreco[]) {
    if (bloqueado || !posto) {
      return;
    }

    const permitidos = produtosCadastro(posto).map((p) => p.codigo);

    if (
      !valores.length ||
      valores.some((v) => !permitidos.includes(v.codigo))
    ) {
      setFalha(
        new FalhaCadastro(
          "validacao",
          "A leitura contém um produto indisponível neste posto.",
        ),
      );

      return;
    }

    setSugestoes(valores.map((i) => ({ ...i })));

    setFalha(null);
    setAviso("");
  }

  function lerTexto() {
    if (bloqueado || !posto) {
      return;
    }

    try {
      setSugestoes(
        lerTextoPrecos(
          texto,
          produtosCadastro(posto).map((p) => p.codigo),
        ),
      );

      setFalha(null);
    } catch (erro) {
      setFalha(
        erro instanceof FalhaCadastro
          ? erro
          : new FalhaCadastro("validacao", "Confira o texto informado."),
      );
    }
  }

  function preencher(substituir: boolean) {
    if (bloqueado || !sugestoes) {
      return;
    }

    try {
      setItens(mesclarSugestoes(itens, sugestoes, substituir));

      setSugestoes(null);
      setFalha(null);

      setAviso(
        "Confira os campos preenchidos e selecione somente os preços que deseja registrar.",
      );
    } catch (erro) {
      setFalha(
        erro instanceof FalhaCadastro
          ? erro
          : new FalhaCadastro("validacao", "Confira as sugestões."),
      );
    }
  }

  function revisar() {
    if (bloqueado || !posto || checandoGps) {
      return;
    }

    try {
      setRevisao(
        validarPedidoLote({
          posto,
          token,
          itens: itens.filter((i) => i.selecionado),
        }),
      );

      setFalha(null);
      setSugestoes(null);
      setAviso("");
    } catch (erro) {
      setFalha(
        erro instanceof FalhaCadastro
          ? erro
          : new FalhaCadastro("validacao", "Revise os preços selecionados."),
      );
    }
  }

  async function enviar() {
    const servico = envio.current;

    if (!servico || emEnvio.current || !revisao || incerto || confirmacao) {
      return;
    }

    emEnvio.current = true;
    setEnviando(true);
    setFalha(null);
    setAviso("");

    const pedido = revisao;

    try {
      const resultado = await servico.enviar(pedido);

      if (!montado.current || lerTokenAtivo() !== token) {
        return;
      }

      setConfirmacao(resultado);
      setRevisao(null);

      setItens((atuais) =>
        atuais.map((i) => ({
          ...i,
          textoPreco: "",
          fotoUrl: null,
        })),
      );

      // Falha ao recarregar não torna um cadastro confirmado incerto.
      try {
        await atualizar();
      } catch {
        if (montado.current) {
          setAviso(
            "Preços confirmados. Atualize o catálogo para conferir os valores.",
          );
        }
      }
    } catch (erro) {
      if (montado.current && lerTokenAtivo() === token) {
        setFalha(
          erro instanceof FalhaCadastro
            ? erro
            : new FalhaCadastro(
                "incerto",
                "Não foi possível confirmar o lote. Confira sua atividade antes de tentar novamente.",
              ),
        );
      }
    } finally {
      emEnvio.current = false;

      if (montado.current) {
        setEnviando(false);
      }
    }
  }

  async function verificarGps() {
    if (gpsOcupado.current || bloqueado) {
      return;
    }

    gpsOcupado.current = true;
    setChecandoGps(true);
    setAviso("");

    try {
      const gps = await obterPosicao("registro");

      if (montado.current) {
        setLocal(gps);
      }
    } catch (erro) {
      if (montado.current) {
        setLocal(null);

        setAviso(
          erro instanceof Error ? erro.message : "Localização indisponível.",
        );
      }
    } finally {
      gpsOcupado.current = false;

      if (montado.current) {
        setChecandoGps(false);
      }
    }
  }

  function novo() {
    if (enviando) {
      return;
    }

    setConfirmacao(null);
    setRevisao(null);
    setFalha(null);
    setSugestoes(null);
    setTexto("");
    setAviso("");

    setItens((atuais) =>
      atuais.map((i) => ({
        ...i,
        textoPreco: "",
        fotoUrl: null,
      })),
    );
  }

  return {
    itens,
    texto,
    setTexto,
    sugestoes,
    setSugestoes,
    revisao,
    setRevisao,
    confirmacao,
    falha,
    aviso,
    local,
    checandoGps,
    enviando,
    incerto,
    bloqueado,
    alterar,
    receberFoto,
    lerTexto,
    preencher,
    revisar,
    enviar,
    verificarGps,
    limparComprovante,
    novo,
  };
}

export type CadastroLote = ReturnType<typeof useCadastroLote>;
