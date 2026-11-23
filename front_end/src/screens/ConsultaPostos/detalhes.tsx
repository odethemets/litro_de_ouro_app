import Ionicons from "@expo/vector-icons/Ionicons";
import { useState } from "react";
import { Linking, Pressable, Text, View } from "react-native";

import { ConfirmarOferta } from "../../components/confirmar-oferta";
import { AppButton, Notice, useAppTheme } from "../../components/design";
import { BotaoFavorito } from "../../components/favoritos";
import type { PosicaoUsuario } from "../../components/mapa/tipos";
import { SolicitarServico } from "../../components/servicos/solicitar-servicos";
import { VotarPreco } from "../../components/votar-preco";
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

// Mantém a referência em destaque e permite expandir os demais produtos.
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
  const permitidos = produtosCadastro(posto);

  const ofertas = [...posto.combustiveis].sort(
    (a, b) => Number(b.codigo === referencia) - Number(a.codigo === referencia),
  );

  // Usa a posição pessoal somente quando ela existe.
  function tracarRota() {
    onErroRota("");

    const origem = usuario
      ? "&origin=" + encodeURIComponent(usuario.lat + "," + usuario.lon)
      : "";

    const destino = encodeURIComponent(posto.latitude + "," + posto.longitude);

    void Linking.openURL(
      "https://www.google.com/maps/dir/?api=1&destination=" +
        destino +
        origem +
        "&travelmode=driving",
    ).catch(() => onErroRota("Não foi possível abrir o aplicativo de mapas."));
  }

  return (
    <View
      style={{
        padding: 20,
        gap: 16,
        minWidth: 0,
      }}
    >
      <Text
        accessibilityRole="header"
        style={[styles.titulo, { color: colors.textPrimary }]}
      >
        {posto.nome}
      </Text>

      <BotaoFavorito postoId={posto.id} nome={posto.nome} />

      <Text
        style={{
          color: colors.textSecondary,
          lineHeight: 22,
        }}
      >
        {posto.marca ?? "Marca não informada"}
        {" · "}
        {posto.endereco}
      </Text>

      {posto.bairro ? (
        <Text
          style={{
            color: colors.textSecondary,
          }}
        >
          {posto.bairro}
        </Text>
      ) : null}

      <AppButton label="Traçar rota" secondary onPress={tracarRota} />

      {erroRota ? <Notice error>{erroRota}</Notice> : null}

      <View style={{ gap: 6 }}>
        <Text
          accessibilityRole="header"
          style={{
            color: colors.textPrimary,
            fontSize: 19,
            fontWeight: "700",
          }}
        >
          Combustíveis e preços
        </Text>

        <Notice>
          Referência do mapa: {produto(referencia).nome}. Cada valor mantém sua
          própria unidade.
        </Notice>
      </View>

      {ofertas.map((oferta) => (
        <CartaoCombustivel
          key={JSON.stringify([
            posto.id,
            oferta.codigo,
            oferta.codigo === referencia,
          ])}
          postoId={posto.id}
          oferta={oferta}
          referencia={oferta.codigo === referencia}
          podeRegistrar={permitidos.some(
            (item) => item.codigo === oferta.codigo,
          )}
          podeSugerir={
            posto.tipo_posto !== "Eletroposto" ||
            oferta.codigo === "recarga_eletrica"
          }
          onAtualizar={onAtualizar}
          onRegistrar={() => onRegistrar(oferta.codigo)}
        />
      ))}

      <AppButton
        label="Voltar à lista de postos"
        secondary
        onPress={onVoltar}
      />
    </View>
  );
}

interface PropsCartao {
  postoId: number;
  oferta: PostoCatalogo["combustiveis"][number];
  referencia: boolean;
  podeRegistrar: boolean;
  podeSugerir: boolean;
  onAtualizar(): void;
  onRegistrar(): void;
}

