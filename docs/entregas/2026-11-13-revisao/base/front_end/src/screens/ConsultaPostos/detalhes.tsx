import { Linking, Text, View } from "react-native";

import {
  AppButton,
  Notice,
  useAppTheme,
} from "../../components/design";
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

export function DetalhesPostoConsulta({
  posto,
  referencia,
  usuario,
  erroRota,
  onErroRota,
  onRegistrar,
  onVoltar,
  onAtualizar,
}: Props) {
  const { colors } = useAppTheme();
  const produtosPermitidos = produtosCadastro(posto);

  return (
    <View style={{ padding: 20, gap: 16 }}>
      <Text
        accessibilityRole="header"
        style={[
          styles.titulo,
          { color: colors.textPrimary },
        ]}
      >
        {posto.nome}
      </Text>

      <BotaoFavorito
        postoId={posto.id}
        nome={posto.nome}
      />

      <Text style={{ color: colors.textSecondary }}>
        {posto.marca ?? "Marca não informada"}
        {" · "}
        {posto.endereco}
      </Text>

      {posto.bairro ? (
        <Text style={{ color: colors.textSecondary }}>
          {posto.bairro}
        </Text>
      ) : null}

      <Text style={{ color: colors.textPrimary }}>
        Referência: {produto(referencia).nome}
      </Text>

      <AppButton
        label="Traçar rota"
        secondary
        onPress={() => {
          const origem = usuario
            ? "&origin=" +
              encodeURIComponent(
                usuario.lat + "," + usuario.lon,
              )
            : "";

          const destino = encodeURIComponent(
            posto.latitude + "," + posto.longitude,
          );

          const url =
            "https://www.google.com/maps/dir/?api=1&destination=" +
            destino +
            origem +
            "&travelmode=driving";

          void Linking.openURL(url).catch(() =>
            onErroRota(
              "Não foi possível abrir o aplicativo de mapas.",
            ),
          );
        }}
      />

      {erroRota ? (
        <Notice error>{erroRota}</Notice>
      ) : null}

      <AppButton
        label="Registrar novo preço"
        onPress={() => onRegistrar(referencia)}
      />

      {posto.combustiveis.map((oferta) => {
        const info = produto(oferta.codigo);

        const podeRegistrar = produtosPermitidos.some(
          (item) => item.codigo === oferta.codigo,
        );

        return (
          <View
            key={oferta.codigo}
            style={[
              styles.cartao,
              {
                backgroundColor: colors.surface,
                borderColor: colors.border,
                gap: 6,
              },
            ]}
          >
            <Text
              style={[
                styles.nome,
                { color: colors.textPrimary },
              ]}
            >
              {oferta.codigo === "recarga_eletrica"
                ? "⚡ "
                : ""}
              {info.nome}
            </Text>

            <Text style={{ color: colors.textSecondary }}>
              Oferta:{" "}
              {oferta.disponivel === null
                ? "não confirmada"
                : oferta.disponivel
                  ? "confirmada"
                  : "não disponível"}
              {oferta.origem ? " · " + oferta.origem : ""}
            </Text>

            <Text
              style={[
                styles.preco,
                { color: colors.textPrimary },
              ]}
            >
              {oferta.preco === null
                ? "Sem preço informado"
                : precoFormatado(oferta.preco) +
                  " / " +
                  info.unidade}
            </Text>

            {oferta.preco !== null ? (
              <Text style={{ color: colors.textSecondary }}>
                {dataPublicacao(oferta.atualizado_em)}
                {oferta.autor_nome
                  ? " · " + oferta.autor_nome
                  : ""}
              </Text>
            ) : null}

            {oferta.preco !== null && oferta.registo_id ? (
              <VotarPreco key={oferta.registo_id} registoId={oferta.registo_id} nome={info.nome} />
            ) : null}

            {podeRegistrar && oferta.disponivel === null ? (
              <ConfirmarOferta key={posto.id + oferta.codigo} postoId={posto.id} codigo={oferta.codigo}
                nome={info.nome} onAtualizar={onAtualizar} />
            ) : null}

            {podeRegistrar ? (
              <AppButton
                label={"Informar preço de " + info.nome}
                secondary
                onPress={() =>
                  onRegistrar(oferta.codigo)
                }
              />
            ) : null}
          </View>
        );
      })}

      <AppButton
        label="Voltar à lista de postos"
        secondary
        onPress={onVoltar}
      />
    </View>
  );
}
