import React, {
    forwardRef,
    useCallback,
    useEffect,
    useImperativeHandle,
    useRef,
} from "react";
import {
    ActivityIndicator,
    Pressable,
    StyleSheet,
    Text,
    View,
} from "react-native";
import { MAPA_HTML } from "./mapaHtml";
import type { MapaLeafletHandle, MapaLeafletProps } from "./tipos";
import { useMapaBridge } from "./useMapaBridge";

/**
 * Versão web (Expo Web): react-native-webview não existe no navegador, então o mesmo HTML
 * roda num <iframe srcDoc>. O protocolo de mensagens é idêntico ao nativo (useMapaBridge).
 * Nada aqui toca em `window`/`document` durante a importação, portanto é seguro com SSR/static rendering.
 */
const MapaLeaflet = forwardRef<MapaLeafletHandle, MapaLeafletProps>(
  function MapaLeaflet(
    { postos, usuario, onSelecionarPosto, onRegiaoMudou },
    ref,
  ) {
    const iframeRef = useRef<HTMLIFrameElement>(null);

    const enviarBruto = useCallback((json: string) => {
      // srcDoc com sandbox sem allow-same-origin tem origem opaca: o alvo só pode ser "*";
      // a segurança vem de validar `event.source` na recepção.
      iframeRef.current?.contentWindow?.postMessage(json, "*");
    }, []);

    const abrirLink = useCallback((url: string) => {
      window.open(url, "_blank", "noopener,noreferrer");
    }, []);

    const { estado, tentativa, aoReceberMensagem, reiniciar, centralizar } =
      useMapaBridge({
        postos,
        usuario,
        enviarBruto,
        onSelecionarPosto,
        onRegiaoMudou,
        onAbrirLink: abrirLink,
      });

    useImperativeHandle(ref, () => ({ centralizar }), [centralizar]);

    useEffect(() => {
      const ouvir = (e: MessageEvent) => {
        if (e.source !== iframeRef.current?.contentWindow) return; // ignora qualquer outra janela
        aoReceberMensagem(e.data);
      };
      window.addEventListener("message", ouvir);
      return () => window.removeEventListener("message", ouvir);
    }, [aoReceberMensagem]);

    return (
      <View style={styles.container}>
        <iframe
          key={tentativa}
          ref={iframeRef}
          title="Mapa de postos"
          srcDoc={MAPA_HTML}
          sandbox="allow-scripts"
          style={{ border: 0, width: "100%", height: "100%" }}
        />

        {estado === "carregando" && (
          <View style={[styles.overlay, { pointerEvents: "none" }]}>
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
