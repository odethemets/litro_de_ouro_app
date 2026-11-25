import Ionicons from "@expo/vector-icons/Ionicons";
import { useState } from "react";
import { Pressable, Text, View } from "react-native";
import {
  classificarPreco,
  descricaoPreco,
  ofertaReferencia,
  produto,
  rotuloPreco,
  segmentosPosto,
  type Combustivel,
  type PostoCatalogo,
} from "../services/catalogoPostos";
import { useAppTheme } from "./design";

export function CartaoPosto({
  posto,
  selecionados = [],
  comparacao = [],
  selecionado = false,
  rotuloAcao,
  onPress,
}: {
  posto: PostoCatalogo;
  selecionados?: Combustivel[];
  comparacao?: PostoCatalogo[];
  selecionado?: boolean;
  rotuloAcao?: string;
  onPress(): void;
}) {
  const { colors, activeTheme } = useAppTheme();
  const [foco, definirFoco] = useState(false);

  const ref = ofertaReferencia(posto);
  const info = produto(posto.combustivel_referencia);
  const ofertas = segmentosPosto(posto, selecionados);
  const faixa = classificarPreco(posto, comparacao);

  const corPreco =
    faixa.cor === "#166534"
      ? colors.success
      : faixa.cor === "#B42318"
        ? colors.danger
        : faixa.cor === "#8A6500"
          ? activeTheme === "dark"
            ? "#F5D56E"
            : faixa.cor
          : colors.textPrimary;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={rotuloAcao ?? posto.nome + ", " + rotuloPreco(posto)}
      accessibilityState={{ selected: selecionado }}
      onPress={onPress}
      onFocus={() => definirFoco(true)}
      onBlur={() => definirFoco(false)}
      style={({ pressed }) => ({
        borderWidth: 2,
        padding: 16,
        borderRadius: 18,
        minHeight: 64,
        backgroundColor: colors.surface,
        borderColor: selecionado || foco ? colors.focus : colors.border,
        opacity: pressed ? 0.85 : 1,
      })}
    >
      <View
        style={{
          flexDirection: "row",
          gap: 12,
          alignItems: "center",
        }}
      >
        <View style={{ flex: 1, gap: 6 }}>
          <View
            style={{
              flexDirection: "row",
              gap: 6,
              alignItems: "center",
            }}
          >
            {posto.tipo_posto === "Eletroposto" ? (
              <Ionicons
                name="flash"
                size={20}
                color="#C026D3"
                accessible={false}
              />
            ) : null}

            <Text
              style={{
                fontSize: 17,
                fontWeight: "700",
                flexShrink: 1,
                color: colors.textPrimary,
              }}
            >
              {posto.nome}
            </Text>
          </View>

          <Text style={{ color: colors.textSecondary }}>
            {posto.marca ?? "Marca não informada"}
          </Text>
        </View>

        <View
          style={{
            alignItems: "flex-end",
            maxWidth: "45%",
          }}
        >
          <Text
            style={{
              fontSize: 18,
              fontWeight: "800",
              flexShrink: 1,
              color: corPreco,
            }}
          >
            {rotuloPreco(posto)}
          </Text>

          {posto.preco_referencia !== null ? (
            <Text style={{ color: colors.textSecondary }}>/{info.unidade}</Text>
          ) : null}
        </View>
      </View>

      <Text
        style={{
          color: colors.textSecondary,
          marginTop: 8,
        }}
      >
        {info.nome}
        {" · "}
        {posto.distancia_m !== undefined
          ? (posto.distancia_m / 1000).toFixed(1).replace(".", ",") + " km · "
          : ""}
        {posto.endereco}
      </Text>

      <View
        accessibilityLabel={
          ofertas.length
            ? "Oferta confirmada: " + ofertas.map((o) => o.nome).join(", ")
            : "Oferta não confirmada para a seleção"
        }
        style={{
          flexDirection: "row",
          flexWrap: "wrap",
          gap: 3,
          marginTop: 10,
        }}
      >
        {ofertas.length ? (
          ofertas.map((o) => (
            <View
              key={o.codigo}
              style={{
                backgroundColor: o.cor,
                height: 5,
                width: 28,
                borderRadius: 4,
              }}
            />
          ))
        ) : (
          <Text
            style={{
              color: colors.textSecondary,
              fontSize: 12,
            }}
          >
            Oferta não confirmada
          </Text>
        )}
      </View>

      {posto.preco_referencia !== null ? (
        <>
          <Text
            style={{
              color: colors.textSecondary,
              fontSize: 12,
              marginTop: 8,
            }}
          >
            {descricaoPreco(ref)}
          </Text>

          <View
            style={{
              flexDirection: "row",
              alignItems: "center",
              gap: 6,
              marginTop: 6,
            }}
          >
            <View
              style={{
                width: 8,
                height: 8,
                borderRadius: 4,
                backgroundColor: corPreco,
              }}
            />

            <Text
              style={{
                color: colors.textSecondary,
                fontSize: 12,
              }}
            >
              {faixa.texto}
            </Text>
          </View>
        </>
      ) : null}
    </Pressable>
  );
}
