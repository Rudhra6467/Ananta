import { useEffect, useRef } from "react";
import { createChart, CandlestickSeries } from "lightweight-charts";

// Wide, uncluttered candlestick view (lightweight-charts) styled for the matte
// silver Ananta theme. Pass an array of {t, open, high, low, close}.
export default function CandleChart({ candles = [], height = 420 }) {
    const containerRef = useRef(null);
    const chartRef = useRef(null);
    const seriesRef = useRef(null);

    useEffect(() => {
        if (!containerRef.current) return;
        const chart = createChart(containerRef.current, {
            height,
            layout: {
                background: { color: "transparent" },
                textColor: "#878E99",
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 10,
            },
            localization: { locale: "en-US" },
            grid: {
                vertLines: { color: "rgba(42,45,53,0.5)" },
                horzLines: { color: "rgba(42,45,53,0.5)" },
            },
            rightPriceScale: { borderColor: "#2A2D35" },
            timeScale: { borderColor: "#2A2D35", timeVisible: true, secondsVisible: false },
            crosshair: {
                vertLine: { color: "#5C6370", labelBackgroundColor: "#1A1D24" },
                horzLine: { color: "#5C6370", labelBackgroundColor: "#1A1D24" },
            },
            handleScale: false,
            handleScroll: false,
        });
        const series = chart.addSeries(CandlestickSeries, {
            upColor: "#10B981",
            downColor: "#F43F5E",
            borderUpColor: "#10B981",
            borderDownColor: "#F43F5E",
            wickUpColor: "#10B981",
            wickDownColor: "#F43F5E",
        });
        chartRef.current = chart;
        seriesRef.current = series;

        const ro = new ResizeObserver(() => {
            if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth });
        });
        ro.observe(containerRef.current);
        chart.applyOptions({ width: containerRef.current.clientWidth });

        return () => {
            ro.disconnect();
            chart.remove();
            chartRef.current = null;
            seriesRef.current = null;
        };
    }, [height]);

    useEffect(() => {
        if (!seriesRef.current || !candles.length) return;
        const data = candles
            .map((c) => ({
                time: Math.floor(c.t / 1000),
                open: c.open,
                high: c.high,
                low: c.low,
                close: c.close,
            }))
            .sort((a, b) => a.time - b.time);
        seriesRef.current.setData(data);
        chartRef.current && chartRef.current.timeScale().fitContent();
    }, [candles]);

    return <div ref={containerRef} style={{ width: "100%", height }} data-testid="candle-chart" />;
}
