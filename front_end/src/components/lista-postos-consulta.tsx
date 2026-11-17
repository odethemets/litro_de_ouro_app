import { useMemo, type ReactNode } from "react";
import {
  ActivityIndicator,
  Keyboard,
  Text,
  View,
} from "react-native";

import type { PostoCatalogo } from "../services/catalogoPostos";
import {
  filtrarPostosPorNome,
  normalizarBuscaNome,
  postoMaisProximo,
} from "../services/buscaPostosNome";
import {
  AppButton,
  AppField,
  Notice,
  useAppTheme,
} from "./design";

interface Props {
  postos: PostoCatalogo[];
  buscaPorNome: boolean;
  busca: string;
  onBuscar(texto: string): void;
  carregando: boolean;
  erro: string;
  gpsDisponivel: boolean;
  onEscolher(posto: PostoCatalogo): void;
  onRecarregar(): void;
  onFiltros(): void;
  renderPosto(posto: PostoCatalogo): ReactNode;
}

export function ListaPostosConsulta({
  postos,
  buscaPorNome,
  busca,
  onBuscar,
  carregando,
  erro,
  gpsDisponivel,
  onEscolher,
  onRecarregar,
  onFiltros,
  renderPosto,
}: Props) {
  const { colors } = useAppTheme();

  const termo = buscaPorNome
    ? normalizarBuscaNome(busca)
    : "";

  const visiveis = useMemo(
    () => filtrarPostosPorNome(postos, termo),
    [postos, termo],
  );

  const proximo = useMemo(
    () => postoMaisProximo(visiveis),
    [visiveis],
  );

  return (
    <View style={{ padding: 16, gap: 12 }}>
      <Text
        accessibilityRole="header"
        style={{
          fontSize: 23,
          fontWeight: "800",
          color: colors.textPrimary,
        }}
      >
        Postos na região
      </Text>

      {buscaPorNome ? (
        <View style={{ gap: 10 }}>
          <AppField
            label="Buscar posto pelo nome"
            placeholder="Ex.: Santa Júlia"
            value={busca}
            onChangeText={onBuscar}
            maxLength={120}
            autoCapitalize="none"
            autoCorrect={false}
            returnKeyType="search"
            onSubmitEditing={() => Keyboard.dismiss()}
          />

          <Notice>
            Busca nos postos dos filtros e da região atuais.
          </Notice>

          {busca.length > 0 ? (
            <AppButton
              label="Limpar busca por nome"
              secondary
              onPress={() => onBuscar("")}
            />
          ) : null}
        </View>
      ) : null}

      <Text
        accessibilityLiveRegion="polite"
        style={{ color: colors.textSecondary }}
      >
        {termo
          ? `Exibindo ${visiveis.length} de ${postos.length} postos desta consulta`
          : `${postos.length} postos nesta consulta`}
      </Text>

      <AppButton
        label="Destacar o posto mais próximo"
        secondary
        disabled={!gpsDisponivel || proximo === null}
        onPress={() => {
          if (proximo) onEscolher(proximo);
        }}
      />

      {carregando ? (
        <ActivityIndicator
          accessibilityLabel="Atualizando postos"
          color={colors.textPrimary}
        />
      ) : null}

      {erro ? (
        <>
          <Notice error>{erro}</Notice>

          <AppButton
            label="Tentar atualizar os postos"
            onPress={onRecarregar}
          />
        </>
      ) : null}

      {!carregando && !erro && postos.length === 0 ? (
        <>
          <Notice>
            Nenhum posto corresponde à consulta. Ofertas
            desconhecidas ficam disponíveis no filtro Todos
            os combustíveis.
          </Notice>

          <AppButton
            label="Revisar filtros"
            onPress={onFiltros}
          />
        </>
      ) : null}

      {!carregando &&
      !erro &&
      postos.length > 0 &&
      visiveis.length === 0 ? (
        <Notice>
          Nenhum posto encontrado com esse nome. Tente outro
          termo ou limpe a busca.
        </Notice>
      ) : null}

      {visiveis.map(renderPosto)}
    </View>
  );
}