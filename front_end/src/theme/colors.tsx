export const cores = {
  light: {
    background: "#F5F6FA",
    surface: "#FFFFFF",
    input: "#F5F6FA",
    textPrimary: "#171923",
    textSecondary: "#596273",
    primary: "#FFC400",
    primaryText: "#171923",
    selection: "#FFF4BD",
    danger: "#B42318",
    success: "#166534",
    border: "#D3D8E1",
    focus: "#1D4ED8",
  },
  dark: {
    background: "#111318",
    surface: "#1C2028",
    input: "#252B35",
    textPrimary: "#F3F4F6",
    textSecondary: "#B9C0CC",
    primary: "#FFC400",
    primaryText: "#171923",
    selection: "#403710",
    danger: "#FDA29B",
    success: "#86EFAC",
    border: "#495363",
    focus: "#93C5FD",
  },
};
export type ThemeType = "light" | "dark";
export type AppThemeMode = ThemeType | "system";
export type ThemeColors = typeof cores.light;
export const isThemeMode = (value: unknown): value is AppThemeMode =>
  value === "light" || value === "dark" || value === "system";
