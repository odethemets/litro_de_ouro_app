// front_end/src/screens/Registro/index.tsx

import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import axios from "axios";
import { useContext, useState } from "react";
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

type Props = NativeStackScreenProps<AuthStackParamList, "Registo">;

interface RespostaCadastro {
  message?: string;
  email_sent?: boolean;
}

export default function Registo({ navigation }: Props) {
  const { colors } = useContext(ThemeContext);

  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [mensagem, setMensagem] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleRegisto = async () => {
    if (isLoading) return;

    setMensagem("");

    const nomeNormalizado = nome.trim();
    const emailNormalizado = email.trim();

    const emailValido =
      emailNormalizado.length <= 100 &&
      /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(emailNormalizado);

    // Conta caracteres Unicode como o len() do Python.
    const tamanhoSenha = Array.from(senha).length;

    if (!nomeNormalizado || !emailValido) {
      setMensagem("Informe seu nome e um e-mail válido.");
      return;
    }

    if (!senha.trim() || tamanhoSenha < 6 || tamanhoSenha > 1024) {
      setMensagem("A senha deve ter entre 6 e 1024 caracteres.");
      return;
    }

    setIsLoading(true);

    try {
      const response = await api.post<RespostaCadastro>("/auth/cadastro", {
        nome: nomeNormalizado,
        email: emailNormalizado,

        // Preserva exatamente a senha digitada.
        senha,
      });

      // A conta já existe mesmo quando o envio do e-mail falha.
      // A tela seguinte apresenta o resultado e permite reenviar.
      navigation.navigate("ValidarCodigo", {
        email: emailNormalizado,
        finalidade: "registo",
        message:
          response.data.message ??
          (response.data.email_sent === false
            ? "Conta criada, mas o envio falhou. Solicite outro código."
            : "Conta criada. Use o código recebido para confirmar seu e-mail."),
      });
    } catch (erro: unknown) {
      const mensagemApi = axios.isAxiosError<{ error?: string }>(erro)
        ? erro.response?.data?.error
        : undefined;

      // Não registrar o erro Axios completo: contém os dados enviados.
      setMensagem(
        mensagemApi ??
          "Não foi possível criar a conta. Confira sua conexão e tente novamente.",
      );
    } finally {
      setIsLoading(false);
    }
  };

  const conteudo = (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
      <View style={styles.contentWrapper}>
        <View style={styles.header}>
          <Text style={[styles.title, { color: colors.primary }]}>
            Criar Conta
          </Text>

          <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
            Junte-se à comunidade Litro de Ouro.
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
            placeholder="Nome completo"
            placeholderTextColor={colors.textSecondary}
            value={nome}
            onChangeText={setNome}
            editable={!isLoading}
            accessibilityLabel="Nome completo"
          />

          <TextInput
            style={[
              styles.input,
              {
                backgroundColor: colors.surface,
                color: colors.textPrimary,
                borderColor: colors.border,
              },
            ]}
            placeholder="E-mail"
            placeholderTextColor={colors.textSecondary}
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
            value={email}
            onChangeText={setEmail}
            editable={!isLoading}
            accessibilityLabel="E-mail"
          />

          <TextInput
            style={[
              styles.input,
              {
                backgroundColor: colors.surface,
                color: colors.textPrimary,
                borderColor: colors.border,
              },
            ]}
            placeholder="Palavra-passe"
            placeholderTextColor={colors.textSecondary}
            secureTextEntry
            autoCapitalize="none"
            autoCorrect={false}
            value={senha}
            onChangeText={setSenha}
            editable={!isLoading}
            accessibilityLabel="Palavra-passe"
          />

          <TouchableOpacity
            style={[
              styles.button,
              {
                backgroundColor: colors.primary,
                opacity: isLoading ? 0.7 : 1,
              },
            ]}
            onPress={handleRegisto}
            disabled={isLoading}
          >
            {isLoading ? (
              <ActivityIndicator size="small" color="#121212" />
            ) : (
              <Text style={styles.buttonText}>Avançar</Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.backButton}
            onPress={() => navigation.goBack()}
            disabled={isLoading}
          >
            <Text
              style={[styles.backButtonText, { color: colors.textSecondary }]}
            >
              Voltar ao Login
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
  subtitle: { fontSize: 16, textAlign: "center" },
  form: { width: "100%" },
  message: { marginBottom: 16, fontSize: 14, lineHeight: 21 },
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
