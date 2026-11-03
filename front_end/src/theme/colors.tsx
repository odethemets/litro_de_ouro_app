// src/theme/colors.ts

export const cores = {
  light: {
    background: "#F5F5F5", // Fundo base claro
    surface: "#FFFFFF", // Fundo de cartões, inputs e Bottom Sheets
    textPrimary: "#121212", // Texto principal escuro
    textSecondary: "#666666", // Texto secundário e placeholders
    primary: "#FFC107", // Dourado Litro de Ouro (Destaque)
    danger: "#F44336", // Vermelho para SOS e erros
    success: "#4CAF50", // Verde para sucesso e preços baixos
    border: "#E0E0E0", // Linhas divisórias subtis
  },
  dark: {
    background: "#121212", // Fundo base escuro (Estilo Uber)
    surface: "#1E1E1E", // Fundo de cartões, inputs e Bottom Sheets
    textPrimary: "#FFFFFF", // Texto principal branco
    textSecondary: "#B3B3B3", // Texto secundário e placeholders
    primary: "#FFC107", // Dourado Litro de Ouro (Destaque)
    danger: "#EF5350", // Vermelho para SOS e erros (tom mais suave para dark mode)
    success: "#66BB6A", // Verde para sucesso (tom mais suave para dark mode)
    border: "#333333", // Linhas divisórias escuras
  },
};

export type ThemeType = "light" | "dark";
export type AppThemeMode = "light" | "dark" | "system";
