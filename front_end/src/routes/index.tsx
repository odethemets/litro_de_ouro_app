// src/routes/index.tsx
import { NavigationContainer } from "@react-navigation/native";
import { useContext } from "react";
import { ActivityIndicator, View } from "react-native";

import { AuthContext } from "../contexts/AuthContext";
import { AppRoutes } from "./app.routes"; // O seu TabNavigator (Início, Atividade, Conta)
import { AuthRoutes } from "./auth.routes";

export function Routes() {
  const { token, isLoadingAuth } = useContext(AuthContext);

  if (isLoadingAuth) {
    return (
      <View
        style={{
          flex: 1,
          justifyContent: "center",
          alignItems: "center",
          backgroundColor: "#121212",
        }}
      >
        <ActivityIndicator size="large" color="#F59E0B" />
      </View>
    );
  }

  return (
    <NavigationContainer>
      {/* Mágica acontece aqui: Se há token, mostra as Abas. Se não, mostra o Login */}
      {token ? <AppRoutes /> : <AuthRoutes />}
    </NavigationContainer>
  );
}
