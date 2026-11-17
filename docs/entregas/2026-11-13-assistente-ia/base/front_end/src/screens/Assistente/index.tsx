import {
    useFocusEffect,
    useNavigation,
    type NavigationProp,
} from "@react-navigation/native";
import { useCallback, useRef, useState } from "react";

import { CartaoPosto } from "../../components/cartao-posto";
import {
    AppButton,
    AppField,
    Notice,
    Page,
    Surface,
} from "../../components/design";
import { useAcao } from "../../components/form-auth";
import { useFiltrosPostos } from "../../contexts/FiltrosPostosContext";
import type { Abas } from "../../routes/app.routes";
import {
    consultarAssistente,
    mensagemErroBusca,
    type BuscaAssistida,
} from "../../services/assistente";
import { produto } from "../../services/catalogoPostos";
import { iniciarVoz, vozDisponivel } from "../../services/voz";

export default function Assistente() {
  const navigation = useNavigation<NavigationProp<Abas>>();

  const { filtros, usuario, aplicar } = useFiltrosPostos();

  const [mensagem, setMensagem] = useState("");
  const [resultado, setResultado] = useState<BuscaAssistida | null>(null);
  const [ouvindo, setOuvindo] = useState(false);

  const voz = useRef<{ parar(): void } | null>(null);
  const consulta = useRef<AbortController | null>(null);

  const { busy, erro, setErro, run } = useAcao(
    "Não foi possível consultar os postos. Tente novamente.",
  );

  const pararVoz = useCallback(() => {
    const atual = voz.current;
    voz.current = null;
    atual?.parar();
    setOuvindo(false);
  }, []);

  useFocusEffect(
    useCallback(() => {
      return () => {
        pararVoz();
        consulta.current?.abort();
      };
    }, [pararVoz]),
  );

  function editar(texto: string) {
    setMensagem(texto);
    setResultado(null);
    setErro("");
  }

  function falar() {
    if (busy) return;

    if (voz.current) {
      pararVoz();
      return;
    }

    setErro("");

    const atual = { parar: () => {} };
    voz.current = atual;
    setOuvindo(true);

    try {
      const cancelar = iniciarVoz(
        (texto) => {
          if (voz.current === atual) editar(texto);
        },
        () => {
          if (voz.current === atual) {
            voz.current = null;
            setOuvindo(false);
          }
        },
        (texto) => {
          if (voz.current === atual) setErro(texto);
        },
      );

      if (voz.current === atual) {
        atual.parar = cancelar;
      } else {
        cancelar();
      }
    } catch (falha) {
      pararVoz();

      setErro(falha instanceof Error ? falha.message : "Voz indisponível.");
    }
  }

  function buscar() {
    if (!mensagem.trim()) {
      setErro("Informe o combustível ou a bandeira " + "que deseja procurar.");
      return;
    }

    setResultado(null);

    void run(async (signal) => {
      const atual = new AbortController();
      consulta.current = atual;

      const cancelar = () => atual.abort();

      signal.addEventListener("abort", cancelar, { once: true });

      try {
        const dados = await consultarAssistente(
          mensagem,
          filtros,
          usuario,
          atual.signal,
        );

        if (!atual.signal.aborted && !signal.aborted) {
          setResultado(dados);
        }
      } catch (falha) {
        if (!atual.signal.aborted && !signal.aborted) {
          setErro(mensagemErroBusca(falha));
        }
      } finally {
        signal.removeEventListener("abort", cancelar);

        if (consulta.current === atual) {
          consulta.current = null;
        }
      }
    });
  }

  function abrirMapa() {
    if (!resultado) return;

    aplicar(resultado.filtros);
    navigation.navigate("Mapa");
  }

  return (
    <Page
      title="Assistente Ouro"
      subtitle={
        "Procure combustível e bandeira " + "no catálogo de João Pessoa."
      }
    >
      <Surface>
        <AppField
          label="O que você procura?"
          value={mensagem}
          onChangeText={editar}
          placeholder="Ex.: diesel e etanol Shell mais barato"
          maxLength={500}
          multiline
          numberOfLines={3}
          style={{
            minHeight: 100,
            textAlignVertical: "top",
          }}
          editable={!busy && !ouvindo}
        />

        {vozDisponivel() ? (
          <>
            <AppButton
              label={ouvindo ? "Parar escuta" : "Falar busca"}
              secondary
              disabled={busy}
              onPress={falar}
            />

            <Notice>
              O navegador reconhece a fala. Revise o texto antes de buscar.
            </Notice>
          </>
        ) : (
          <Notice>
            Use o ditado do teclado para falar sua busca ou digite. O botão de
            voz depende do navegador e do dispositivo.
          </Notice>
        )}

        {erro ? <Notice error>{erro}</Notice> : null}

        <AppButton
          label="Buscar postos"
          busy={busy}
          disabled={ouvindo}
          onPress={buscar}
        />

        <Notice>
          Frases que precisam de interpretação podem ser enviadas ao serviço de
          IA. A localização é usada no catálogo para consultas por proximidade.
        </Notice>
      </Surface>

      {resultado ? (
        <>
          <Surface>
            <Notice>{resultado.mensagem}</Notice>

            <Notice>
              Combustíveis:{" "}
              {resultado.filtros.combustiveis.length
                ? resultado.filtros.combustiveis
                    .map((c) => produto(c).nome)
                    .join(", ")
                : "Todos"}
            </Notice>

            <Notice>
              Preço de referência: {produto(resultado.filtros.referencia).nome}
            </Notice>

            <Notice>
              Bandeira:{" "}
              {resultado.filtros.marca === "nao_informada"
                ? "Não informada"
                : resultado.filtros.marca || "Qualquer"}
            </Notice>

            <Notice>
              Ordenação:{" "}
              {resultado.filtros.ordenar === "preco"
                ? "Menor preço"
                : resultado.localizacao_usada
                  ? "Mais próximos"
                  : "Distância indisponível"}
            </Notice>

            <Notice>
              {resultado.interpretacao === "comando"
                ? "Busca por combustível e bandeira."
                : "Busca interpretada por IA " + "e conferida no catálogo."}
            </Notice>

            <AppButton label="Aplicar esta busca no mapa" onPress={abrirMapa} />
          </Surface>

          <Notice>
            Prévia de até 20 postos. Aplique os filtros para consultar no Mapa e
            no Feed.
          </Notice>

          {resultado.postos.map((posto) => (
            <CartaoPosto
              key={posto.id}
              posto={posto}
              selecionados={resultado.filtros.combustiveis}
              comparacao={resultado.postos}
              rotuloAcao={"Ver esta busca no mapa: " + posto.nome}
              onPress={abrirMapa}
            />
          ))}
        </>
      ) : null}
    </Page>
  );
}
