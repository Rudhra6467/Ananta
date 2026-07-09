import React from "react";
import { View, Text, Pressable, StyleSheet, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import type { MaterialTopTabBarProps } from "@react-navigation/material-top-tabs";
import { SwipeTabs } from "../../src/nav/SwipeTabs";
import { colors } from "../../src/theme";

const TABS: Record<string, { title: string; icon: keyof typeof Ionicons.glyphMap }> = {
  index: { title: "Cockpit", icon: "speedometer" },
  trade: { title: "Trade", icon: "swap-horizontal" },
  strategy: { title: "Strategy", icon: "git-branch" },
  research: { title: "Research", icon: "flask" },
  workspace: { title: "Workspace", icon: "options" },
};

function BottomBar({ state, navigation }: MaterialTopTabBarProps) {
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.bar, { height: 58 + insets.bottom, paddingBottom: insets.bottom || 8 }]}>
      {state.routes.map((route, i) => {
        const focused = state.index === i;
        const meta = TABS[route.name] || { title: route.name, icon: "ellipse" };
        const color = focused ? colors.teal : colors.textFaint;
        const onPress = () => {
          const event = navigation.emit({ type: "tabPress", target: route.key, canPreventDefault: true });
          if (!focused && !event.defaultPrevented) navigation.navigate(route.name);
        };
        return (
          <Pressable key={route.key} testID={`tab-${route.name}`} onPress={onPress} style={styles.item} hitSlop={6}>
            <View style={[styles.iconWrap, focused && styles.iconWrapActive]}>
              <Ionicons name={meta.icon} size={20} color={color} />
            </View>
            <Text style={[styles.label, { color }]}>{meta.title}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export default function TabsLayout() {
  return (
    <SwipeTabs
      tabBarPosition="bottom"
      tabBar={(props: MaterialTopTabBarProps) => <BottomBar {...props} />}
      screenOptions={{ swipeEnabled: true, lazy: true }}
    >
      <SwipeTabs.Screen name="index" options={{ title: "Cockpit" }} />
      <SwipeTabs.Screen name="trade" options={{ title: "Trade" }} />
      <SwipeTabs.Screen name="strategy" options={{ title: "Strategy" }} />
      <SwipeTabs.Screen name="research" options={{ title: "Research" }} />
      <SwipeTabs.Screen name="workspace" options={{ title: "Workspace" }} />
    </SwipeTabs>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: "row",
    backgroundColor: colors.bgElevated,
    borderTopColor: colors.cardBorder,
    borderTopWidth: 1,
    paddingTop: 6,
  },
  item: { flex: 1, alignItems: "center", justifyContent: "center", gap: 2 },
  iconWrap: { paddingHorizontal: 14, paddingVertical: 3, borderRadius: 999 },
  iconWrapActive: { backgroundColor: colors.tealGlow },
  label: { fontSize: 10, fontWeight: Platform.OS === "ios" ? "600" : "700" },
});
