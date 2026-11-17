import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { isAxiosError } from "axios";
import { useRef, useState } from "react";
import { Switch, Text, View } from "react-native";
import {
  AppButton,
  AppField,
  AuthLayout,
  Notice,
  Surface,
  useAppTheme,
} from "../../components/design";
import { useAuth } from "../../contexts/AuthContext";
import type { AuthStackParamList } from "../../routes/auth.routes";
import { api } from "../../services/API";

type Props = NativeStackScreenProps<AuthStackParamList, "Login">;

export default function Login({ navigation, route }: Props) {
  const { signIn, enterGuest } = useAuth();
  const { colors } = useAppTheme();

  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [mostrar, setMostrar] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState("");

  const pending = useRef(false);

  const entrar = async () => {
    if (pending.current) return;

    setErro("");
    const endereco = email.trim();

    if (
      endereco.length > 100 ||
      !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(endereco) ||
      !senha.trim()
    ) {
      setErro("Informe um e-mail válido e sua senha.");
      return;
    }

    pending.current = true;
    setOcupado(true);

    try {
      const resposta = await api.post<{ token: string }>("/auth/login", {
        email: endereco,
        senha,
      });

      await signIn(resposta.data.token);
    } catch (falha: unknown) {
      if (
        isAxiosError<{
          error?: string;
          require_validation?: boolean;
        }>(falha) &&
        falha.response?.status === 403 &&
        falha.response.data.require_validation
      ) {
        navigation.navigate("ValidarCodigo", {
          email: endereco,
          finalidade: "registo",
          message: falha.response.data.error,
        });
      } else {
        const mensagem = isAxiosError<{ error?: string }>(falha)
          ? falha.response?.data?.error
          : undefined;

        setErro(
          mensagem ||
            "Não foi possível entrar e guardar sua sessão. Confira a conexão e permita o armazenamento neste dispositivo.",
        );
      }
    } finally {
      pending.current = false;
      setOcupado(false);
    }
  };

  return (
    <AuthLayout
      title="Bom ter você de volta"
      subtitle="Entre para contribuir e acompanhar sua atividade."
    >
      <Surface>
        {route.params?.message ? <Notice>{route.params.message}</Notice> : null}

        {erro ? <Notice error>{erro}</Notice> : null}

        <AppField
          label="E-mail"
          placeholder="Seu e-mail"
          keyboardType="email-address"
          autoCapitalize="none"
          autoCorrect={false}
          autoComplete="email"
          value={email}
          onChangeText={setEmail}
          editable={!ocupado}
        />

        <AppField
          label="Senha"
          placeholder="Sua senha"
          secureTextEntry={!mostrar}
          autoCapitalize="none"
          autoComplete="current-password"
          value={senha}
          onChangeText={setSenha}
          editable={!ocupado}
          onSubmitEditing={() => {
            void entrar();
          }}
        />

        <View
          style={{
            flexDirection: "row",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
          }}
        >
          <Text
            style={{
              color: colors.textSecondary,
              fontSize: 15,
            }}
          >
            Mostrar senha
          </Text>

          <Switch
            accessibilityLabel="Mostrar senha"
            value={mostrar}
            disabled={ocupado}
            onValueChange={setMostrar}
            trackColor={{
              false: colors.border,
              true: colors.primary,
            }}
          />
        </View>

        <AppButton
          label="Entrar"
          busy={ocupado}
          onPress={() => {
            void entrar();
          }}
        />

        <AppButton
          label="Esqueci minha senha"
          secondary
          disabled={ocupado}
          onPress={() =>
            navigation.navigate("RecuperarSenha", { emailBase: email.trim() })
          }
        />

        <AppButton
          label="Criar conta"
          secondary
          disabled={ocupado}
          onPress={() => navigation.navigate("Registo")}
        />
      </Surface>

      <AppButton
        label="Explorar sem conta"
        secondary
        disabled={ocupado}
        onPress={enterGuest}
      />

      <AppButton
        label="Voltar à entrada"
        secondary
        disabled={ocupado}
        onPress={() => navigation.navigate("Entrada")}
      />
    </AuthLayout>
  );
}
