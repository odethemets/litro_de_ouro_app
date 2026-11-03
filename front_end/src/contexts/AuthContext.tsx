// src/contexts/AuthContext.tsx
import AsyncStorage from "@react-native-async-storage/async-storage";
import { createContext, useEffect, useState } from "react";

export const AuthContext = createContext({} as any);

export function AuthProvider({ children }: any) {
  const [token, setToken] = useState<string | null>(null);
  const [isLoadingAuth, setIsLoadingAuth] = useState(true);

  useEffect(() => {
    async function loadStorageData() {
      try {
        const storedToken = await AsyncStorage.getItem("@LitroDeOuro:token");
        if (storedToken) {
          setToken(storedToken);
        }
      } catch (error) {
        console.error("Erro ao carregar token do AsyncStorage:", error);
      } finally {
        setIsLoadingAuth(false);
      }
    }
    loadStorageData();
  }, []);

  const signIn = async (newToken: string) => {
    try {
      await AsyncStorage.setItem("@LitroDeOuro:token", newToken);
      setToken(newToken);
    } catch (error) {
      console.error("Erro ao guardar token:", error);
    }
  };

  const signOut = async () => {
    try {
      await AsyncStorage.removeItem("@LitroDeOuro:token");
    } catch (error) {
      console.error("Erro ao remover token:", error);
    } finally {
      // Garante que a aplicação comuta imediatamente para o Login
      setToken(null);
    }
  };

  return (
    <AuthContext.Provider value={{ token, isLoadingAuth, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}
