import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { Text } from "react-native";
import {
  AppButton,
  AuthLayout,
  Notice,
  Surface,
  useAppTheme,
} from "../../components/design";
import { useAuth } from "../../contexts/AuthContext";
import type { AuthStackParamList } from "../../routes/auth.routes";

type Props = NativeStackScreenProps<AuthStackParamList, "Entrada">;

export default function Entrada({ navigation }: Props) {
  const { enterGuest } = useAuth();
  const { colors } = useAppTheme();

  return (
    <AuthLayout
      title="Encontre postos. Compare preços. Contribua."
      subtitle="Informações compartilhadas pela comunidade para ajudar nas suas escolhas."
    >
      <Surface>
        <Text
          style={{
            color: colors.textPrimary,
            fontSize: 24,
            fontWeight: "800",
          }}
        >
          Como você quer começar?
        </Text>

        <Notice>
          Explore o mapa e o Feed. Para contribuir, entre na sua conta.
        </Notice>

        <AppButton
          label="Fazer login"
          onPress={() => navigation.navigate("Login")}
        />
        <AppButton
          label="Criar conta"
          secondary
          onPress={() => navigation.navigate("Registo")}
        />
        <AppButton label="Explorar sem conta" secondary onPress={enterGuest} />
      </Surface>
    </AuthLayout>
  );
}