// Os controles secundários só são montados ao expandir o cartão.
function CartaoCombustivel({
  postoId,
  oferta,
  referencia,
  podeRegistrar,
  podeSugerir,
  onAtualizar,
  onRegistrar,
}: PropsCartao) {
  const { colors } = useAppTheme();
  const [aberto, setAberto] = useState(referencia);
  const [focado, setFocado] = useState(false);
  const info = produto(oferta.codigo);

  const disponibilidade =
    oferta.disponivel === null
      ? "Oferta não confirmada"
      : oferta.disponivel
        ? "Disponibilidade confirmada"
        : "Não disponível";

  return (
    <View
      style={[
        styles.cartao,
        {
          backgroundColor: colors.surface,
          borderColor: colors.border,
          gap: 12,
          minWidth: 0,
        },
      ]}
    >
      <View
        style={{
          flexDirection: "row",
          gap: 10,
          alignItems: "center",
        }}
      >
        <View
          accessible={false}
          style={{
            width: 6,
            height: 32,
            borderRadius: 3,
            backgroundColor: info.cor,
          }}
        />

        <Text
          style={[
            styles.nome,
            {
              color: colors.textPrimary,
              flex: 1,
            },
          ]}
        >
          {oferta.codigo === "recarga_eletrica" ? "⚡ " : ""}
          {info.nome}
        </Text>
      </View>

      {referencia ? (
        <Text
          style={{
            color: colors.textSecondary,
            fontWeight: "700",
          }}
        >
          Referência do mapa
        </Text>
      ) : null}

      <Text style={[styles.preco, { color: colors.textPrimary }]}>
        {oferta.preco === null
          ? "Sem preço informado"
          : precoFormatado(oferta.preco) + " / " + info.unidade}
      </Text>

      <Text
        style={{
          color: colors.textSecondary,
        }}
      >
        {disponibilidade}
      </Text>

      {oferta.preco !== null ? (
        <Text
          style={{
            color: colors.textSecondary,
            lineHeight: 22,
          }}
        >
          {oferta.autor_nome
            ? "Informado por " + oferta.autor_nome + " · "
            : ""}
          {dataPublicacao(oferta.atualizado_em)}
        </Text>
      ) : null}

      <Pressable
        accessibilityRole="button"
        accessibilityLabel={
          (aberto ? "Ocultar" : "Ver") + " detalhes de " + info.nome
        }
        accessibilityState={{
          expanded: aberto,
        }}
        onPress={() => setAberto((valor) => !valor)}
        onFocus={() => setFocado(true)}
        onBlur={() => setFocado(false)}
        style={({ pressed }) => ({
          minHeight: 48,
          borderWidth: 1,
          borderColor: focado ? colors.textPrimary : colors.border,
          borderRadius: 14,
          padding: 12,
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          backgroundColor: colors.surface,
          opacity: pressed ? 0.75 : 1,
        })}
      >
        <Text
          style={{
            color: colors.textPrimary,
            fontWeight: "600",
            flexShrink: 1,
          }}
        >
          {aberto ? "Ocultar detalhes" : "Ver detalhes e contribuir"}
        </Text>

        <Ionicons
          name={aberto ? "chevron-up" : "chevron-down"}
          size={20}
          color={colors.textPrimary}
          accessible={false}
        />
      </Pressable>

      {aberto ? (
        <View style={{ gap: 12 }}>
          {podeRegistrar ? (
            <AppButton
              label="Informar novo preço"
              secondary={!referencia}
              onPress={onRegistrar}
            />
          ) : null}

          {podeRegistrar && oferta.disponivel === null ? (
            <ConfirmarOferta
              postoId={postoId}
              codigo={oferta.codigo}
              nome={info.nome}
              onAtualizar={onAtualizar}
            />
          ) : null}

          {podeSugerir && oferta.disponivel !== true ? (
            <SolicitarServico postoId={postoId} codigo={oferta.codigo} />
          ) : null}

          {oferta.preco !== null && oferta.registo_id ? (
            <VotarPreco registoId={oferta.registo_id} nome={info.nome} />
          ) : null}
        </View>
      ) : null}
    </View>
  );
}
