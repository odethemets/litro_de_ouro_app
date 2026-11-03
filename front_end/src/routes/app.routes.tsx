// src/routes/app.routes.tsx
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { useContext } from "react";
import { Text, View } from "react-native";

import { ThemeContext } from "../contexts/ThemeContext";

// Importação dos ecrãs reais
import Atividade from "../screens/Atividade";
import Conta from "../screens/Conta";
import Inicio from "../screens/Inicio";

const Tab = createBottomTabNavigator();
const ContaStack = createNativeStackNavigator();

// --- ECRÃS TEMPORÁRIOS (Placeholders) para as Definições e Notificações ---
function DefinicoesScreen() {
  const { colors } = useContext(ThemeContext) as any;
  return (
    <View
      style={{
        flex: 1,
        justifyContent: "center",
        alignItems: "center",
        backgroundColor: colors.background,
      }}
    >
      <Text style={{ color: colors.textPrimary, fontSize: 18 }}>
        Página de Definições
      </Text>
    </View>
  );
}

function NotificacoesScreen() {
  const { colors } = useContext(ThemeContext) as any;
  return (
    <View
      style={{
        flex: 1,
        justifyContent: "center",
        alignItems: "center",
        backgroundColor: colors.background,
      }}
    >
      <Text style={{ color: colors.textPrimary, fontSize: 18 }}>
        Página de Notificações
      </Text>
    </View>
  );
}

// --- PILHA DE NAVEGAÇÃO DO PERFIL ---
function ContaRoutes() {
  const { colors } = useContext(ThemeContext) as any;

  return (
    <ContaStack.Navigator
      screenOptions={{
        headerStyle: { backgroundColor: colors.surface },
        headerTintColor: colors.primary,
        headerTitleStyle: { fontWeight: "bold" },
      }}
    >
      <ContaStack.Screen
        name="MeuPerfil"
        component={Conta}
        options={{ headerShown: false }}
      />
      <ContaStack.Screen
        name="Definicoes"
        component={DefinicoesScreen}
        options={{ title: "Definições da Conta" }}
      />
      <ContaStack.Screen
        name="Notificacoes"
        component={NotificacoesScreen}
        options={{ title: "As minhas Notificações" }}
      />
    </ContaStack.Navigator>
  );
}

// --- ROTAS PRINCIPAIS (ABAS) ---
export function AppRoutes() {
  const { colors } = useContext(ThemeContext) as any;

  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          height: 65,
          paddingBottom: 10,
          paddingTop: 10,
        },
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textSecondary,
      }}
    >
      <Tab.Screen name="Início" component={Inicio} />
      <Tab.Screen name="Atividade" component={Atividade} />
      {/* Aqui a aba Conta agora chama a Pilha que criámos acima */}
      <Tab.Screen name="Conta" component={ContaRoutes} />
    </Tab.Navigator>
  );
}
