'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import PageLayout from '@/app/components/PageLayout';
import TerminalSelect from '@/app/components/TerminalSelect';
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
  Brush,
} from 'recharts';

// ─── Types ────────────────────────────────────────────────────────────────────

interface StrategyRow {
  strategy_name: string;
  class_name: string;
  portfolio: string;
  status: string;
}

type StrategySetting = Record<string, number>;

interface TelemetryPoint {
  ts: number;          // ms epoch
  pnl: number;
  delta: number;
  gamma: number;
  theta: number;
  spot: number | null;
}

interface OrderTrade {
  id?: number | string;
  record_type?: string;
  strategy_name?: string;
  symbol?: string;
  direction?: string;
  volume?: number | null;
  traded?: number | null;
  price?: number | null;
  status?: string;
  timestamp?: string;
  [key: string]: unknown;
}

interface Holding {
  underlying?: {
    quantity?: number;
    market_price?: number;
    [key: string]: unknown;
  };
  options?: Record<string, {
    quantity?: number;
    [key: string]: unknown;
  }>;
  summary?: {
    pnl?: number;
    delta?: number;
    gamma?: number;
    theta?: number;
    vega?: number;
    rho?: number;
  };
  spot_price?: number;
  [key: string]: unknown;
}

// ─── MetricCard ─────────────────────────────────────────────────────────────

function MetricCard({
  label,
  children,
  valueClassName,
}: {
  label: string;
  children: React.ReactNode;
  valueClassName?: string;
}) {
  return (
    <div className="panel px-2 py-2">
      <p className="text-[10px] uppercase tracking-wide text-[color:var(--text-muted)] mb-1">
        {label}
      </p>
      <p
        className={`leading-none font-semibold numeric-12 ${valueClassName ?? 'text-base text-[color:var(--text-primary)]'}`}
      >
        {children}
      </p>
    </div>
  );
}

// ─── Live Telemetry Tooltip ───────────────────────────────────────────────────

const LiveTooltip = ({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color: string; dataKey: string }>;
  label?: number;
}) => {
  if (!active || !payload || payload.length === 0) return null;
  const ts = label ? new Date(label).toLocaleTimeString() : '';
  return (
    <div
      style={{
        backgroundColor: '#0d1117',
        border: '1px solid #1f242f',
        padding: '8px 10px',
        fontFamily: 'Geist Mono, monospace',
        fontSize: '11px',
        lineHeight: '1.6',
        color: '#e5e7eb',
      }}
    >
      <div style={{ color: '#6b7280', marginBottom: 4 }}>{ts}</div>
      {payload.map((p) => (
        <div
          key={p.dataKey}
          style={{ color: p.color, display: 'flex', justifyContent: 'space-between', gap: 12 }}
        >
          <span>{p.name}</span>
          <span style={{ fontWeight: 600 }}>
            {p.dataKey === 'pnl' || p.dataKey === 'spot'
              ? `$${Number(p.value).toFixed(2)}`
              : Number(p.value).toFixed(4)}
          </span>
        </div>
      ))}
    </div>
  );
};

// ─── Live Telemetry Chart ─────────────────────────────────────────────────────

