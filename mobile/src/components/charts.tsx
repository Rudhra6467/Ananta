import React from "react";
import { View } from "react-native";
import Svg, { Path, Line, Rect, Defs, LinearGradient, Stop, Circle } from "react-native-svg";
import { colors } from "../theme";

// ---------- Sparkline: tiny trend line for snapshot cards ----------
export function Sparkline({
  data,
  width = 64,
  height = 28,
  color,
}: {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
}) {
  if (!data || data.length < 2) return <View style={{ width, height }} />;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const stepX = width / (data.length - 1);
  const pts = data.map((v, i) => {
    const x = i * stepX;
    const y = height - ((v - min) / span) * height;
    return [x, y];
  });
  const stroke = color ?? (data[data.length - 1] >= data[0] ? colors.teal : colors.red);
  const d = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(2)},${p[1].toFixed(2)}`).join(" ");
  return (
    <Svg width={width} height={height}>
      <Path d={d} stroke={stroke} strokeWidth={1.8} fill="none" strokeLinejoin="round" strokeLinecap="round" />
    </Svg>
  );
}

// ---------- Equity curve: area chart for performance tab ----------
export function EquityCurve({
  data,
  width,
  height = 180,
  color = colors.teal,
}: {
  data: number[];
  width: number;
  height?: number;
  color?: string;
}) {
  if (!data || data.length < 2) return <View style={{ width, height }} />;
  const pad = 6;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const w = width - pad * 2;
  const h = height - pad * 2;
  const stepX = w / (data.length - 1);
  const pts = data.map((v, i) => {
    const x = pad + i * stepX;
    const y = pad + (h - ((v - min) / span) * h);
    return [x, y];
  });
  const line = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(2)},${p[1].toFixed(2)}`).join(" ");
  const area = `${line} L${pts[pts.length - 1][0].toFixed(2)},${height - pad} L${pts[0][0].toFixed(2)},${height - pad} Z`;
  return (
    <Svg width={width} height={height}>
      <Defs>
        <LinearGradient id="eqgrad" x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor={color} stopOpacity={0.28} />
          <Stop offset="1" stopColor={color} stopOpacity={0} />
        </LinearGradient>
      </Defs>
      <Path d={area} fill="url(#eqgrad)" />
      <Path d={line} stroke={color} strokeWidth={2.2} fill="none" strokeLinejoin="round" strokeLinecap="round" />
      <Circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r={3.5} fill={color} />
    </Svg>
  );
}

// ---------- Candlestick chart: native SVG, asset detail ----------
type Candle = { t: number; open: number; high: number; low: number; close: number };

export function CandleChart({
  candles,
  width,
  height = 240,
}: {
  candles: Candle[];
  width: number;
  height?: number;
}) {
  if (!candles || candles.length < 2) return <View style={{ width, height }} />;
  const pad = 8;
  const w = width - pad * 2;
  const h = height - pad * 2;
  const highs = candles.map((c) => c.high);
  const lows = candles.map((c) => c.low);
  const max = Math.max(...highs);
  const min = Math.min(...lows);
  const span = max - min || 1;
  const slot = w / candles.length;
  const bodyW = Math.max(2, slot * 0.6);
  const y = (v: number) => pad + (h - ((v - min) / span) * h);

  return (
    <Svg width={width} height={height}>
      {candles.map((c, i) => {
        const cx = pad + i * slot + slot / 2;
        const up = c.close >= c.open;
        const fill = up ? colors.teal : colors.red;
        const top = y(Math.max(c.open, c.close));
        const bot = y(Math.min(c.open, c.close));
        const bodyH = Math.max(1, bot - top);
        return (
          <React.Fragment key={i}>
            <Line x1={cx} y1={y(c.high)} x2={cx} y2={y(c.low)} stroke={fill} strokeWidth={1} />
            <Rect x={cx - bodyW / 2} y={top} width={bodyW} height={bodyH} fill={fill} rx={1} />
          </React.Fragment>
        );
      })}
    </Svg>
  );
}
