import {
  useFocusEffect,
  useNavigation,
  type NavigationProp,
} from "@react-navigation/native";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  Text,
  View,
  useWindowDimensions,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { AvaliacaoApp } from "../../components/avaliacao-app";
import { AtalhoBuscaMapa } from "../../components/busca-no-mapa";
import { AppButton, useAppTheme } from "../../components/design";
import {
  AvisoFavoritos,
  CartaoPostoComFavorito,
} from "../../components/favoritos";
import {
  FiltrosPostosPainel,
  LegendaCombustiveis,
} from "../../components/filtros-postos";
import { ListaPostosConsulta } from "../../components/lista-postos-consulta";
import MapaLeaflet from "../../components/mapa/MapaLeaflet";
import type { MapaLeafletHandle } from "../../components/mapa/tipos";
import { useAuth } from "../../contexts/AuthContext";
import { useFiltrosPostos } from "../../contexts/FiltrosPostosContext";
import type { Abas } from "../../routes/app.routes";
import {
  classificarPreco,
  ofertaReferencia,
  produto,
  rotuloPreco,
  segmentosPosto,
  type PostoCatalogo,
} from "../../services/catalogoPostos";
import { registrarPostoVisto } from "../../services/historicoVistos";
import { design } from "../../theme/design";
import { zoomLocalizacao } from "../../utils/precisaoGps";
import { DetalhesPostoConsulta } from "./detalhes";
import { BotaoConsulta, styles } from "./layout";

