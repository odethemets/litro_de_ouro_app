import { useState } from "react";
import {
    Modal,
    Pressable,
    ScrollView,
    StyleSheet,
    Text,
    View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFiltrosPostos } from "../contexts/FiltrosPostosContext";
import {
    COMBUSTIVEIS,
    FILTROS_INICIAIS,
    alternarCombustivel,
    type FiltrosPostos,
} from "../services/catalogoPostos";
import { AppButton, useAppTheme } from "./design";

export function FiltrosPostosPainel({
  aberto,
  fechar,
  marcas,
}: {
  aberto: boolean;
  fechar(): void;
  marcas: string[];
}) {
  const { colors } = useAppTheme();
  const { filtros, aplicar } = useFiltrosPostos();
  const [rascunho, definir] = useState<FiltrosPostos>(filtros);
  function opcao(
    label: string,
    ativo: boolean,
    onPress: () => void,
    cor?: string,
  ) {
    return (
      <Pressable
        key={label}
        accessibilityRole="button"
        accessibilityLabel={label}
        accessibilityState={{ selected: ativo }}
        onPress={onPress}
        style={[
          styles.opcao,
          {
            backgroundColor: ativo ? colors.selection : colors.surface,
            borderColor: ativo ? colors.primary : colors.border,
          },
        ]}
      >
        {cor ? (
          <View
            style={{
              width: 12,
              height: 12,
              borderRadius: 6,
              backgroundColor: cor,
            }}
          />
        ) : null}
        <Text
          style={{
            color: colors.textPrimary,
            fontWeight: ativo ? "700" : "400",
          }}
        >
          {ativo ? "✓ " : ""}
          {label}
        </Text>
      </Pressable>
    );
  }
  const referencias = rascunho.combustiveis.length
    ? COMBUSTIVEIS.filter((p) => rascunho.combustiveis.includes(p.codigo))
    : COMBUSTIVEIS;
  return (
    <Modal
      visible={aberto}
      transparent
      animationType="slide"
      onRequestClose={fechar}
    >
      <View style={styles.fundo}>
        <SafeAreaView
          style={[styles.painel, { backgroundColor: colors.background }]}
        >
          <View style={styles.cabecalho}>
            <Text
              accessibilityRole="header"
              style={[styles.titulo, { color: colors.textPrimary }]}
            >
              Filtros e preferências
            </Text>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Fechar filtros"
              onPress={fechar}
              style={styles.fechar}
            >
              <Text style={{ color: colors.textPrimary, fontSize: 24 }}>×</Text>
            </Pressable>
          </View>
          <ScrollView contentContainerStyle={{ padding: 20, gap: 16 }}>
            <Text style={{ color: colors.textSecondary }}>
              Selecione os combustíveis. A oferta desconhecida aparece no modo
              Todos.
            </Text>
            <View style={styles.opcoes}>
              {opcao(
                "Todos os combustíveis",
                !rascunho.combustiveis.length,
                () => definir({ ...rascunho, combustiveis: [] }),
              )}
              {COMBUSTIVEIS.map((p) =>
                opcao(
                  p.nome,
                  rascunho.combustiveis.includes(p.codigo),
                  () => definir(alternarCombustivel(rascunho, p.codigo)),
                  p.cor,
                ),
              )}
            </View>
            <Text style={[styles.subtitulo, { color: colors.textPrimary }]}>
              Combustível de referência
            </Text>
            <Text style={{ color: colors.textSecondary }}>
              Define o preço principal e a comparação, mesmo com vários produtos
              selecionados.
            </Text>
            <View style={styles.opcoes}>
              {referencias.map((p) =>
                opcao(
                  "Referência: " + p.nome,
                  rascunho.referencia === p.codigo,
                  () => definir({ ...rascunho, referencia: p.codigo }),
                ),
              )}
            </View>
            <Text style={[styles.subtitulo, { color: colors.textPrimary }]}>
              Bandeira
            </Text>
            <View style={styles.opcoes}>
              {opcao("Todas as bandeiras", !rascunho.marca, () =>
                definir({ ...rascunho, marca: "" }),
              )}
              {[
                ...new Set([
                  "Shell",
                  "Petrobras",
                  "Ipiranga",
                  "Ale",
                  ...marcas,
                  ...(rascunho.marca && rascunho.marca !== "nao_informada"
                    ? [rascunho.marca]
                    : []),
                ]),
              ]
                .sort()
                .map((m) =>
                  opcao(m, rascunho.marca === m, () =>
                    definir({ ...rascunho, marca: m }),
                  ),
                )}
              {opcao(
                "Marca não informada",
                rascunho.marca === "nao_informada",
                () => definir({ ...rascunho, marca: "nao_informada" }),
              )}
            </View>
            <Text style={[styles.subtitulo, { color: colors.textPrimary }]}>
              Ordenação
            </Text>
            <View style={styles.opcoes}>
              {opcao("Mais próximos", rascunho.ordenar === "distancia", () =>
                definir({ ...rascunho, ordenar: "distancia" }),
              )}
              {opcao(
                "Menor preço da referência",
                rascunho.ordenar === "preco",
                () => definir({ ...rascunho, ordenar: "preco" }),
              )}
            </View>
          </ScrollView>
          <View style={[styles.rodape, { borderTopColor: colors.border }]}>
            <AppButton
              label="Limpar filtros"
              secondary
              onPress={() => definir(FILTROS_INICIAIS)}
            />
            <AppButton
              label="Aplicar filtros"
              onPress={() => {
                aplicar(rascunho);
                fechar();
              }}
            />
          </View>
        </SafeAreaView>
      </View>
    </Modal>
  );
}
export function LegendaCombustiveis() {
  const { colors } = useAppTheme();
  return (
    <View style={{ gap: 12 }}>
      <Text style={[styles.subtitulo, { color: colors.textPrimary }]}>
        Legenda dos combustíveis
      </Text>
      {COMBUSTIVEIS.map((p) => (
        <View key={p.codigo} style={styles.linha}>
          <View
            style={{
              backgroundColor: p.cor,
              width: 22,
              height: 8,
              borderRadius: 4,
            }}
          />
          <Text style={{ color: colors.textPrimary }}>
            {p.codigo === "recarga_eletrica" ? "⚡ " : ""}
            {p.nome} · {p.unidade}
          </Text>
        </View>
      ))}
      <Text style={{ color: colors.textSecondary }}>
        As barrinhas indicam oferta confirmada dos produtos selecionados. Sem
        barrinha: oferta não confirmada para a seleção. O preço central segue a
        referência indicada.
      </Text>
      <Text style={{ color: colors.textSecondary }}>
        Preço em verde, mostarda ou vermelho: faixa menor, intermediária ou
        maior entre os valores recentes desta consulta, do mesmo combustível. A
        faixa é calculada por terços do intervalo mínimo–máximo. Registros de
        até três dias entram na comparação; dados sem atualização válida ficam
        neutros.
      </Text>
    </View>
  );
}
const styles = StyleSheet.create({
  fundo: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,.4)",
    justifyContent: "flex-end",
    alignItems: "center",
  },
  painel: {
    width: "100%",
    maxWidth: 640,
    maxHeight: "94%",
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    overflow: "hidden",
  },
  cabecalho: {
    paddingLeft: 20,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  titulo: { fontSize: 21, fontWeight: "800", flex: 1 },
  subtitulo: { fontSize: 18, fontWeight: "700" },
  fechar: {
    width: 56,
    height: 56,
    alignItems: "center",
    justifyContent: "center",
  },
  opcoes: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  opcao: {
    minHeight: 48,
    padding: 12,
    borderWidth: 1,
    borderRadius: 12,
    flexDirection: "row",
    gap: 6,
    alignItems: "center",
    flexShrink: 1,
  },
  rodape: { padding: 16, borderTopWidth: 1, gap: 10 },
  linha: { flexDirection: "row", alignItems: "center", gap: 10 },
});
