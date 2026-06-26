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
        tabBarLabelStyle: { fontSize: 11, fontWeight: "600" },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Cockpit",
          tabBarIcon: ({ color, size }) => <Ionicons name="speedometer" size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="portfolio"
        options={{
          title: "Portfolio",
          tabBarIcon: ({ color, size }) => <Ionicons name="wallet" size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="reports"
        options={{
          title: "Reports",
          tabBarIcon: ({ color, size }) => <Ionicons name="analytics" size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: "Settings",
          tabBarIcon: ({ color, size }) => <Ionicons name="settings-sharp" size={size} color={color} />,
        }}
      />
    </Tabs>
  );
}
