'use client';

import React, { useEffect, useState, useRef } from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
} from 'recharts';
import { useTradeStore, StreamMetrics } from '@/lib/store/useTradeStore';

// Custom tooltip that shows full date + time + all values
const CustomTooltip = ({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color: string; dataKey: string }>;
  label?: number;
}) => {
  if (!active || !payload || payload.length === 0) return null;

  const formatDatetime = (tsNs: number) => {
    try {
      const d = new Date(tsNs / 1e6);
      return d.toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
    } catch { return ''; }
  };

  return (
    <div style={{
      backgroundColor: '#0d1117',
      border: '1px solid #1f242f',
      padding: '8px 10px',
      fontFamily: 'Geist Mono, monospace',
      fontSize: '11px',
      lineHeight: '1.6',
      color: '#e5e7eb',
    }}>
      <div style={{ color: '#6b7280', marginBottom: 4 }}>{formatDatetime(Number(label))}</div>
      {payload.map((p) => (
        <div key={p.dataKey} style={{ color: p.color, display: 'flex', justifyContent: 'space-between', gap: 12 }}>
          <span>{p.name}</span>
          <span style={{ fontWeight: 600 }}>
            {p.dataKey === 'cumulative_pnl' || p.dataKey === 'spot_price'
              ? `$${Number(p.value).toFixed(2)}`
              : p.dataKey === 'implied_vol'
                ? `${(Number(p.value) * 100).toFixed(1)}%`
                : Number(p.value).toFixed(4)}
          </span>
        </div>
      ))}
    </div>
  );
};

export default function TelemetryChart() {
  const [renderData, setRenderData] = useState<StreamMetrics[]>([]);
  const lastMetricsLengthRef = useRef<number>(0);
  const lastMetricsRef = useRef<StreamMetrics[]>([]);

  // Periodically read from Zustand store using requestAnimationFrame (30 FPS cap to save CPU)
  useEffect(() => {
    let animationFrameId: number;
    let lastRenderTime = 0;
    const fpsLimit = 1000 / 30; // 30 FPS cap

    const loop = (timestamp: number) => {
      const elapsed = timestamp - lastRenderTime;
      if (elapsed >= fpsLimit) {
        const currentMetrics = useTradeStore.getState().metrics;

        // Only trigger React state update if the data has actually changed
        if (currentMetrics.length !== lastMetricsLengthRef.current || currentMetrics !== lastMetricsRef.current) {
          lastMetricsLengthRef.current = currentMetrics.length;
          lastMetricsRef.current = currentMetrics;

          // Downsample data points to max 400 points for smooth rendering
          const maxRenderPoints = 400;
          if (currentMetrics.length > maxRenderPoints) {
            const factor = Math.ceil(currentMetrics.length / maxRenderPoints);
            const downsampled = currentMetrics.filter((_, idx) => idx % factor === 0 || idx === currentMetrics.length - 1);
            setRenderData(downsampled);
          } else {
            setRenderData(currentMetrics);
          }
          lastRenderTime = timestamp;
        }
      }
      animationFrameId = requestAnimationFrame(loop);
    };

    animationFrameId = requestAnimationFrame(loop);
    return () => { cancelAnimationFrame(animationFrameId); };
  }, []);

  if (renderData.length === 0) {
    return (
      <div className="absolute inset-0 flex items-center justify-center">
        <p className="text-sm text-[color:var(--text-muted)] uppercase tracking-wider">
          Waiting for telemetry data stream...
        </p>
      </div>
    );
  }

  // Format timestamp (from nanoseconds) to date + short time for X-axis ticks
  const formatXTick = (tsNs: number) => {
    try {
      const d = new Date(tsNs / 1e6);
      const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
      const dd = String(d.getUTCDate()).padStart(2, '0');
      const hh = String(d.getUTCHours()).padStart(2, '0');
      const min = String(d.getUTCMinutes()).padStart(2, '0');
      return `${mm}/${dd} ${hh}:${min}`;
    } catch { return ''; }
  };

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart
        data={renderData}
        margin={{ top: 5, right: 60, left: 10, bottom: 5 }}
      >
        <CartesianGrid stroke="#1a1f2e" strokeDasharray="3 3" />
        <XAxis
          dataKey="tick_timestamp_ns"
          tickFormatter={formatXTick}
          stroke="#374151"
          tick={{ fill: '#6b7280', fontSize: 9, fontFamily: 'Geist Mono' }}
          interval="preserveStartEnd"
          minTickGap={60}
        />
        <YAxis
          yAxisId="pnl"
          stroke="#22c55e"
          tick={{ fill: '#22c55e', fontSize: 9, fontFamily: 'Geist Mono' }}
          domain={['auto', 'auto']}
          tickFormatter={(v: number) => `$${v.toFixed(0)}`}
          width={60}
        />
        <YAxis
          yAxisId="spot"
          orientation="right"
          stroke="#94a3b8"
          tick={{ fill: '#94a3b8', fontSize: 9, fontFamily: 'Geist Mono' }}
          domain={['auto', 'auto']}
          tickFormatter={(v: number) => `$${v.toFixed(0)}`}
          width={55}
        />
        <YAxis
          yAxisId="greek"
          orientation="right"
          stroke="#f59e0b"
          tick={false}
          tickLine={false}
          axisLine={false}
          domain={['auto', 'auto']}
          width={0}
        />
        {/* Zero reference line for PnL */}
        <ReferenceLine yAxisId="pnl" y={0} stroke="#374151" strokeDasharray="4 4" strokeWidth={1} />
        <Tooltip content={<CustomTooltip />} />
        <Legend
          wrapperStyle={{ fontSize: '10px', fontFamily: 'Geist', paddingTop: '4px' }}
        />
        <Line
          yAxisId="pnl"
          type="monotone"
          dataKey="cumulative_pnl"
          name="Cum. PnL ($)"
          stroke="#22c55e"
          dot={false}
          activeDot={{ r: 3, fill: '#22c55e' }}
          strokeWidth={1.5}
          isAnimationActive={false}
        />
        <Line
          yAxisId="spot"
          type="monotone"
          dataKey="spot_price"
          name="Spot ($)"
          stroke="#94a3b8"
          dot={false}
          activeDot={{ r: 3, fill: '#94a3b8' }}
          strokeWidth={1.0}
          isAnimationActive={false}
        />
        <Line
          yAxisId="greek"
          type="monotone"
          dataKey="delta"
          name="Delta"
          stroke="#f59e0b"
          dot={false}
          activeDot={{ r: 3, fill: '#f59e0b' }}
          strokeWidth={1.0}
          isAnimationActive={false}
        />
        <Line
          yAxisId="greek"
          type="monotone"
          dataKey="implied_vol"
          name="IV"
          stroke="#818cf8"
          dot={false}
          activeDot={{ r: 3, fill: '#818cf8' }}
          strokeWidth={0.8}
          isAnimationActive={false}
          strokeDasharray="3 3"
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
