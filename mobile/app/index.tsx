import React from "react";
import { Redirect } from "expo-router";

// Entry point — redirect into the tab cockpit; the root nav handles the
// auth/biometric gate from there.
export default function Index() {
  return <Redirect href="/(tabs)" />;
}
