import { createNativeStackNavigator } from "@react-navigation/native-stack";

import { useAuth } from "../contexts/AuthContext";
import Entrada from "../screens/Entrada";
import Login from "../screens/Login";
import ValidarCodigo from "../screens/Login/ValidarCodigo";
import RecuperarSenha from "../screens/RecuperarSenha";
import RedefinirSenha from "../screens/RedefinirSenha";
import Registo from "../screens/Registro";

export type AuthStackParamList = {
  Entrada: undefined;

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
    message?: string;
  };

  RedefinirSenha: {
    email: string;
    codigo: string;
  };
};

const Stack = createNativeStackNavigator<AuthStackParamList>();

export function AuthRoutes() {
  const { destinoAuth } = useAuth();

  return (
    <Stack.Navigator
      initialRouteName={destinoAuth}
      screenOptions={{ headerShown: false }}
    >
      <Stack.Screen name="Entrada" component={Entrada} />
      <Stack.Screen name="Login" component={Login} />
      <Stack.Screen name="Registo" component={Registo} />
      <Stack.Screen name="RecuperarSenha" component={RecuperarSenha} />
      <Stack.Screen name="ValidarCodigo" component={ValidarCodigo} />
      <Stack.Screen name="RedefinirSenha" component={RedefinirSenha} />
    </Stack.Navigator>
  );
}
