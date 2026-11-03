import React, {
    forwardRef,
    useCallback,
    useImperativeHandle,
    useRef,
} from "react";
import {
    ActivityIndicator,
    Linking,
    Pressable,
    StyleSheet,
    Text,
    View,
} from "react-native";
import { WebView, type WebViewMessageEvent } from "react-native-webview";
import { MAPA_BASE_URL, MAPA_HTML } from "./mapaHtml";
import type { MapaLeafletHandle, MapaLeafletProps } from "./tipos";
import { useMapaBridge } from "./useMapaBridge";

// Constante de módulo: a MESMA referência em todo render => o WebView nunca recarrega a página.
const SOURCE = { html: MAPA_HTML, baseUrl: MAPA_BASE_URL };
const ORIGENS = ["*"];

const MapaLeaflet = forwardRef<MapaLeafletHandle, MapaLeafletProps>(
  function MapaLeaflet(
    { postos, usuario, onSelecionarPosto, onRegiaoMudou },
    ref,
  ) {
    const webRef = useRef<WebView<any>>(null);
    const enviarBruto = useCallback((json: string) => {
      // JSON.stringify duas vezes => literal de string JS seguro (aspas, quebras de linha, "</script>").
      webRef.current?.injectJavaScript(
        `window.__litro && window.__litro.receber(${JSON.stringify(json)}); true;`,
      );
    }, []);

    const abrirLink = useCallback((url: string) => {
      Linking.openURL(url).catch(() => undefined);
    }, []);

    const {
      estado,
      tentativa,
      aoReceberMensagem,
      reiniciar,
      aoFalhar,
      centralizar,
    } = useMapaBridge({
      postos,
      usuario,
      enviarBruto,
      onSelecionarPosto,
      onRegiaoMudou,
      onAbrirLink: abrirLink,
    });

    useImperativeHandle(ref, () => ({ centralizar }), [centralizar]);

    const aoMensagem = useCallback(
      (e: WebViewMessageEvent) => aoReceberMensagem(e.nativeEvent.data),
      [aoReceberMensagem],
    );

    return (
      <View style={styles.container}>
        <WebView
          key={tentativa}
          ref={webRef}
          source={SOURCE}
          originWhitelist={ORIGENS}
          onMessage={aoMensagem}
          onError={aoFalhar}
          onHttpError={aoFalhar}
          // O processo do WebView pode ser morto pelo sistema (pouca memória): remonta e reenvia o estado.
          onContentProcessDidTerminate={reiniciar}
          onRenderProcessGone={reiniciar}
          javaScriptEnabled
          domStorageEnabled
          setSupportMultipleWindows={false}
          mixedContentMode="never"
          allowFileAccess={false}
          scrollEnabled={false}
          bounces={false}
          overScrollMode="never"
          showsHorizontalScrollIndicator={false}
          showsVerticalScrollIndicator={false}
          style={styles.webview}
        />

        {estado === "carregando" && (
          <View style={styles.overlay} pointerEvents="none">
            <ActivityIndicator size="large" />
          </View>
        )}

        {estado === "erro" && (
          <View style={styles.overlay}>
            <Text style={styles.titulo}>Não foi possível carregar o mapa</Text>
            <Text style={styles.texto}>
              Verifique a sua conexão com a internet.
            </Text>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Tentar carregar o mapa novamente"
              onPress={reiniciar}
              style={styles.botao}
            >
              <Text style={styles.botaoTexto}>Tentar novamente</Text>
            </Pressable>
          </View>
        )}
      </View>
    );
  },
);

export default React.memo(MapaLeaflet);

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#e9edf1" },
  webview: { flex: 1, backgroundColor: "transparent" },
  overlay: {
    ...StyleSheet.absoluteFill,
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
    backgroundColor: "rgba(233,237,241,0.92)",
  },
  titulo: {
    fontSize: 16,
    fontWeight: "600",
    color: "#1f2933",
    textAlign: "center",
  },
  texto: { marginTop: 6, fontSize: 14, color: "#52606d", textAlign: "center" },
  botao: {
    marginTop: 16,
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderRadius: 8,
    backgroundColor: "#1f2933",
  },
  botaoTexto: { color: "#fff", fontSize: 15, fontWeight: "600" },
});
