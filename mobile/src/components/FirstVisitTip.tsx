import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { getItem, setItem } from "../storage";
import { colors, spacing, radius } from "../theme";

// Progressive first-visit hint — shows once per key, dismissible, persisted.
export function FirstVisitTip({ tipKey, text }: { tipKey: string; text: string }) {
  const [show, setShow] = useState(false);
  const storeKey = `ananta_tip_${tipKey}`;
  useEffect(() => {
    getItem(storeKey).then((v) => setShow(v !== "1")).catch(() => setShow(true));
  }, [storeKey]);
  if (!show) return null;
  const dismiss = () => { setShow(false); setItem(storeKey, "1").catch(() => {}); };
  return (
    <View style={styles.wrap} testID={`tip-${tipKey}`}>
      <Ionicons name="bulb" size={15} color={colors.amber} />
      <Text style={styles.txt}>Tip: {text}</Text>
      <Pressable testID={`tip-dismiss-${tipKey}`} onPress={dismiss} hitSlop={8}><Ionicons name="close" size={16} color={colors.textMuted} /></Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: "rgba(242,169,59,0.08)", borderWidth: 1, borderColor: "rgba(242,169,59,0.3)", borderRadius: radius.sm, paddingVertical: spacing.sm, paddingHorizontal: spacing.md, marginBottom: spacing.sm },
  txt: { flex: 1, color: colors.text, fontSize: 12 },
});
