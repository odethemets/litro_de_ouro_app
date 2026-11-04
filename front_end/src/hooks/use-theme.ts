import { Colors } from "@/constants/theme";
import { useColorScheme } from "@/hooks/use-color-scheme";

export function useTheme() {
  const scheme = useColorScheme();

  // Quando o sistema não informar um tema, utiliza o claro.
  const theme = scheme ?? "light";

  return Colors[theme];
}
