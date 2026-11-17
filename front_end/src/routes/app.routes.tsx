import Ionicons from "@expo/vector-icons/Ionicons";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import type { NavigatorScreenParams } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { Text, TouchableOpacity, useWindowDimensions } from "react-native";

import { AcessoRestrito } from "../components/acesso-restrito";
import { useAppTheme } from "../components/design";
import { Navegacao } from "../components/navegacao";
import { FavoritosProvider } from "../contexts/FavoritosContext";
import { FiltrosPostosProvider } from "../contexts/FiltrosPostosContext";
import AdicionarPreco from "../screens/AdicionarPreco";
import ApagarConta from "../screens/ApagarConta";
import Aparencia from "../screens/Aparencia";
import Assistente from "../screens/Assistente";
import Atividade from "../screens/Atividade";
import Configuracoes from "../screens/Configuracoes";
import ConsultaPostos from "../screens/ConsultaPostos";
import Conta from "../screens/Conta";
import DadosPessoais from "../screens/DadosPessoais";
import Favoritos from "../screens/Favoritos";
import HistoricoKarma from "../screens/HistoricoKarma";
import Notificacoes from "../screens/Notificacoes";
import PreferenciasAlertas from "../screens/PreferenciaAlertas";
import Ranking from "../screens/Raking";
import RedefinirSenhaConta from "../screens/RedefinirSenhaConta";
import type { Combustivel } from "../services/catalogoPostos";
import { design } from "../theme/design";
export type Abas = {
  Feed: undefined;
  Mapa: undefined;
  Adicionar:
    | {
        postoId?: number;
        combustivel?: Combustivel;
        solicitacao?: number;
      }
    | undefined;
  IA: undefined;
  Perfil: NavigatorScreenParams<ContaPilha> | undefined;
};

export type ContaPilha = {
  MeuPerfil: undefined;
  AtividadePessoal: undefined;
  HistoricoKarma: undefined;
  Ranking: undefined;
  Definicoes: undefined;
  DadosPessoais: undefined;
  ApagarConta: undefined;
  Notificacoes: undefined;
  PreferenciasAlertas: undefined;
  Aparencia: undefined;
  Favoritos: undefined;
  RedefinirSenhaConta: undefined;
};
const Tab = createBottomTabNavigator<Abas>();
const Stack = createNativeStackNavigator<ContaPilha>();

function Feed() {
  return <ConsultaPostos modo="lista" />;
}

function Adicionar() {
  return (
    <AcessoRestrito>
      <AdicionarPreco />
    </AcessoRestrito>
  );
}

function IA() {
  return (
    <AcessoRestrito>
      <Assistente />
    </AcessoRestrito>
  );
}

function ContaRoutes() {
  const { colors } = useAppTheme();

  return (
    <Stack.Navigator
      screenOptions={({ navigation }) => ({
        headerLeft: () => (
          <TouchableOpacity
            accessibilityRole="button"
            accessibilityLabel="Voltar"
            onPress={() => {
              if (navigation.canGoBack()) navigation.goBack();
              else navigation.popTo("MeuPerfil");
            }}
            style={{
              padding: 12,
              minHeight: 48,
              minWidth: 48,
              flexDirection: "row",
              alignItems: "center",
              gap: 8,
            }}
          >
            <Ionicons
              name="arrow-back"
              size={22}
              color={colors.textPrimary}
              accessible={false}
            />

            <Text style={{ color: colors.textPrimary }}>Voltar</Text>
          </TouchableOpacity>
        ),
        headerStyle: {
          backgroundColor: colors.surface,
        },
        headerTintColor: colors.textPrimary,
        contentStyle: {
          backgroundColor: colors.background,
        },
      })}
    >
      <Stack.Screen
        name="MeuPerfil"
        component={Conta}
        options={{
          title: "Perfil",
          headerShown: false,
        }}
      />

      <Stack.Screen
        name="AtividadePessoal"
        component={Atividade}
        options={({ navigation }) => ({
          title: "Atividade pessoal",
          headerLeft: () => (
            <TouchableOpacity
              accessibilityRole="button"
              accessibilityLabel="Voltar ao perfil"
              onPress={() => navigation.popTo("MeuPerfil")}
              style={{
                padding: 12,
                minHeight: 48,
                minWidth: 48,
                justifyContent: "center",
                flexDirection: "row",
                alignItems: "center",
                gap: 8,
              }}
            >
              <Ionicons
                name="arrow-back"
                size={22}
                color={colors.textPrimary}
                accessible={false}
              />

              <Text style={{ color: colors.textPrimary }}>Voltar</Text>
            </TouchableOpacity>
          ),
        })}
      />

      <Stack.Screen
        name="Definicoes"
        component={Configuracoes}
        options={{ title: "Configurações" }}
      />

      <Stack.Screen
        name="DadosPessoais"
        component={DadosPessoais}
        options={{ title: "Dados pessoais" }}
      />

      <Stack.Screen
        name="ApagarConta"
        component={ApagarConta}
        options={{ title: "Apagar conta" }}
      />

      <Stack.Screen
        name="Aparencia"
        component={Aparencia}
        options={{ title: "Aparência" }}
      />

      <Stack.Screen
        name="Favoritos"
        component={Favoritos}
        options={{ title: "Favoritos" }}
      />

      <Stack.Screen
        name="RedefinirSenhaConta"
        component={RedefinirSenhaConta}
        options={{ title: "Redefinir senha" }}
      />

      <Stack.Screen
        name="Notificacoes"
        component={Notificacoes}
        options={{ title: "Notificações" }}
      />

      <Stack.Screen
        name="PreferenciasAlertas"
        component={PreferenciasAlertas}
        options={{ title: "Preferências de alertas" }}
      />
      <Stack.Screen
        name="HistoricoKarma"
        component={HistoricoKarma}
        options={{ title: "Histórico de Karma" }}
      />

      <Stack.Screen
        name="Ranking"
        component={Ranking}
        options={{ title: "Ranking" }}
      />
    </Stack.Navigator>
  );
}

function Perfil() {
  return (
    <AcessoRestrito>
      <ContaRoutes />
    </AcessoRestrito>
  );
}

function AbasRoutes() {
  const desktop = useWindowDimensions().width >= design.desktop;
  const { colors } = useAppTheme();

  return (
    <Tab.Navigator
      initialRouteName="Mapa"
      tabBar={(props) => <Navegacao {...props} />}
      screenOptions={{
        headerShown: false,
        tabBarPosition: desktop ? "left" : "bottom",
        sceneStyle: {
          backgroundColor: colors.background,
        },
      }}
    >
      <Tab.Screen name="Feed" component={Feed} />
      <Tab.Screen name="Mapa" component={ConsultaPostos} />
      <Tab.Screen name="Adicionar" component={Adicionar} />
      <Tab.Screen name="IA" component={IA} />
      <Tab.Screen name="Perfil" component={Perfil} />
    </Tab.Navigator>
  );
}

export function AppRoutes() {
  return (
    <FavoritosProvider>
      <FiltrosPostosProvider>
        <AbasRoutes />
      </FiltrosPostosProvider>
    </FavoritosProvider>
  );
}
