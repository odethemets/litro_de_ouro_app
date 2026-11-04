// front_end/src/screens/Login/ValidarCodigo.tsx

import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import axios from "axios";
import { useContext, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Keyboard,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  TouchableWithoutFeedback,
  View,
} from "react-native";

import { ThemeContext } from "../../contexts/ThemeContext";
import type { AuthStackParamList } from "../../routes/auth.routes";
import { api } from "../../services/API";

type Props = NativeStackScreenProps<AuthStackParamList, "ValidarCodigo">;

type Acao = "validar" | "reenviar" | null;

export default function ValidarCodigo({ route, navigation }: Props) {
  const { colors } = useContext(ThemeContext);
  const { email, finalidade } = route.params;

  const [codigo, setCodigo] = useState("");
  const [mensagem, setMensagem] = useState(route.params.message ?? "");
  const [acao, setAcao] = useState<Acao>(null);

  const ocupado = acao !== null;
  const codigoValido = /^[0-9]{6}$/.test(codigo);

  useEffect(() => {
    // Limpa um código anterior quando a tela recebe outra solicitação.
    setCodigo("");
    setMensagem(route.params.message ?? "");
  }, [route.params]);

  const handleValidar = async () => {
    if (ocupado) return;

    setMensagem("");

    if (!codigoValido) {
      setMensagem("O código deve conter exatamente 6 dígitos.");
      return;
    }

    if (finalidade === "recuperacao") {
      // Não informa que o código foi validado.
      // O backend fará essa validação junto com a nova senha.
      navigation.navigate("RedefinirSenha", {
        email,
        codigo,
      });
      return;
    }

    setAcao("validar");

    try {
      await api.post("/auth/confirmar-email", {
        email,
        codigo,
      });

      // Remove a tela de código do histórico após a confirmação.
      navigation.reset({
        index: 0,
        routes: [
          {
            name: "Login",
            params: {
              message:
                "E-mail confirmado com sucesso! Faça login para continuar.",
            },
          },
        ],
      });
    } catch (erro: unknown) {
      const mensagemApi = axios.isAxiosError<{ error?: string }>(erro)
        ? erro.response?.data?.error
        : undefined;

      setMensagem(
        mensagemApi ??
          "Não foi possível confirmar o código. Confira sua conexão e tente novamente.",
      );
    } finally {
      setAcao(null);
    }
  };

  const handleReenviar = async () => {
    if (ocupado) return;

    setAcao("reenviar");
    setMensagem("");

    try {
      // Cada finalidade utiliza sua própria rota.
      const endpoint =
        finalidade === "recuperacao"
          ? "/auth/recuperar-senha"
          : "/auth/reenviar-codigo";

      const response = await api.post<{ message?: string }>(endpoint, {
        email,
      });

      // O código antigo deixa de ser válido após um novo envio.
      setCodigo("");

      setMensagem(
        response.data.message ??
          "Solicitação recebida. Confira o e-mail e o spam. Se não chegar, tente novamente em instantes.",
      );
    } catch (erro: unknown) {
      const mensagemApi = axios.isAxiosError<{ error?: string }>(erro)
        ? erro.response?.data?.error
        : undefined;

      setMensagem(
        mensagemApi ??
          "Não foi possível solicitar outro código. Tente novamente.",
      );
    } finally {
      setAcao(null);
    }
  };

  const conteudo = (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
      <View style={styles.contentWrapper}>
        <View style={styles.header}>
          <Text style={[styles.title, { color: colors.primary }]}>
            Verificação
          </Text>

          <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
            Use o código de 6 dígitos recebido no e-mail:
          </Text>

          <Text style={[styles.emailHighlight, { color: colors.textPrimary }]}>
            {email}
          </Text>
        </View>

        <View style={styles.form}>
          {mensagem ? (
            <Text
              accessibilityRole="alert"
              accessibilityLiveRegion="polite"
              style={[styles.message, { color: colors.textPrimary }]}
            >
              {mensagem}
            </Text>
          ) : null}

          <TextInput
            style={[
              styles.input,
              {
                backgroundColor: colors.surface,
                color: colors.textPrimary,
                borderColor: colors.border,
              },
            ]}
            placeholder="000000"
            placeholderTextColor={colors.textSecondary}
            keyboardType="number-pad"
            maxLength={6}
            textAlign="center"
            value={codigo}
            onChangeText={(valor) =>
              setCodigo(valor.replace(/[^0-9]/g, "").slice(0, 6))
            }
            editable={!ocupado}
            accessibilityLabel="Código de verificação"
          />

          {finalidade === "recuperacao" ? (
            <Text style={[styles.help, { color: colors.textSecondary }]}>
              O código será verificado ao salvar a nova senha.
            </Text>
          ) : null}

          <TouchableOpacity
            style={[
              styles.button,
              {
                backgroundColor: colors.primary,
                opacity: ocupado || !codigoValido ? 0.7 : 1,
              },
            ]}
            onPress={handleValidar}
            disabled={ocupado || !codigoValido}
          >
            {acao === "validar" ? (
              <ActivityIndicator size="small" color="#121212" />
            ) : (
              <Text style={styles.buttonText}>
                {finalidade === "recuperacao"
                  ? "Continuar"
                  : "Confirmar Código"}
              </Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.backButton}
            onPress={handleReenviar}
            disabled={ocupado}
          >
            {acao === "reenviar" ? (
              <ActivityIndicator size="small" color={colors.primary} />
            ) : (
              <Text style={{ color: colors.primary }}>
                Solicitar outro código
              </Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.backButton}
            onPress={() => navigation.goBack()}
            disabled={ocupado}
          >
            <Text
              style={[styles.backButtonText, { color: colors.textSecondary }]}
            >
              Voltar
            </Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );

  if (Platform.OS === "web") return conteudo;

  return (
    <KeyboardAvoidingView
      style={{ flex: 1 }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <TouchableWithoutFeedback onPress={Keyboard.dismiss} accessible={false}>
        {conteudo}
      </TouchableWithoutFeedback>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
  },
  contentWrapper: {
    width: "100%",
    maxWidth: 400,
    paddingHorizontal: 24,
  },
  header: { marginBottom: 48, alignItems: "center" },
  title: { fontSize: 32, fontWeight: "bold", marginBottom: 8 },
  subtitle: { fontSize: 16, textAlign: "center", marginBottom: 4 },
  emailHighlight: {
    fontSize: 16,
    fontWeight: "bold",
    textAlign: "center",
  },
  form: { width: "100%" },
  message: { marginBottom: 16, fontSize: 14, lineHeight: 21 },
  help: { marginBottom: 16, fontSize: 13, lineHeight: 19 },
  input: {
    height: 54,
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 16,
    marginBottom: 16,
    fontSize: 16,
  },
  button: {
    height: 54,
    borderRadius: 8,
    justifyContent: "center",
    alignItems: "center",
    marginTop: 8,
  },
  buttonText: {
    color: "#121212",
    fontSize: 16,
    fontWeight: "bold",
  },
  backButton: { marginTop: 24, alignItems: "center" },
  backButtonText: { fontSize: 16 },
});
