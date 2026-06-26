// Ananta.AI — mobile design tokens.
// Operator's cockpit aesthetic: ultra-dark, calm, execution-focused.

export const colors = {
  bg: "#0A0E17", // ultra dark background
  bgElevated: "#0E1320",
  card: "#121824", // slate cards
  cardBorder: "#1C2536",
  cardPressed: "#161E2E",

  text: "#FFFFFF",
  textMuted: "#8A94A6",
  textFaint: "#5A6478",

  teal: "#14E0C9", // electric teal accent (also = gains)
  tealDim: "#0E9C8C",
  tealGlow: "rgba(20,224,201,0.12)",

  gold: "#E5B84B", // imperial gold — branding/logo ONLY

  red: "#FF5A6A", // losses / warnings
  redDim: "#B23B47",
  redGlow: "rgba(255,90,106,0.12)",

  amber: "#F2A93B", // caution states

  overlay: "rgba(5,8,14,0.72)",
};

// P&L semantic color: teal for positive/zero, red for negative.
export const pnlColor = (v: number) => (v >= 0 ? colors.teal : colors.red);

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
};

export const radius = {
  sm: 10,
  md: 16,
  lg: 22,
  pill: 999,
};

export const font = {
  // weights
  black: "800" as const,
  bold: "700" as const,
  semibold: "600" as const,
  medium: "500" as const,
  regular: "400" as const,
};

export const type = {
  hero: { fontSize: 44, fontWeight: font.black, color: colors.text, letterSpacing: -1 },
  h1: { fontSize: 30, fontWeight: font.bold, color: colors.text, letterSpacing: -0.5 },
  h2: { fontSize: 22, fontWeight: font.bold, color: colors.text },
  h3: { fontSize: 18, fontWeight: font.semibold, color: colors.text },
  body: { fontSize: 15, fontWeight: font.regular, color: colors.text },
  bodyMuted: { fontSize: 15, fontWeight: font.regular, color: colors.textMuted },
  label: { fontSize: 12, fontWeight: font.semibold, color: colors.textMuted, letterSpacing: 0.8, textTransform: "uppercase" as const },
  small: { fontSize: 13, fontWeight: font.regular, color: colors.textMuted },
};
