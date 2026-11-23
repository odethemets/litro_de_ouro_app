import { useState } from "react";
import { ActivityIndicator, Modal, ScrollView, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import type { PostoCatalogo } from "../../services/catalogoPostos";
import { CartaoPosto } from "../cartao-posto";
import { AppButton, AppField, Notice, useAppTheme } from "../design";

export function SeletorPosto({
  aberto,
  postos,
  postoId,
  carregando,
  fechar,
  escolher,
}: {
  aberto: boolean;
  postos: PostoCatalogo[];
  postoId: number | null;
  carregando: boolean;
  fechar(): void;
  escolher(posto: PostoCatalogo): void;
}) {
  const { colors } = useAppTheme();
  const [busca, setBusca] = useState("");

  const encontrados = postos.filter((p) =>
    (p.nome + " " + p.endereco + " " + (p.marca ?? ""))
      .toLocaleLowerCase("pt-BR")
      .includes(busca.trim().toLocaleLowerCase("pt-BR")),
  );

  return (
    <Modal
      visible={aberto}
      transparent
      animationType="slide"
      onRequestClose={fechar}
    >
      <View
        style={{
          flex: 1,
          backgroundColor: "rgba(0,0,0,.45)",
          justifyContent: "flex-end",
          alignItems: "center",
        }}
      >
        <SafeAreaView
          edges={["left", "right", "bottom"]}
          style={{
            width: "100%",
            maxWidth: 780,
            maxHeight: "92%",
            backgroundColor: colors.background,
            borderTopLeftRadius: 24,
            borderTopRightRadius: 24,
          }}
        >
          <View style={{ padding: 16, gap: 12 }}>
            <Text
              accessibilityRole="header"
              style={{
                color: colors.textPrimary,
                fontSize: 23,
                fontWeight: "800",
              }}
            >
              Escolher posto
            </Text>

            <AppField
              label="Buscar posto, endereço ou bandeira"
              value={busca}
              onChangeText={setBusca}
              placeholder="Digite para buscar"
            />

            <Notice>
              {encontrados.length} postos no catálogo carregado. A seleção não
              altera os filtros do Mapa e do Feed.
            </Notice>
          </View>

          <ScrollView
            keyboardShouldPersistTaps="handled"
            contentContainerStyle={{
              padding: 16,
              gap: 12,
            }}
          >
            {carregando ? (
              <ActivityIndicator
                accessibilityLabel="Carregando postos para cadastro"
                color={colors.textPrimary}
              />
            ) : null}

            {!encontrados.length ? (
              <Notice>Nenhum posto corresponde à busca.</Notice>
            ) : (
              encontrados.map((p) => (
                <CartaoPosto
                  key={p.id}
                  posto={p}
                  selecionado={p.id === postoId}
                  rotuloAcao={"Selecionar " + p.nome}
                  onPress={() => escolher(p)}
                />
              ))
            )}
          </ScrollView>

          <View style={{ padding: 16 }}>
            <AppButton
              label="Fechar seleção de posto"
              secondary
              onPress={fechar}
            />
          </View>
        </SafeAreaView>
      </View>
    </Modal>
  );
}