function LiveTelemetryChart({ data }: { data: TelemetryPoint[] }) {
  if (data.length === 0) {
    return (
      <div className="absolute inset-0 flex items-center justify-center">
        <p className="text-sm text-[color:var(--text-muted)] uppercase tracking-wider">
          Waiting for live telemetry…
        </p>
      </div>
    );
  }

  const formatXTick = (ms: number) => {
    try {
      const d = new Date(ms);
      const hh = String(d.getHours()).padStart(2, '0');
      const mm = String(d.getMinutes()).padStart(2, '0');
      const ss = String(d.getSeconds()).padStart(2, '0');
      return `${hh}:${mm}:${ss}`;
    } catch {
      return '';
    }
  };

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 5, right: 60, left: 10, bottom: 5 }}>
        <CartesianGrid stroke="#1a1f2e" strokeDasharray="3 3" />
        <XAxis
          dataKey="ts"
          tickFormatter={formatXTick}
          stroke="#374151"
          tick={{ fill: '#6b7280', fontSize: 9, fontFamily: 'Geist Mono' }}
          interval="preserveStartEnd"
          minTickGap={60}
        />
        {/* Left Y-axis: PnL */}
        <YAxis
          yAxisId="pnl"
          stroke="#22c55e"
          tick={{ fill: '#22c55e', fontSize: 9, fontFamily: 'Geist Mono' }}
          domain={['auto', 'auto']}
          tickFormatter={(v: number) => `$${v.toFixed(0)}`}
          width={60}
        />
        {/* Right Y-axis: Spot */}
        <YAxis
          yAxisId="spot"
          orientation="right"
          stroke="#94a3b8"
          tick={{ fill: '#94a3b8', fontSize: 9, fontFamily: 'Geist Mono' }}
          domain={['auto', 'auto']}
          tickFormatter={(v: number) => `$${v.toFixed(0)}`}
          width={55}
        />
        {/* Right Y-axis (hidden): Greeks */}
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
        <ReferenceLine yAxisId="pnl" y={0} stroke="#374151" strokeDasharray="4 4" strokeWidth={1} />
        <Tooltip content={<LiveTooltip />} />
        <Legend wrapperStyle={{ fontSize: '10px', fontFamily: 'Geist', paddingTop: '4px' }} />

        <Line
          yAxisId="pnl"
          type="monotone"
          dataKey="pnl"
          name="uPnL ($)"
          stroke="#22c55e"
          dot={false}
          activeDot={{ r: 3 }}
          strokeWidth={1.5}
          isAnimationActive={false}
        />
        <Line
          yAxisId="spot"
          type="monotone"
          dataKey="spot"
          name="Spot ($)"
          stroke="#94a3b8"
          dot={false}
          activeDot={{ r: 3 }}
          strokeWidth={1.0}
          isAnimationActive={false}
          connectNulls
        />
        <Line
          yAxisId="greek"
          type="monotone"
          dataKey="delta"
          name="Delta"
          stroke="#f59e0b"
          dot={false}
          strokeWidth={1.0}
          isAnimationActive={false}
        />
        <Line
          yAxisId="greek"
          type="monotone"
          dataKey="gamma"
          name="Gamma"
          stroke="#a855f7"
          dot={false}
          strokeWidth={1.0}
          isAnimationActive={false}
        />
        <Line
          yAxisId="greek"
          type="monotone"
          dataKey="theta"
          name="Theta"
          stroke="#818cf8"
          dot={false}
          strokeWidth={0.8}
          isAnimationActive={false}
          strokeDasharray="3 3"
        />
        <Brush dataKey="ts" tickFormatter={formatXTick} height={15} stroke="#374151" fill="#0d1117" />
      </LineChart>
    </ResponsiveContainer>
  );
}

// â”€â”€â”€ Main Page â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const MAX_HISTORY = 200;

