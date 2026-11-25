import { useFocusEffect } from "@react-navigation/native";
import { useCallback, useEffect, useRef, useState } from "react";
import { View } from "react-native";

import { useFiltrosPostos } from "../contexts/FiltrosPostosContext";
import { useBuscaVoz } from "../hooks/useBuscaVoz";
import {
    consultarAssistente,
    mensagemErroBusca,
    type BuscaAssistida,
} from "../services/assistente";
import { produto } from "../services/catalogoPostos";
import { CartaoPosto } from "./cartao-posto";
import { AppButton, AppField, Notice, Surface } from "./design";

interface Props {
  token: string;
  aoAplicar(): void;
  mostrarPostos?: boolean;
}

export function FormularioBuscaAssistida({
  token,
  aoAplicar,
  mostrarPostos = true,
}: Props) {
  const { filtros, usuario, aplicar } = useFiltrosPostos();
  const contexto = JSON.stringify([filtros, usuario]);

  const [mensagem, definirMensagem] = useState("");
  const [resultado, definirResultado] = useState<{
    dados: BuscaAssistida;
    contexto: string;
  } | null>(null);
  const [busy, definirBusy] = useState(false);
  const [erro, definirErro] = useState("");
  const [aviso, definirAviso] = useState("");

  const consulta = useRef<AbortController | null>(null);
  const ativo = useRef(false);

  function cancelarBusca() {
    const atual = consulta.current;
    consulta.current = null;
    atual?.abort();
    definirBusy(false);
  }

  function editar(texto: string) {
    cancelarBusca();
    definirMensagem(texto);
    definirResultado(null);
    definirErro("");
    definirAviso("");
  }

  const voz = useBuscaVoz({
    token,
    aoTexto: editar,
    aoErro: definirErro,
  });

  const cancelarVoz = useRef(voz.cancelar);
  useEffect(() => {
    cancelarVoz.current = voz.cancelar;
  }, [voz.cancelar]);

  useFocusEffect(
    useCallback(() => {
      ativo.current = true;
      definirBusy(false);

      return () => {
        ativo.current = false;
        cancelarVoz.current();

        const atual = consulta.current;
        consulta.current = null;
        atual?.abort();
      };
    }, []),
  );

  const usandoVoz = voz.estado !== "parado";
  const vozProcessando =
    voz.estado === "preparando" ||
    voz.estado === "transcrevendo" ||
    voz.estado === "cancelando";

  function falar() {
    if (consulta.current || !ativo.current) return;

    if (voz.estado === "ouvindo") {
      voz.parar();
      return;
    }

    if (usandoVoz) return;

    definirResultado(null);
    definirErro("");
    definirAviso("");
    voz.iniciar();
  }

  async function buscar() {
    if (consulta.current || voz.emAndamento() || !ativo.current) {
      return;
    }

    const texto = mensagem.trim();

    if (!texto || texto.length > 500) {
      definirErro(
        "Informe uma busca de até 500 caracteres, com combustível ou bandeira.",
      );
      return;
    }

    const atual = new AbortController();
    consulta.current = atual;

    definirBusy(true);
    definirErro("");
    definirAviso("");
    definirResultado(null);

    try {
      const dados = await consultarAssistente(
        texto,
        filtros,
        usuario,
        atual.signal,
        token,
      );

      if (
        ativo.current &&
        consulta.current === atual &&
        !atual.signal.aborted
      ) {
        definirResultado({ dados, contexto });
      }
    } catch (falha) {
      if (
        ativo.current &&
        consulta.current === atual &&
        !atual.signal.aborted
      ) {
        definirErro(mensagemErroBusca(falha));
      }
    } finally {
      if (ativo.current && consulta.current === atual) {
        consulta.current = null;
        definirBusy(false);
      }
    }
  }

  const dados = resultado?.dados;
  const contextoMudou = !!resultado && resultado.contexto !== contexto;

  function aplicarBusca() {
    if (
      !resultado ||
      contextoMudou ||
      consulta.current ||
      voz.emAndamento() ||
      !ativo.current
    ) {
      return;
    }

    aplicar({
      ...resultado.dados.filtros,
      combustiveis: [...resultado.dados.filtros.combustiveis],
    });

    aoAplicar();
  }

  return (
    <>
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
          editable={!busy && !usandoVoz}
        />

        {voz.disponivel ? (
          <>
            <AppButton
              label={voz.estado === "ouvindo" ? "Concluir fala" : "Falar busca"}
              secondary
              disabled={busy || vozProcessando}
              onPress={falar}
            />

            <Notice>
              {voz.estado === "preparando"
                ? "Preparando o microfone..."
                : voz.estado === "ouvindo"
                  ? "Ouvindo... Diga o que deseja procurar."
                  : voz.estado === "transcrevendo"
                    ? "Transcrevendo sua fala..."
                    : voz.estado === "cancelando"
                      ? "Encerrando a gravação..."
                      : "Revise a transcrição antes de buscar."}
            </Notice>

            <Notice>{voz.descricao}</Notice>
          </>
        ) : (
          <Notice>
            Para falar, use o microfone do teclado. Você também pode digitar sua
            busca.
          </Notice>
        )}

        {usandoVoz ? (
          <AppButton label="Cancelar voz" secondary onPress={voz.cancelar} />
        ) : null}

        {erro ? <Notice error>{erro}</Notice> : null}

        {aviso ? (
          <View accessibilityLiveRegion="polite">
            <Notice>{aviso}</Notice>
          </View>
        ) : null}

        <AppButton
          label="Buscar postos"
          busy={busy}
          disabled={usandoVoz || !mensagem.trim()}
          onPress={() => void buscar()}
        />

        {busy ? (
          <AppButton
            label="Cancelar busca"
            secondary
            onPress={() => {
              cancelarBusca();
              definirAviso(
                "Busca cancelada nesta tela. Você pode editar o texto e buscar novamente.",
              );
            }}
          />
        ) : null}

        <Notice>
          Frases que precisem de interpretação podem ser enviadas à IA. Os
          preços vêm do catálogo de postos.
        </Notice>
      </Surface>

      {dados ? (
        <>
          <Surface>
            <View accessibilityLiveRegion="polite">
              <Notice>{dados.mensagem}</Notice>
            </View>

            <Notice>{dados.total} postos encontrados nesta busca.</Notice>

            <Notice>
              Combustíveis:{" "}
              {dados.filtros.combustiveis.length
                ? dados.filtros.combustiveis
                    .map((c) => produto(c).nome)
                    .join(", ")
                : "Todos"}
            </Notice>

            <Notice>
              Preço de referência: {produto(dados.filtros.referencia).nome}
            </Notice>

            <Notice>
              Bandeira:{" "}
              {dados.filtros.marca === "nao_informada"
                ? "Não informada"
                : dados.filtros.marca || "Qualquer"}
            </Notice>

            <Notice>
              Ordenação:{" "}
              {dados.filtros.ordenar === "preco"
                ? "Menor preço"
                : dados.localizacao_usada
                  ? "Mais próximos"
                  : "Distância pessoal indisponível"}
            </Notice>

            {!dados.total ? (
              <Notice>
                Nenhum posto corresponde a esta busca. Tente outra bandeira ou
                combustível.
              </Notice>
            ) : null}

            {contextoMudou ? (
              <Notice error>
                Seus filtros ou sua posição mudaram. Busque novamente antes de
                aplicar.
              </Notice>
            ) : null}

            <AppButton
              label="Aplicar esta busca no mapa"
              disabled={contextoMudou || busy || usandoVoz}
              onPress={aplicarBusca}
            />
          </Surface>

          {mostrarPostos ? (
            <>
              <Notice>
                Prévia de até 20 postos. Os filtros serão compartilhados pelo
                Mapa e pelo Feed.
              </Notice>

              {!contextoMudou
                ? dados.postos.map((posto) => (
                    <CartaoPosto
                      key={posto.id}
                      posto={posto}
                      selecionados={dados.filtros.combustiveis}
                      comparacao={dados.postos}
                      rotuloAcao={"Aplicar busca no mapa: " + posto.nome}
                      onPress={aplicarBusca}
                    />
                  ))
                : null}
            </>
          ) : null}
        </>
      ) : null}
    </>
  );
}