// Coordena Mapa/Feed com catálogo e filtros compartilhados.
export default function ConsultaPostos({
  modo = "mapa",
}: {
  modo?: "mapa" | "lista";
}) {
  const { colors } = useAppTheme();
  const navigation = useNavigation<NavigationProp<Abas>>();
  const { perfil } = useAuth();

  const {
    filtros,
    postos,
    marcas,
    usuario,
    avisoGps,
    erro,
    carregando,
    referenciaMapa,
    atualizarLocalizacao,
    recarregar,
  } = useFiltrosPostos();

  useEffect(() => {
    if (referenciaMapa) {
      mapa.current?.centralizar(
        referenciaMapa.lat,
        referenciaMapa.lon,
        zoomLocalizacao(referenciaMapa),
      );
    }
  }, [referenciaMapa]);

  useFocusEffect(
    useCallback(() => {
      recarregar();
    }, [recarregar]),
  );

  const desktop = useWindowDimensions().width >= design.desktop;
  const mapa = useRef<MapaLeafletHandle>(null);

  const [filtrosAbertos, abrirFiltros] = useState(false);
  const [listaAberta, abrirLista] = useState(false);
  const [legendaAberta, abrirLegenda] = useState(false);
  const [selecionado, selecionar] = useState<number | null>(null);
  const [painelDesktop, definirPainelDesktop] = useState(true);
  const [erroRota, definirErroRota] = useState("");
  const [buscaNome, definirBuscaNome] = useState("");

  const posto = postos.find((p) => p.id === selecionado);
  const referencia = produto(filtros.referencia);

  useEffect(() => {
    if (usuario) {
      mapa.current?.centralizar(usuario.lat, usuario.lon, 14);
    }
  }, [usuario]);

  const pinos = useMemo(
    () =>
      postos.map((p) => ({
        id: p.id,
        lat: p.latitude,
        lon: p.longitude,
        cor: classificarPreco(p, postos).cor,
        rotulo:
          p.preco_referencia === null
            ? ofertaReferencia(p).disponivel === true
              ? "Sem preço"
              : "Ver preços"
            : rotuloPreco(p),
        segmentos: segmentosPosto(p, filtros.combustiveis).map((s) => s.cor),
        eletrico:
          p.tipo_posto === "Eletroposto" ||
          p.combustiveis.some(
            (o) => o.codigo === "recarga_eletrica" && o.disponivel === true,
          ),
        selecionado: p.id === selecionado,
        nome: p.nome,
      })),
    [postos, filtros.combustiveis, selecionado],
  );

  // Seleciona o posto e registra a visualização da conta atual.
  function escolher(p: PostoCatalogo) {
    definirErroRota("");
    selecionar(p.id);
    abrirLista(false);
    definirPainelDesktop(true);

    mapa.current?.centralizar(p.latitude, p.longitude, 17);

    void registrarPostoVisto(
      {
        id: p.id,
        nome: p.nome,
        endereco: p.endereco,
      },
      perfil?.id,
    );
  }

  function cartao(p: PostoCatalogo) {
    return (
      <CartaoPostoComFavorito
        key={p.id}
        posto={p}
        selecionados={filtros.combustiveis}
        comparacao={postos}
        selecionado={p.id === selecionado}
        onPress={() => escolher(p)}
      />
    );
  }

  function abrirCadastro(
    p: PostoCatalogo,
    combustivel: typeof filtros.referencia,
    solicitacao: number,
  ) {
    abrirLista(false);
    selecionar(null);

    navigation.navigate("Adicionar", {
      postoId: p.id,
      combustivel,
      solicitacao,
    });
  }

  // A busca por nome permanece habilitada apenas no Feed.
  function lista() {
    return (
      <ListaPostosConsulta
        postos={postos}
        buscaPorNome={modo === "lista"}
        busca={buscaNome}
        onBuscar={definirBuscaNome}
        carregando={carregando}
        erro={erro}
        gpsDisponivel={!!usuario}
        onEscolher={escolher}
        onRecarregar={recarregar}
        onFiltros={() => abrirFiltros(true)}
        renderPosto={cartao}
      />
    );
  }

  function detalhes() {
    if (!posto) return null;

    return (
      <DetalhesPostoConsulta
        posto={posto}
        referencia={filtros.referencia}
        usuario={usuario}
        erroRota={erroRota}
        onErroRota={definirErroRota}
        onAtualizar={recarregar}
        onRegistrar={(combustivel) =>
          abrirCadastro(posto, combustivel, Date.now())
        }
        onVoltar={() => {
          selecionar(null);
          abrirLista(modo === "mapa");
        }}
      />
    );
  }

  const painelNaLateral = desktop && modo === "mapa";

  const modalAberto =
    legendaAberta || (!painelNaLateral && (listaAberta || !!posto));

  function fecharPainel() {
    abrirLegenda(false);
    abrirLista(false);
    selecionar(null);
  }

  return (
    <SafeAreaView
      edges={["top", "left", "right"]}
      style={{
        flex: 1,
        backgroundColor: colors.background,
      }}
    >
      <View style={[styles.cabecalho, { borderBottomColor: colors.border }]}>
        <AvisoFavoritos />

        <View
          style={{
            flexDirection: "row",
            alignItems: "center",
            gap: 12,
          }}
        >
          <Text
            accessibilityRole="header"
            style={[
              styles.titulo,
              {
                color: colors.textPrimary,
                flex: 1,
                minWidth: 0,
              },
            ]}
          >
            {modo === "mapa"
              ? desktop
                ? "Encontre seu próximo posto"
                : "Postos próximos"
              : "Postos na região"}
          </Text>

          {modo === "mapa" ? (
            <AtalhoBuscaMapa aoAplicar={() => selecionar(null)} />
          ) : null}
        </View>

        <Text style={{ color: colors.textSecondary }}>
          Preço exibido: {referencia.nome}
          {" · "}
          {filtros.combustiveis.length
            ? filtros.combustiveis.length === 1
              ? produto(filtros.combustiveis[0]).nome
              : filtros.combustiveis.length + " combustíveis selecionados"
            : "Todos os combustíveis"}
          {" · "}
          {filtros.marca === "nao_informada"
            ? "Marca não informada"
            : filtros.marca || "Todas as bandeiras"}
        </Text>

        {modo === "lista" ? <AvaliacaoApp compacto /> : null}

        {avisoGps ? (
          <Text
            accessibilityLabel={avisoGps}
            style={{
              color: colors.textSecondary,
              marginTop: 6,
            }}
          >
            {avisoGps}
          </Text>
        ) : null}
      </View>

      <View
        style={{
          flex: 1,
          flexDirection: "row",
        }}
      >
        <View style={{ flex: 1 }}>
          {modo === "mapa" ? (
            <MapaLeaflet
              ref={mapa}
              postos={pinos}
              usuario={referenciaMapa}
              onSelecionarPosto={(id) => {
                const p = postos.find((item) => item.id === id);

                if (p) escolher(p);
              }}
            />
          ) : (
            <ScrollView
              keyboardShouldPersistTaps="handled"
              contentContainerStyle={{
                paddingBottom: 16,
              }}
            >
              {lista()}
            </ScrollView>
          )}

          {modo === "mapa" && (carregando || erro) ? (
            <View
              pointerEvents="box-none"
              style={[
                styles.aviso,
                {
                  backgroundColor: colors.surface,
                },
              ]}
            >
              {carregando ? (
                <ActivityIndicator color={colors.textPrimary} />
              ) : (
                <Pressable
                  accessibilityRole="button"
                  onPress={recarregar}
                  style={{ padding: 12 }}
                >
                  <Text style={{ color: colors.danger }}>
                    Falha ao atualizar. Tentar novamente
                  </Text>
                </Pressable>
              )}
            </View>
          ) : null}

          <View
            style={[
              styles.acoes,
              {
                backgroundColor: colors.background,
                borderTopColor: colors.border,
              },
            ]}
          >
            <BotaoConsulta
              label="Filtros"
              icone="options-outline"
              onPress={() => abrirFiltros(true)}
            />

            <BotaoConsulta
              label="Localização"
              icone="locate-outline"
              onPress={() => {
                if (referenciaMapa) {
                  mapa.current?.centralizar(
                    referenciaMapa.lat,
                    referenciaMapa.lon,
                    zoomLocalizacao(referenciaMapa),
                  );
                }

                atualizarLocalizacao();
              }}
            />

            {modo === "mapa" ? (
              <BotaoConsulta
                label="Postos"
                icone="list-outline"
                onPress={() => {
                  selecionar(null);

                  if (desktop) {
                    definirPainelDesktop((v) => !v);
                  } else {
                    abrirLista(true);
                  }
                }}
              />
            ) : null}

            <BotaoConsulta
              label="Legenda"
              icone="information-circle-outline"
              onPress={() => abrirLegenda(true)}
            />
          </View>
        </View>

        {painelNaLateral && painelDesktop ? (
          <View
            testID="painel-postos-desktop"
            style={{
              width: 360,
              maxWidth: "46%",
              borderLeftWidth: 1,
              borderLeftColor: colors.border,
            }}
          >
            <ScrollView keyboardShouldPersistTaps="handled">
              {posto ? detalhes() : lista()}
            </ScrollView>
          </View>
        ) : null}
      </View>

      {filtrosAbertos ? (
        <FiltrosPostosPainel
          aberto
          fechar={() => {
            abrirFiltros(false);
            selecionar(null);
          }}
          marcas={marcas}
        />
      ) : null}

      <Modal
        visible={modalAberto}
        transparent
        animationType="slide"
        onRequestClose={fecharPainel}
      >
        <View style={styles.fundoModal}>
          <SafeAreaView
            style={[
              styles.painelModal,
              {
                backgroundColor: colors.background,
              },
            ]}
          >
            <ScrollView
              keyboardShouldPersistTaps="handled"
              contentContainerStyle={{
                paddingBottom: 16,
              }}
            >
              {legendaAberta ? (
                <View style={{ padding: 20 }}>
                  <LegendaCombustiveis />
                </View>
              ) : posto ? (
                detalhes()
              ) : (
                lista()
              )}
            </ScrollView>

            <View style={{ padding: 16 }}>
              <AppButton label="Fechar painel" onPress={fecharPainel} />
            </View>
          </SafeAreaView>
        </View>
      </Modal>
    </SafeAreaView>
  );
}
