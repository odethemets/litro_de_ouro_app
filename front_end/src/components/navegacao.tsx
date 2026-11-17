import Ionicons from "@expo/vector-icons/Ionicons";
import type { BottomTabBarProps } from "@react-navigation/bottom-tabs";
import { useState } from "react";
import { Pressable, Text, useWindowDimensions, View } from "react-native";
import { design } from "../theme/design";
import { Brand, useAppTheme } from "./design";

const icons = {
  Feed: "list-outline",
  Mapa: "map-outline",
  Adicionar: "add",
  IA: "sparkles-outline",
  Perfil: "person-outline",
} as const;

export function Navegacao({ state, navigation, insets }: BottomTabBarProps) {
  const { colors } = useAppTheme();
  const desktop = useWindowDimensions().width >= design.desktop;

  const [focusedKey, setFocusedKey] = useState<string | null>(null);

  return (
    <View
      testID={desktop ? "navegacao-desktop" : "navegacao-mobile"}
      style={{
        backgroundColor: colors.surface,
        borderColor: colors.border,
        borderTopWidth: desktop ? 0 : 1,
        borderRightWidth: desktop ? 1 : 0,
        width: desktop ? 224 : undefined,
        padding: desktop ? 16 : 6,
        paddingTop: desktop ? Math.max(insets.top, 24) : 8,
        paddingBottom: desktop ? 24 : Math.max(insets.bottom, 8),
        gap: desktop ? 24 : 0,
      }}
    >
      {desktop ? <Brand compact /> : null}

      <View
        accessibilityRole="tablist"
        style={{
          flexDirection: desktop ? "column" : "row",
          gap: desktop ? 8 : 0,
        }}
      >
        {state.routes.map((route, index) => {
          const active = state.index === index;
          const name = route.name as keyof typeof icons;

          return (
            <Pressable
              key={route.key}
              accessibilityRole="tab"
              accessibilityLabel={"Aba " + route.name}
              accessibilityState={{ selected: active }}
              aria-selected={active}
              onFocus={() => setFocusedKey(route.key)}
              onBlur={() => setFocusedKey(null)}
              onPress={() => {
                const event = navigation.emit({
                  type: "tabPress",
                  target: route.key,
                  canPreventDefault: true,
                });

                if (!event.defaultPrevented) {
                  navigation.navigate(
                    route.name,
                    route.name === "Perfil" ? undefined : route.params,
                  );
                }
              }}
              onLongPress={() =>
                navigation.emit({
                  type: "tabLongPress",
                  target: route.key,
                })
              }
              style={({ pressed }) => ({
                flex: desktop ? undefined : 1,
                minHeight: 56,
                padding: desktop ? 14 : 4,
                alignItems: "center",
                justifyContent: desktop ? "flex-start" : "center",
                flexDirection: desktop ? "row" : "column",
                gap: 6,
                borderRadius: 14,
                backgroundColor: active ? colors.selection : colors.surface,
                borderWidth: 2,
                borderColor:
                  focusedKey === route.key ? colors.focus : "transparent",
                opacity: pressed ? 0.75 : 1,
              })}
            >
              <View
                style={{
                  padding: name === "Adicionar" ? 4 : 0,
                  borderRadius: 24,
                  backgroundColor:
                    name === "Adicionar" ? colors.primary : "transparent",
                }}
              >
                <Ionicons
                  name={icons[name]}
                  size={24}
                  color={
                    name === "Adicionar"
                      ? colors.primaryText
                      : active
                        ? colors.textPrimary
                        : colors.textSecondary
                  }
                />
              </View>

              <Text
                style={{
                  color: active ? colors.textPrimary : colors.textSecondary,
                  fontSize: desktop ? 16 : 12,
                  fontWeight: active ? "700" : "500",
                  textAlign: "center",
                }}
              >
                {route.name}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}
