import Ionicons from "@expo/vector-icons/Ionicons";
import type { ComponentProps } from "react";
import { Pressable, Text, View } from "react-native";

import { useAuth } from "../contexts/AuthContext";
import { useFavoritos } from "../contexts/FavoritosContext";
import { CartaoPosto } from "./cartao-posto";
import { AppButton, Notice, useAppTheme } from "./design";

export function BotaoFavorito({
  postoId,
  nome,
}: {
  postoId: number;
  nome: string;
}) {
  const { status, openAuth } = useAuth();
  const favoritos = useFavoritos();
  const { colors } = useAppTheme();

  const autenticado = status === "AUTHENTICATED";
  const salvo = favoritos.ids.has(postoId);

  const label = !autenticado
    ? "Entrar para favoritar " + nome
    : !favoritos.confirmado
      ? "Atualizar favoritos para " + nome
      : (salvo ? "Remover dos favoritos: " : "Favoritar: ") + nome;

  const ocupado = favoritos.carregando || favoritos.salvando;

  const texto = !autenticado
    ? "Entrar para favoritar"
    : favoritos.carregando
      ? "Carregando favoritos..."
      : favoritos.salvando
        ? "Salvando..."
        : !favoritos.confirmado
          ? "Atualizar favoritos"
          : salvo
            ? "Favoritado — remover"
            : "Favoritar posto";

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{
        disabled: ocupado,
        selected: salvo,
      }}
      disabled={ocupado}
      onPress={() => {
        if (!autenticado) {
          openAuth("Login");
        } else if (!favoritos.confirmado) {
          favoritos.atualizar();
        } else {
          void favoritos.alternar(postoId);
        }
      }}
      style={({ pressed }) => ({
        flexDirection: "row",
        gap: 8,
        alignItems: "center",
        minHeight: 48,
        padding: 12,
        borderRadius: 12,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.surface,
        opacity: pressed || ocupado ? 0.6 : 1,
      })}
    >
      <Ionicons
        name={salvo ? "star" : "star-outline"}
        size={22}
        color={colors.textPrimary}
        accessible={false}
      />

      <Text style={{ color: colors.textPrimary, flexShrink: 1 }}>{texto}</Text>
    </Pressable>
  );
}

export function CartaoPostoComFavorito(
  props: ComponentProps<typeof CartaoPosto>,
) {
  return (
    <View style={{ gap: 6 }}>
      <CartaoPosto {...props} />
      <BotaoFavorito postoId={props.posto.id} nome={props.posto.nome} />
    </View>
  );
}

export function AvisoFavoritos() {
  const { erro, atualizar, carregando, salvando } = useFavoritos();

  return erro ? (
    <>
      <Notice error>{erro}</Notice>

      <AppButton
        label="Tentar atualizar favoritos"
        secondary
        disabled={carregando || salvando}
        onPress={atualizar}
      />
    </>
  ) : null;
}
