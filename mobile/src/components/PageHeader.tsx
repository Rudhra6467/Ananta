import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { colors, spacing, type } from "../theme";

// Consistent screen header with the web "one question per page" line.
export function PageHeader({ title, question, right }: { title: string; question: string; right?: React.ReactNode }) {
  return (
    <View style={styles.wrap}>
      <View style={{ flex: 1 }}>
        <Text style={styles.question} testID="page-question">{question}</Text>
        <Text style={[type.h1, { marginTop: 2 }]}>{title}</Text>
      </View>
      {right}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between", marginBottom: spacing.md },
  question: { fontSize: 11, fontWeight: "600", letterSpacing: 0.8, textTransform: "uppercase", color: colors.teal },
});