export default function StrategyManagerPage() {
  const [strategies, setStrategies] = useState<StrategyRow[]>([]);
  const [loadingStrategies, setLoadingStrategies] = useState(false);
  const [selectedStrategy, setSelectedStrategy] = useState<string | null>(null);
  const [strategyClasses, setStrategyClasses] = useState<string[]>([]);
  const [selectedClass, setSelectedClass] = useState<string>('');
  const [portfolios, setPortfolios] = useState<string[]>([]);
  const [selectedPortfolio, setSelectedPortfolio] = useState<string>('__custom__');
  const [customPortfolioName, setCustomPortfolioName] = useState<string>('');
  const [settingsByClass, setSettingsByClass] = useState<Record<string, StrategySetting>>({});
  const [configOpen, setConfigOpen] = useState(false);
  const [configForClass, setConfigForClass] = useState<string | null>(null);
  const [pendingSetting, setPendingSetting] = useState<{ key: string; value: string }[]>([]);

  // Live holdings (latest snapshot, keyed by strategy name)
  const [holdings, setHoldings] = useState<Record<string, Holding>>({});

  // Telemetry history per strategy (capped at MAX_HISTORY points)
  const [history, setHistory] = useState<Record<string, TelemetryPoint[]>>({});

  // Orders & Trades from DB (latest 200 for the selected strategy)
  const [ordersTrades, setOrdersTrades] = useState<OrderTrade[]>([]);

  // Connection Health Heartbeat State
  const [isBackendConnected, setIsBackendConnected] = useState(true);

  // ── Resize state ───────────────────────────────────────────────────────────
  // leftW: width of left panel in px; chartH: height of chart in px
  const [leftW, setLeftW] = useState(420);
  const [chartH, setChartH] = useState(200);
  const leftWRef = useRef(420);
  const chartHRef = useRef(200);
  const draggingRef = useRef<null | 'col' | 'row'>(null);
  const dragStartRef = useRef({ x: 0, y: 0, leftW: 420, chartH: 200 });

  useEffect(() => {
    const savedLeftW = localStorage.getItem('leftW');
    const savedChartH = localStorage.getItem('chartH');
    if (savedLeftW) {
      const parsed = parseInt(savedLeftW, 10);
      setLeftW(parsed);
      leftWRef.current = parsed;
    }
    if (savedChartH) {
      const parsed = parseInt(savedChartH, 10);
      setChartH(parsed);
      chartHRef.current = parsed;
    }
  }, []);

  const changeLeftW = (w: number) => {
    leftWRef.current = w;
    setLeftW(w);
  };

  const changeChartH = (h: number) => {
    chartHRef.current = h;
    setChartH(h);
  };

  const onMouseDownCol = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    draggingRef.current = 'col';
    dragStartRef.current = { x: e.clientX, y: e.clientY, leftW, chartH };
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [leftW, chartH]);

  const onMouseDownRow = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    draggingRef.current = 'row';
    dragStartRef.current = { x: e.clientX, y: e.clientY, leftW, chartH };
    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';
  }, [leftW, chartH]);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!draggingRef.current) return;
      if (draggingRef.current === 'col') {
        const dx = e.clientX - dragStartRef.current.x;
        changeLeftW(Math.max(260, Math.min(760, dragStartRef.current.leftW + dx)));
      } else {
        const dy = e.clientY - dragStartRef.current.y;
        changeChartH(Math.max(100, Math.min(500, dragStartRef.current.chartH + dy)));
      }
    };
    const onUp = () => {
      if (draggingRef.current) {
        localStorage.setItem('leftW', String(leftWRef.current));
        localStorage.setItem('chartH', String(chartHRef.current));
      }
      draggingRef.current = null;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, []);

  // ── Fetch helpers ──────────────────────────────────────────────────────────

  const fetchStrategies = useCallback(async () => {
    setLoadingStrategies(true);
    try {
      const data = await api.get<{ strategies?: StrategyRow[] }>('/api/strategies');
      const list: StrategyRow[] = data.strategies || [];
      setStrategies(list);
      setSelectedStrategy((prev) => prev || (list[0]?.strategy_name ?? null));
      setIsBackendConnected(true);
    } catch (e) {
      console.error('Error loading strategies', e);
      setIsBackendConnected(false);
    } finally {
      setLoadingStrategies(false);
    }
  }, []);

  const fetchHoldings = useCallback(async () => {
    try {
      const data = await api.get<{ holdings?: Record<string, Holding> }>('/api/strategies/holdings');
      setIsBackendConnected(true);
      if (data.holdings) {
        setHoldings(data.holdings);

        // Accumulate telemetry history
        const now = Date.now();
        setHistory((prev) => {
          const next = { ...prev };
          for (const [name, h] of Object.entries(data.holdings!)) {
            const point: TelemetryPoint = {
              ts: now,
              pnl: h?.summary?.pnl ?? 0,
              delta: h?.summary?.delta ?? 0,
              gamma: h?.summary?.gamma ?? 0,
              theta: h?.summary?.theta ?? 0,
              spot: h?.underlying?.market_price ?? h?.spot_price ?? null,
            };
            const existing = prev[name] ?? [];
            const updated = [...existing, point];
            next[name] = updated.length > MAX_HISTORY ? updated.slice(updated.length - MAX_HISTORY) : updated;
          }
          return next;
        });
      }
    } catch (e) {
      console.warn('Failed to fetch strategy holdings', e);
      setIsBackendConnected(false);
    }
  }, []);

  const fetchOrdersTrades = useCallback(async (strategyName: string | null) => {
    try {
      const path = strategyName
        ? `/api/orders-trades/db?limit=200&strategy=${encodeURIComponent(strategyName)}`
        : '/api/orders-trades/db?limit=200';
      const data = await api.get<{ records?: OrderTrade[]; orders?: OrderTrade[]; trades?: OrderTrade[] }>(path);
      setIsBackendConnected(true);
      // Backend may return records, orders, or trades key
      const records = data.records ?? data.orders ?? data.trades ?? [];
      setOrdersTrades(Array.isArray(records) ? records : []);
    } catch (e) {
      console.warn('Failed to fetch orders & trades', e);
      setIsBackendConnected(false);
    }
  }, []);

  const fetchStrategyClasses = useCallback(async () => {
    try {
      const data = await api.get<{ classes?: string[] }>('/api/strategies/meta/strategy-classes');
      const classes: string[] = data.classes || [];
      setStrategyClasses(classes);
      setSelectedClass((prev) => prev || (classes[0] ?? ''));
    } catch (e) {
      console.warn('Failed to load strategy classes', e);
      setStrategyClasses([]);
      setSelectedClass('');
    }
  }, []);

  // ── Effects ────────────────────────────────────────────────────────────────

  useEffect(() => {
    void fetchStrategies();
    void fetchStrategyClasses();
    void fetchHoldings();

    (async () => {
      try {
        const data = await api.get<{ portfolios?: string[] }>('/api/strategies/meta/portfolios');
        const pf: string[] = data.portfolios || [];
        setPortfolios(pf);
        setSelectedPortfolio((prev) => prev || (pf[0] ?? '__custom__'));
      } catch { /* ignore */ }
    })();

    const stratInterval = setInterval(() => { void fetchStrategies(); }, 5000);
    const holdingsInterval = setInterval(() => { void fetchHoldings(); }, 2000);

    return () => {
      clearInterval(stratInterval);
      clearInterval(holdingsInterval);
    };
  }, [fetchStrategies, fetchStrategyClasses, fetchHoldings]);

  // Fetch orders & trades whenever selected strategy changes, then refresh every 5s
  useEffect(() => {
    void fetchOrdersTrades(selectedStrategy);
    const interval = setInterval(() => { void fetchOrdersTrades(selectedStrategy); }, 5000);
    return () => clearInterval(interval);
  }, [selectedStrategy, fetchOrdersTrades]);

  const exportTelemetryCSV = () => {
    if (selHistory.length === 0) {
      alert("No telemetry data to export.");
      return;
    }
    const headers = ["Timestamp", "uPnL", "Delta", "Gamma", "Theta", "Spot"];
    const rows = selHistory.map((p) => [
      new Date(p.ts).toISOString(),
      p.pnl,
      p.delta,
      p.gamma,
      p.theta,
      p.spot ?? "",
    ]);
    const csvContent =
      "data:text/csv;charset=utf-8," +
      [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `${selectedStrategy}_telemetry.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const exportOrdersCSV = () => {
    if (ordersTrades.length === 0) {
      alert("No orders/trades data to export.");
      return;
    }
    const headers = ["Type", "Symbol", "Direction", "Volume", "Traded", "Price", "Status", "Timestamp"];
    const rows = ordersTrades.map((r) => [
      r.record_type ?? "",
      r.symbol ?? "",
      r.direction ?? "",
      r.volume ?? "",
      r.traded ?? "",
      r.price ?? "",
      r.status ?? "",
      r.timestamp ?? "",
    ]);
    const csvContent =
      "data:text/csv;charset=utf-8," +
      [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `${selectedStrategy}_orders_trades.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // ── Derived metrics for selected strategy ──────────────────────────────────

  const selHolding = selectedStrategy ? holdings[selectedStrategy] : null;
  const selHistory = selectedStrategy ? (history[selectedStrategy] ?? []) : [];

  const latestPnl = selHolding?.summary?.pnl ?? null;
  const latestDelta = selHolding?.summary?.delta ?? null;
  const latestGamma = selHolding?.summary?.gamma ?? null;
  const latestTheta = selHolding?.summary?.theta ?? null;
  const totalTrades = ordersTrades.filter((r) => (r.record_type ?? '').toLowerCase() === 'trade').length;
  // 'traded' is the filled quantity; fees not tracked separately in this schema
  const totalVolume = ordersTrades
    .filter((r) => (r.record_type ?? '').toLowerCase() === 'trade')
    .reduce((sum, r) => sum + (typeof r.traded === 'number' ? r.traded : 0), 0);

  // ── Position summary helper ────────────────────────────────────────────────

  const getPositionSummary = (h?: Holding | null) => {
    if (!h) return '-';
    const parts: string[] = [];
    if (h.underlying?.quantity) parts.push(`${h.underlying.quantity} STK`);
    if (h.options) {
      let optQty = 0;
      for (const k of Object.keys(h.options)) optQty += h.options[k].quantity || 0;
      if (optQty !== 0) parts.push(`${optQty} OPT`);
    }
    return parts.length > 0 ? parts.join(', ') : 'Flat';
  };

  // ── Strategy lifecycle helpers ─────────────────────────────────────────────

  const withSelected = (fn: (name: string) => Promise<void>) => async () => {
    if (!selectedStrategy) { alert('Please select a strategy first'); return; }
    await fn(selectedStrategy);
    await fetchStrategies();
  };

  const handleAddStrategy = async () => {
    if (!selectedClass) { alert('Please select a strategy class first'); return; }
    const portfolioName = selectedPortfolio === '__custom__' ? customPortfolioName : selectedPortfolio;
    if (!portfolioName) { alert('Please select a portfolio or enter a custom symbol name.'); return; }
    const setting = settingsByClass[selectedClass] ?? {};
    try {
      await api.post('/api/strategies', { strategy_class: selectedClass, portfolio_name: portfolioName, setting });
      setCustomPortfolioName('');
      await fetchStrategies();
    } catch (e) {
      console.error('Add strategy error', e);
    }
  };

  const callStrategyEndpoint = async (name: string, action: 'init' | 'start' | 'stop' | 'remove' | 'delete') => {
    const path = `/api/strategies/${encodeURIComponent(name)}`;
    if (action === 'init') await api.post(`${path}/init`);
    else if (action === 'start') await api.post(`${path}/start`);
    else if (action === 'stop') await api.post(`${path}/stop`);
    else if (action === 'remove') await api.delete(`${path}/remove`);
    else await api.delete(`${path}/delete`);
  };

  const handleOpenConfig = async () => {
    if (!selectedClass) { alert('Please select a strategy class first'); return; }
    const strategyClass = selectedClass;
    setConfigForClass(strategyClass);
    setConfigOpen(true);
    let defaults: StrategySetting = {};
    try {
      const data = await api.get<{ settings?: StrategySetting }>(
        `/api/strategies/meta/settings?class=${encodeURIComponent(strategyClass)}`
      );
      if (data.settings && typeof data.settings === 'object') defaults = data.settings;
    } catch { /* live engine may be down */ }
    const existing = settingsByClass[strategyClass] ?? {};
    const merged: StrategySetting = { ...defaults, ...existing };
    setPendingSetting(
      Object.keys(merged).length === 0
        ? []
        : Object.entries(merged).map(([key, value]) => ({ key, value: String(value) }))
    );
  };

  const handleConfigApply = () => {
    if (!configForClass) { setConfigOpen(false); return; }
    const setting: StrategySetting = {};
    for (const { key, value } of pendingSetting) {
      const trimmedKey = key.trim();
      if (!trimmedKey) continue;
      const num = Number(value);
      if (Number.isFinite(num)) setting[trimmedKey] = num;
    }
    setSettingsByClass((prev) => ({ ...prev, [configForClass]: setting }));
    setConfigOpen(false);
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <PageLayout title="Strategy Manager">
      {/* ── Two-column root ─────────────────────────────────────────────────── */}
      <div className="h-full flex min-h-0 p-3 overflow-hidden" style={{ gap: 0 }}>

        {/* ── LEFT PANEL: controls + strategy table ────────────────────────── */}
        <div className="flex flex-col gap-2 min-h-0 overflow-hidden"
             style={{ width: selectedStrategy ? leftW : '100%', flexShrink: 0 }}>

          {/* Header */}
          <div className="flex items-center justify-between shrink-0">
            <p className="text-[10px] uppercase tracking-widest text-[color:var(--text-muted)]">System Control</p>
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider">
              <span className={`w-2 h-2 rounded-full ${isBackendConnected ? 'bg-green-500' : 'bg-red-500 animate-pulse'}`} />
              <span className={isBackendConnected ? 'text-green-500' : 'text-red-500 font-semibold'}>
                {isBackendConnected ? 'Connected' : 'Disconnected'}
              </span>
            </div>
          </div>

          {/* Row 1: Strategy class */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="form-label shrink-0">Class</span>
            <TerminalSelect
              value={selectedClass}
              onValueChange={setSelectedClass}
              placeholder="Select strategy class..."
              className="flex-1 min-w-[160px]"
              options={strategyClasses.map((cls) => ({ value: cls, label: cls }))}
            />
            <button
              type="button"
              onClick={handleOpenConfig}
              className={`h-7 px-3 btn shrink-0 ${selectedClass ? 'btn-primary' : 'btn-ghost'}`}
              disabled={!selectedClass}
            >Config</button>
          </div>

          {/* Row 2: Portfolio */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="form-label shrink-0">Portfolio</span>
            <TerminalSelect
              value={selectedPortfolio}
              onValueChange={setSelectedPortfolio}
              placeholder="Custom..."
              className="min-w-[140px]"
              options={[
                { value: '__custom__', label: 'Custom / Enter Symbol...' },
                ...portfolios.map((pf) => ({ value: pf, label: pf })),
              ]}
            />
            {selectedPortfolio === '__custom__' && (
              <input
                type="text"
                placeholder="Symbol (e.g. SPY)"
                value={customPortfolioName}
                onChange={(e) => setCustomPortfolioName(e.target.value.toUpperCase())}
                className="h-7 px-2 text-xs form-input w-32 bg-slate-900 border border-slate-700 text-white rounded"
              />
            )}
          </div>

          {/* Row 3: Actions */}
          <div className="flex flex-wrap items-center gap-1.5">
            <button type="button" onClick={handleAddStrategy} className="h-7 px-3 btn btn-primary text-xs">Add Strategy</button>
            <button type="button" onClick={fetchStrategies} className="h-7 px-3 btn btn-primary text-xs">Refresh</button>
            <div className="w-px h-5 bg-[color:var(--border-subtle)]" />
            <button type="button" onClick={withSelected((n) => callStrategyEndpoint(n, 'init'))} className="h-7 px-2 btn btn-primary text-xs">Initialize</button>
            <button type="button" onClick={withSelected((n) => callStrategyEndpoint(n, 'start'))} className="h-7 px-2 btn btn-primary text-xs">Start</button>
            <button type="button" onClick={withSelected((n) => callStrategyEndpoint(n, 'stop'))} className="h-7 px-2 btn btn-primary text-xs">Stop</button>
            <button type="button" onClick={withSelected((n) => callStrategyEndpoint(n, 'remove'))} className="h-7 px-2 btn btn-danger text-xs">Remove</button>
            <button type="button" onClick={withSelected((n) => callStrategyEndpoint(n, 'delete'))} className="h-7 px-2 btn btn-danger text-xs">Delete</button>
          </div>

          {/* Strategy Table */}
          <div className="panel bg-[color:var(--surface-subtle)] flex-1 min-h-0 overflow-auto">
            {loadingStrategies ? (
              <p className="text-xs text-[color:var(--text-muted)] p-2">Loading...</p>
            ) : (
              <table className="table-terminal w-full">
                <thead>
                  <tr>
                    <th className="py-1 px-1 text-left w-6"></th>
                    <th className="py-1 px-2 text-left">Name</th>
                    <th className="py-1 px-2 text-left">Status</th>
                    <th className="py-1 px-2 text-right">uPnL</th>
                    <th className="py-1 px-2 text-right">Δ</th>
                    <th className="py-1 px-2 text-right">Γ</th>
                    <th className="py-1 px-2 text-right">Θ</th>
                    <th className="py-1 px-2 text-left">Pos</th>
                  </tr>
                </thead>
                <tbody>
                  {strategies.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="py-4 px-2 text-center text-[color:var(--text-muted)] text-xs">
                        No strategies — use &quot;Add Strategy&quot; above.
                      </td>
                    </tr>
                  ) : (
                    strategies.map((s) => {
                      const isSelected = s.strategy_name === selectedStrategy;
                      const h = holdings[s.strategy_name];
                      const pnl = h?.summary?.pnl;
                      return (
                        <tr
                          key={s.strategy_name}
                          className={`cursor-pointer ${isSelected ? 'table-row-selected' : 'table-row-hover'}`}
                          onClick={() => setSelectedStrategy(isSelected ? null : s.strategy_name)}
                        >
                          <td className="py-1 px-1">
                            <input type="radio" checked={isSelected} onChange={() => setSelectedStrategy(s.strategy_name)} />
                          </td>
                          <td className="py-1 px-2 text-[color:var(--text-primary)] text-xs font-medium"
                              style={{ maxWidth: '140px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                              title={s.strategy_name}>
                            {s.strategy_name}
                          </td>
                          <td className="py-1 px-2">
                            <span className={`text-[10px] uppercase tracking-wide ${
                              s.status === 'running' ? 'text-[color:var(--state-success)]'
                                : s.status === 'error' ? 'text-[color:var(--state-error)]'
                                : s.status === 'stopped' ? 'text-[color:var(--text-primary)]'
                                : 'text-[color:var(--text-soft)]'
                            }`}>{s.status}</span>
                          </td>
                          <td className={`py-1 px-2 numeric-12 text-right text-xs ${
                            (pnl ?? 0) > 0 ? 'text-[color:var(--state-success)]'
                              : (pnl ?? 0) < 0 ? 'text-[color:var(--state-error)]'
                              : 'text-[color:var(--text-soft)]'
                          }`}>
                            {pnl !== undefined ? pnl.toFixed(2) : '-'}
                          </td>
                          <td className="py-1 px-2 numeric-12 text-right text-xs text-[color:var(--text-soft)]">
                            {h?.summary?.delta !== undefined ? h.summary.delta.toFixed(3) : '-'}
                          </td>
                          <td className="py-1 px-2 numeric-12 text-right text-xs text-[color:var(--text-soft)]">
                            {h?.summary?.gamma !== undefined ? h.summary.gamma.toFixed(4) : '-'}
                          </td>
                          <td className="py-1 px-2 numeric-12 text-right text-xs text-[color:var(--text-soft)]">
                            {h?.summary?.theta !== undefined ? h.summary.theta.toFixed(3) : '-'}
                          </td>
                          <td className="py-1 px-2 numeric-12 text-xs text-[color:var(--text-muted)]">
                            {getPositionSummary(h)}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* ── Vertical drag handle ── */}
        {selectedStrategy && (
          <div
            onMouseDown={onMouseDownCol}
            style={{
              width: '6px',
              cursor: 'col-resize',
              flexShrink: 0,
              background: 'transparent',
              position: 'relative',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            className="group"
          >
            <div style={{
              width: '2px',
              height: '40px',
              borderRadius: '1px',
              background: 'var(--border-subtle)',
              transition: 'background 0.15s',
            }}
            className="group-hover:bg-[color:var(--accent-primary)]"
            />
          </div>
        )}

        {/* ══ RIGHT PANEL: telemetry (only when strategy selected) ════════════ */}
        {selectedStrategy && (
          <div className="flex-1 flex flex-col gap-2 min-h-0 min-w-0 overflow-hidden">

            {/* Header + live badge */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <p className="text-[10px] uppercase tracking-widest text-[color:var(--text-muted)]">
                  {selectedStrategy}
                </p>
                <span className="text-[color:var(--state-success)] text-[10px] animate-pulse">â— live</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={exportTelemetryCSV}
                  className="text-[10px] px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-green-400 border border-slate-700 transition-colors"
                >
                  Export Telemetry
                </button>
                <button
                  type="button"
                  onClick={exportOrdersCSV}
                  className="text-[10px] px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-blue-400 border border-slate-700 transition-colors"
                >
                  Export Orders
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedStrategy(null)}
                  className="text-[10px] text-[color:var(--text-muted)] hover:text-[color:var(--text-soft)] transition-colors ml-1"
                >
                  ✕ close
                </button>
              </div>
            </div>

            {/* â”€â”€ Metric Cards: 4 per row â”€â”€ */}
            <div className="grid grid-cols-4 gap-2 shrink-0">
              <MetricCard
                label="uPnL"
                valueClassName={`text-sm font-semibold ${
                  latestPnl === null ? 'text-[color:var(--text-soft)]'
                    : latestPnl >= 0 ? 'text-[color:var(--state-success)]'
                    : 'text-[color:var(--state-error)]'
                }`}
              >
                {latestPnl !== null ? `$${latestPnl.toFixed(2)}` : 'â€”'}
              </MetricCard>

              <MetricCard label="Trades">
                {totalTrades > 0 ? totalTrades : 'â€”'}
              </MetricCard>

              <MetricCard label="Volume">
                {totalVolume > 0 ? totalVolume.toFixed(2) : 'â€”'}
              </MetricCard>

              <MetricCard label="Pts">
                {selHistory.length}
              </MetricCard>

              <MetricCard label="Delta">
                {latestDelta !== null ? latestDelta.toFixed(4) : 'â€”'}
              </MetricCard>

              <MetricCard label="Gamma">
                {latestGamma !== null ? latestGamma.toFixed(4) : 'â€”'}
              </MetricCard>

              <MetricCard label="Theta">
                {latestTheta !== null ? latestTheta.toFixed(4) : 'â€”'}
              </MetricCard>

              <MetricCard label="Position">
                {getPositionSummary(selHolding)}
              </MetricCard>
            </div>

            {/* â”€â”€ Chart (compact 200px) â”€â”€ */}
            <div className="panel border border-[color:var(--border-subtle)] px-2 pt-2 pb-1 shrink-0">
              <p className="text-[10px] uppercase tracking-widest text-[color:var(--text-muted)] mb-1">
                Live PnL / Greeks / Spot
              </p>
              <div style={{ height: `${chartH}px` }}>
                <LiveTelemetryChart data={selHistory} />
              </div>
            </div>

            {/* ── Horizontal drag handle (chart ↔ orders) ── */}
            <div
              onMouseDown={onMouseDownRow}
              title="Drag to resize chart"
              style={{
                height: '8px',
                cursor: 'row-resize',
                flexShrink: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                margin: '0 -4px',
              }}
              className="group"
            >
              <div style={{
                height: '2px',
                width: '80px',
                borderRadius: '1px',
                background: 'var(--border-subtle)',
                transition: 'background 0.15s, width 0.15s',
              }}
              className="group-hover:bg-[color:var(--accent-primary)] group-hover:w-[120px]"
              />
            </div>

            {/* ── Orders & Trades (flex-1, scrolls) ── */}
            <div className="panel flex-1 min-h-0 flex flex-col px-3 py-2 overflow-hidden">
              <h3 className="text-[10px] uppercase tracking-widest text-[color:var(--text-muted)] flex items-center gap-2 mb-2 shrink-0">
                Orders &amp; Trades
                <span className="text-[color:var(--state-warning)] text-[10px] normal-case animate-pulse">â—  live</span>
                <span className="text-[color:var(--text-muted)] text-[10px] normal-case font-normal">({ordersTrades.length})</span>
              </h3>
              <div className="flex-1 min-h-0 overflow-auto">
                {ordersTrades.length === 0 ? (
                  <p className="text-xs text-[color:var(--text-muted)] py-2">No orders or trades recorded yet for this strategy.</p>
                ) : (
                  <table className="table-terminal">
                    <thead className="sticky top-0 z-10" style={{ backgroundColor: 'var(--surface-subtle)' }}>
                      <tr>
                        <th className="text-left">Type</th>
                        <th className="text-left">Symbol</th>
                        <th className="text-left">Dir</th>
                        <th className="text-right">Vol</th>
                        <th className="text-right">Filled</th>
                        <th className="text-right">Price</th>
                        <th className="text-left">Status</th>
                        <th className="text-left">Time</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ordersTrades.map((r, idx) => {
                        const rtype = (r.record_type ?? '').toLowerCase();
                        const dir = (r.direction ?? '').toUpperCase();
                        return (
                          <tr key={idx} className="table-row-hover">
                            <td className={`numeric-12 text-left font-medium ${
                              rtype === 'trade' ? 'text-[color:var(--state-success)]' : 'text-[color:var(--text-soft)]'
                            }`}>{r.record_type ?? '-'}</td>
                            <td className="numeric-12 text-left text-[color:var(--text-primary)]">{r.symbol ?? '-'}</td>
                            <td className={`numeric-12 text-left ${
                              dir === 'BUY' ? 'text-[color:var(--state-success)]'
                                : dir === 'SELL' ? 'text-[color:var(--state-error)]'
                                : 'text-[color:var(--text-soft)]'
                            }`}>{dir || '-'}</td>
                            <td className="numeric-12 text-right text-[color:var(--text-primary)]">
                              {r.volume != null ? Number(r.volume).toFixed(2) : '-'}
                            </td>
                            <td className="numeric-12 text-right text-[color:var(--text-soft)]">
                              {r.traded != null ? Number(r.traded).toFixed(2) : '-'}
                            </td>
                            <td className="numeric-12 text-right text-[color:var(--text-soft)]">
                              {r.price != null ? `$${Number(r.price).toFixed(2)}` : '-'}
                            </td>
                            <td className="numeric-12 text-left text-[color:var(--text-soft)]">{r.status ?? '-'}</td>
                            <td className="numeric-12 text-left text-[color:var(--text-muted)]">
                              {r.timestamp ? new Date(r.timestamp).toLocaleTimeString() : '-'}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* â”€â”€ Config Modal â”€â”€ */}
      {configOpen && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60">
          <div className="panel max-w-lg w-full mx-4 p-4" style={{ backgroundColor: 'var(--surface-subtle)' }}>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-panel-title text-[color:var(--text-primary)]">Strategy Settings</h2>
            </div>
            <p className="text-xs text-[color:var(--text-muted)] mb-3">
              Configure numeric parameters for the selected strategy class (from engine defaults).
            </p>
            <div className="space-y-2 mb-3">
              {pendingSetting.length === 0 && (
                <p className="text-xs text-[color:var(--text-soft)]">No parameters for this strategy class.</p>
              )}
              {pendingSetting.map((row, index) => (
                <div key={index} className="flex items-center gap-2">
                  <span className="form-label min-w-[120px] shrink-0">{row.key}</span>
                  <input
                    type="number"
                    value={row.value}
                    onChange={(e) => {
                      setPendingSetting((rows) => {
                        const next = [...rows];
                        next[index] = { ...next[index], value: e.target.value };
                        return next;
                      });
                    }}
                    placeholder="0"
                    className="w-28 form-input text-xs"
                  />
                </div>
              ))}
            </div>
            <div className="flex justify-end gap-2">
              <button type="button" className="h-7 px-4 btn btn-ghost" onClick={() => setConfigOpen(false)}>Cancel</button>
              <button type="button" className="h-7 px-4 btn btn-primary" onClick={handleConfigApply}>Apply</button>
            </div>
          </div>
        </div>
      )}
    </PageLayout>
  );
}

