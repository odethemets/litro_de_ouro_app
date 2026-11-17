import type { ReactNode } from "react";
import { FlatList, Text, View, type ListRenderItem } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { design } from "../theme/design";
import { AppButton, Notice, useAppTheme } from "./design";

interface Props<T> {
  titulo: string;
  subtitulo: string;
  itens: T[] | null;
  carregando: boolean;
  erro: boolean;
  atualizar(): void;
  atualizarLabel: string;
  vazio: string;
  rodape: string;
  renderItem: ListRenderItem<T>;
  keyExtractor(item: T, index: number): string;
  children?: ReactNode;
}

function Separador() {
  return <View style={{ height: 12 }} />;
}

export function ListaConta<T>({
  titulo,
  subtitulo,
  itens,
  carregando,
  erro,
  atualizar,
  atualizarLabel,
  vazio,
  rodape,
  renderItem,
  keyExtractor,
  children,
}: Props<T>) {
  const { colors } = useAppTheme();

  return (
    <SafeAreaView
      edges={["top", "left", "right"]}
      style={{ flex: 1, backgroundColor: colors.background }}
    >
      <FlatList
        style={{ flex: 1 }}
        data={itens ?? []}
        renderItem={renderItem}
        keyExtractor={keyExtractor}
        ItemSeparatorComponent={Separador}
        initialNumToRender={8}
        maxToRenderPerBatch={12}
        windowSize={5}
        refreshing={carregando}
        onRefresh={atualizar}
        contentContainerStyle={{
          flexGrow: 1,
          padding: 24,
          width: "100%",
          maxWidth: design.content,
          alignSelf: "center",
        }}
        ListHeaderComponent={
          <View style={{ gap: 16, marginBottom: 20 }}>
            <Text
              accessibilityRole="header"
              style={{
                color: colors.textPrimary,
                fontSize: 28,
                fontWeight: "800",
              }}
            >
              {titulo}
            </Text>

            <Notice>{subtitulo}</Notice>

            {children}

            <AppButton
              label={atualizarLabel}
              secondary
              disabled={carregando}
              onPress={atualizar}
            />

            <View accessibilityLiveRegion="polite" aria-live="polite">
              {carregando ? <Notice>Atualizando dados...</Notice> : null}
            </View>

            {erro ? (
              <Notice error>
                Não foi possível atualizar esta lista. Tente novamente.
                {itens !== null ? " Exibindo os últimos dados recebidos." : ""}
              </Notice>
            ) : null}
          </View>
        }
        ListEmptyComponent={
          !carregando && !erro && itens !== null ? (
            <Notice>{vazio}</Notice>
          ) : undefined
        }
        ListFooterComponent={
          <View style={{ marginTop: 20, paddingBottom: 16 }}>
            <Notice>{rodape}</Notice>
          </View>
        }
      />
    </SafeAreaView>
  );
}
