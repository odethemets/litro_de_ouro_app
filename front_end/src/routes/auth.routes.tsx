import { createNativeStackNavigator } from "@react-navigation/native-stack";

import Login from "../screens/Login";
import ValidarCodigo from "../screens/Login/ValidarCodigo";
import RecuperarSenha from "../screens/RecuperarSenha";
import RedefinirSenha from "../screens/RedefinirSenha";
import Registo from "../screens/Registro";

export type AuthStackParamList = {
  // Mensagem de confirmação ou de alteração de senha.
  Login:
    | {
        message?: string;
      }
    | undefined;

  Registo: undefined;

  RecuperarSenha:
    | {
        emailBase?: string;
      }
    | undefined;

  ValidarCodigo: {
    email: string;
    finalidade: "recuperacao" | "registo";

    // Permite enviar e ler a mensagem sem torná-la obrigatória.
    message?: string;
  };

  RedefinirSenha: {
    email: string;
    codigo: string;
  };
};

const Stack = createNativeStackNavigator<AuthStackParamList>();

export function AuthRoutes() {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="Login" component={Login} />
      <Stack.Screen name="Registo" component={Registo} />
      <Stack.Screen name="RecuperarSenha" component={RecuperarSenha} />
      <Stack.Screen name="ValidarCodigo" component={ValidarCodigo} />
      <Stack.Screen name="RedefinirSenha" component={RedefinirSenha} />
    </Stack.Navigator>
  );
}
