import React from "react";
import { Tabs } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { Platform } from "react-native";
import { colors } from "../../src/theme";

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.teal,
        tabBarInactiveTintColor: colors.textFaint,
        tabBarStyle: {
          backgroundColor: colors.bgElevated,
          borderTopColor: colors.cardBorder,
          borderTopWidth: 1,
          height: Platform.OS === "ios" ? 88 : 64,
          paddingTop: 6,
          paddingBottom: Platform.OS === "ios" ? 28 : 8,
        },
        tabBarLabelStyle: { fontSize: 10, fontWeight: "600" },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{ title: "Cockpit", tabBarIcon: ({ color, size }) => <Ionicons name="speedometer" size={size} color={color} /> }}
      />
      <Tabs.Screen
        name="trade"
        options={{ title: "Trade", tabBarIcon: ({ color, size }) => <Ionicons name="swap-horizontal" size={size} color={color} /> }}
      />
      <Tabs.Screen
        name="strategy"
        options={{ title: "Strategy", tabBarIcon: ({ color, size }) => <Ionicons name="git-branch" size={size} color={color} /> }}
      />
      <Tabs.Screen
        name="research"
        options={{ title: "Research", tabBarIcon: ({ color, size }) => <Ionicons name="flask" size={size} color={color} /> }}
      />
      <Tabs.Screen
        name="workspace"
        options={{ title: "Workspace", tabBarIcon: ({ color, size }) => <Ionicons name="options" size={size} color={color} /> }}
      />
    </Tabs>
  );
}
