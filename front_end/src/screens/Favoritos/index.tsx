import { useCallback, useState } from "react";

import {
  AvisoFavoritos,
  CartaoPostoComFavorito,
} from "../../components/favoritos";

import {
  AppButton,
  AppField,
  Notice,
  Page,
  Surface,
} from "../../components/design";

import { useFavoritos } from "../../contexts/FavoritosContext";
import { useFiltrosPostos } from "../../contexts/FiltrosPostosContext";
import { useConsultaConta } from "../../hooks/useConsultaConta";
import { api } from "../../services/API";

import {
  COMBUSTIVEIS,
  dataPublicacao,
  lerCatalogo,
  precoFormatado,
} from "../../services/catalogoPostos";

export default function Favoritos() {
  const favoritos = useFavoritos();
  const { filtros } = useFiltrosPostos();

  const [todos, setTodos] = useState(false);
  const [busca, setBusca] = useState("");
  const [detalhe, setDetalhe] = useState<number | null>(null);

  const carregar = useCallback(
    async (signal: AbortSignal) =>
      lerCatalogo(
        (
          await api.get("/postos", {
            params: {
              referencia: filtros.referencia,
            },
            signal,
          })
        ).data,
        filtros.referencia,
      ),
    [filtros.referencia],
  );

  const consulta = useConsultaConta(carregar);
  const termo = busca.trim().toLocaleLowerCase("pt-BR");

  const postos =
    consulta.dados?.filter(
      (p) =>
        (todos || favoritos.ids.has(p.id)) &&
        (p.nome + " " + p.endereco).toLocaleLowerCase("pt-BR").includes(termo),
    ) ?? [];

  return (
    <Page
      title="Favoritos"
      subtitle="Seus postos salvos na conta, disponíveis nos seus dispositivos."
    >
      <AppButton
        label={
          todos ? "Mostrar meus favoritos" : "Explorar postos para favoritar"
        }
        secondary
        onPress={() => setTodos(!todos)}
      />

      <AppField label="Buscar posto" value={busca} onChangeText={setBusca} />

      <AvisoFavoritos />

      {consulta.erro ? (
        <Notice error>
          Não foi possível atualizar os postos. Tente novamente.
        </Notice>
      ) : null}

      <AppButton
        label="Atualizar favoritos"
        secondary
        disabled={
          favoritos.salvando || favoritos.carregando || consulta.loading
        }
        onPress={() => {
          favoritos.atualizar();
          consulta.atualizar();
        }}
      />

      {consulta.loading || favoritos.carregando ? (
        <Notice>Carregando favoritos...</Notice>
      ) : null}

      {!consulta.loading &&
      !consulta.erro &&
      favoritos.confirmado &&
      !postos.length ? (
        <Notice>
          Nenhum posto nesta seleção. Use “Explorar postos para favoritar” ou
          procure no Mapa e no Feed.
        </Notice>
      ) : null}

      {postos.map((posto) => (
        <Surface key={posto.id}>
          <CartaoPostoComFavorito
            posto={posto}
            selecionados={filtros.combustiveis}
            comparacao={consulta.dados ?? []}
            rotuloAcao={"Ver preços de " + posto.nome}
            onPress={() => setDetalhe(detalhe === posto.id ? null : posto.id)}
          />

          {detalhe === posto.id
            ? posto.combustiveis.map((oferta) => {
                const info = COMBUSTIVEIS.find(
                  (p) => p.codigo === oferta.codigo,
                )!;

                return (
                  <Notice key={oferta.codigo}>
                    {info.nome}:{" "}
                    {oferta.preco === null
                      ? "Sem preço informado"
                      : precoFormatado(oferta.preco) + " / " + info.unidade}
                    {oferta.preco !== null
                      ? " · " +
                        (oferta.autor_nome ?? "Autor não informado") +
                        " · " +
                        dataPublicacao(oferta.atualizado_em)
                      : ""}
                  </Notice>
                );
              })
            : null}
        </Surface>
      ))}
    </Page>
  );
}
