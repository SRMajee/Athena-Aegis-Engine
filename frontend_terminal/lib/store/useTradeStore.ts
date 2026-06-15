import { create } from 'zustand';
import { api, getWsStreamUrl } from '@/lib/api';

export interface StreamMetrics {
  tick_timestamp_ns: number;
  spot_price: number;
  implied_vol: number;
  cumulative_pnl: number;
  pnl: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  rho: number;
}

export interface BacktestSummary {
  final_pnl: number;
  net_pnl: number;
  total_trades: number;
  total_fees: number;
  max_drawdown: number;
  daily_sharpe: number;
  num_days: number;
  duration_seconds: number;
  processed_timesteps: number;
  total_rows?: number;
  total_frames?: number;
}

export interface DailyResult {
  file: string;
  pnl: number;
  net_pnl: number;
  fees: number;
  trades: number;
  timesteps: number;
  rows: number;
}

// Running daily snapshot built from tick stream (for real-time table)
export interface RunningDailyRow {
  date: string;          // YYYY-MM-DD
  cumPnL: number;        // cumulative PnL at end of this date
  dayPnL: number;        // delta PnL from previous day
  fees: number;
  trades: number;
  timesteps: number;
}

export type StatusBarPhase = 'idle' | 'running' | 'finalising' | 'completed';

interface TradeStoreState {
  isRunning: boolean;
  statusBarPhase: StatusBarPhase;
  metrics: StreamMetrics[];
  summary: BacktestSummary | null;
  dailyResults: DailyResult[];
  error: string | null;
  maxDelta: number;
  maxGamma: number;
  maxTheta: number;

  // Running telemetry metrics
  runningFinalPnL: number;
  runningPeak: number;
  runningMaxDrawdown: number;
  runningUniqueDays: Set<string>;
  runningDailyPnLs: { [key: string]: number };        // date → latest cumPnL
  runningDailyFees: { [key: string]: number };        // date → cumulative fees
  runningDailyTrades: { [key: string]: number };      // date → trade count
  runningDailyTimesteps: { [key: string]: number };   // date → tick count
  runningSharpe: number;
  runningDuration: number;
  runningFrames: number;
  runningTotalTrades: number;
  runningTotalFees: number;
  startTime: number | null;

  startBacktest: (jobId: string, strategyName: string, feeRate: number, riskFreeRate: number) => void;
  stopBacktest: () => void;
  clearStore: () => void;
}

// Module-level variables to keep track of active connection & schedules
let activeWs: WebSocket | null = null;
let finaliseTimeout: NodeJS.Timeout | null = null;
let pollInterval: NodeJS.Timeout | null = null;

// Shared closure variables updated by the poll callback so they can feed into tick handler
let _feeRate = 0;

export const useTradeStore = create<TradeStoreState>((set) => ({
  isRunning: false,
  statusBarPhase: 'idle',
  metrics: [],
  summary: null,
  dailyResults: [],
  error: null,
  maxDelta: 0,
  maxGamma: 0,
  maxTheta: 0,

  runningFinalPnL: 0,
  runningPeak: -999999999.0,
  runningMaxDrawdown: 0,
  runningUniqueDays: new Set<string>(),
  runningDailyPnLs: {},
  runningDailyFees: {},
  runningDailyTrades: {},
  runningDailyTimesteps: {},
  runningSharpe: 0,
  runningDuration: 0,
  runningFrames: 0,
  runningTotalTrades: 0,
  runningTotalFees: 0,
  startTime: null,

  startBacktest: (jobId: string, strategyName: string, feeRate: number, riskFreeRate: number) => {
    // 1. Clean up any existing connection & timeouts & polling interval
    if (activeWs) {
      try {
        activeWs.onclose = null;
        activeWs.onerror = null;
        activeWs.close();
      } catch { /* ignore */ }
      activeWs = null;
    }
    if (finaliseTimeout) { clearTimeout(finaliseTimeout); finaliseTimeout = null; }
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }

    _feeRate = feeRate;
    const now = Date.now();

    // 2. Reset state for new run
    set({
      isRunning: true,
      statusBarPhase: 'running',
      metrics: [],
      summary: null,
      dailyResults: [],
      error: null,
      maxDelta: 0,
      maxGamma: 0,
      maxTheta: 0,
      runningFinalPnL: 0,
      runningPeak: -999999999.0,
      runningMaxDrawdown: 0,
      runningUniqueDays: new Set<string>(),
      runningDailyPnLs: {},
      runningDailyFees: {},
      runningDailyTrades: {},
      runningDailyTimesteps: {},
      runningSharpe: 0,
      runningDuration: 0,
      runningFrames: 0,
      runningTotalTrades: 0,
      runningTotalFees: 0,
      startTime: now,
    });

    // 3. Poll trades/fees from DB in real-time
    const pollTrades = async () => {
      try {
        // The endpoint returns { strategies: string[], records: TradeRecord[] }
        const res = await api.get<{
          strategies?: string[];
          records?: Array<{
            record_type: string;
            timestamp: string;
            strategy_name: string;
            price: number | null;
            volume: number | null;
          }>;
        }>(`/api/orders-trades/db?strategy=${encodeURIComponent(strategyName)}&record_type=Trade&limit=5000`);

        const allRecords = res?.records ?? [];
        const trades = allRecords.filter((r) => r.record_type === 'Trade');
        const totalTrades = trades.length;
        let totalFees = 0;
        const perDay: { [date: string]: { fees: number; trades: number } } = {};

        for (const t of trades) {
          const fee = (Number(t.volume) || 0) * _feeRate;
          totalFees += fee;
          // Parse date from timestamp
          try {
            const d = new Date(t.timestamp).toISOString().slice(0, 10);
            if (!perDay[d]) perDay[d] = { fees: 0, trades: 0 };
            perDay[d].fees += fee;
            perDay[d].trades += 1;
          } catch { /* ignore */ }
        }

        set((state) => {
          // Merge per-day fees and trades into running state
          const newDailyFees = { ...state.runningDailyFees };
          const newDailyTrades = { ...state.runningDailyTrades };
          for (const [d, v] of Object.entries(perDay)) {
            newDailyFees[d] = v.fees;
            newDailyTrades[d] = v.trades;
          }
          return {
            runningTotalTrades: totalTrades,
            runningTotalFees: totalFees,
            runningDailyFees: newDailyFees,
            runningDailyTrades: newDailyTrades,
          };
        });
      } catch (err) {
        console.error('Failed to poll running trades:', err);
      }
    };

    // 4. Establish WebSocket connection
    try {
      const url = getWsStreamUrl(jobId);
      const ws = new WebSocket(url);
      activeWs = ws;

      let connectionTimeout: NodeJS.Timeout | null = setTimeout(() => {
        if (ws && ws.readyState === WebSocket.CONNECTING) {
          ws.onclose = null;
          ws.onerror = null;
          ws.close();
          activeWs = null;
          if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
          set({
            error: 'Connection timeout: WebSocket failed to connect within 10 seconds.',
            isRunning: false,
            statusBarPhase: 'completed',
          });
        }
      }, 10000);

      ws.onopen = () => {
        if (connectionTimeout) {
          clearTimeout(connectionTimeout);
          connectionTimeout = null;
        }
      };

      // Poll immediately and then every 1000ms
      void pollTrades();
      pollInterval = setInterval(() => { void pollTrades(); }, 1000);

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data as string);

          // Final summary payload
          if (data.status === 'ok' && data.result) {
            if (activeWs) {
              activeWs.onclose = null;
              activeWs.onerror = null;
              activeWs.close();
              activeWs = null;
            }
            if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
            set({
              summary: data.result as BacktestSummary,
              dailyResults: (data.daily_results as DailyResult[]) || [],
              isRunning: false,
              statusBarPhase: 'finalising',
            });
            finaliseTimeout = setTimeout(() => {
              set({ statusBarPhase: 'completed' });
            }, 800);
          }
          // Cancelled
          else if (data.status === 'cancelled') {
            if (activeWs) {
              activeWs.onclose = null;
              activeWs.onerror = null;
              activeWs.close();
              activeWs = null;
            }
            if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
            set({ error: (data.error as string) || 'Backtest cancelled by user', isRunning: false, statusBarPhase: 'completed' });
          }
          // Error
          else if (data.status === 'error') {
            if (activeWs) {
              activeWs.onclose = null;
              activeWs.onerror = null;
              activeWs.close();
              activeWs = null;
            }
            if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
            set({ error: (data.error as string) || 'Backtest execution failed', isRunning: false, statusBarPhase: 'completed' });
          }
          // Telemetry tick
          else if (data.tick_timestamp_ns !== undefined) {
            set((state) => {
              const spot = Number(data.spot_price ?? data.spot ?? 0);
              const iv = Number(data.implied_vol ?? data.iv ?? 0);
              const greeks = (data.greeks as Record<string, number>) ?? {};

              const tick: StreamMetrics = {
                tick_timestamp_ns: Number(data.tick_timestamp_ns),
                spot_price: spot,
                implied_vol: iv,
                cumulative_pnl: Number(data.cumulative_pnl ?? data.pnl ?? 0),
                pnl: Number(data.pnl ?? 0),
                delta: Number(greeks.delta ?? 0),
                gamma: Number(greeks.gamma ?? 0),
                theta: Number(greeks.theta ?? 0),
                vega: Number(greeks.vega ?? 0),
                rho: Number(greeks.rho ?? 0),
              };

              const newMetrics = [...state.metrics, tick];
              if (newMetrics.length > 10000) newMetrics.shift();

              // Running PnL metrics
              const runningFinalPnL = tick.cumulative_pnl;
              const runningPeak =
                state.runningPeak === -999999999.0
                  ? tick.cumulative_pnl
                  : Math.max(state.runningPeak, tick.cumulative_pnl);
              const runningMaxDrawdown = Math.max(state.runningMaxDrawdown, runningPeak - tick.cumulative_pnl);

              const ms = tick.tick_timestamp_ns / 1e6;
              const dateStr = !isNaN(ms) ? new Date(ms).toISOString().slice(0, 10) : '';

              const newUniqueDays = new Set(state.runningUniqueDays);
              if (dateStr) newUniqueDays.add(dateStr);

              const newDailyPnLs = { ...state.runningDailyPnLs };
              if (dateStr) newDailyPnLs[dateStr] = tick.cumulative_pnl;

              const newDailyTimesteps = { ...state.runningDailyTimesteps };
              if (dateStr) newDailyTimesteps[dateStr] = (newDailyTimesteps[dateStr] ?? 0) + 1;

              // Sharpe
              let runningSharpe = 0;
              const sortedDates = Object.keys(newDailyPnLs).sort();
              const dailyReturns: number[] = [];
              let prevP = 0;
              for (const dStr of sortedDates) {
                const currP = newDailyPnLs[dStr];
                dailyReturns.push(currP - prevP);
                prevP = currP;
              }
              if (dailyReturns.length > 1) {
                const mean = dailyReturns.reduce((s, v) => s + v, 0) / dailyReturns.length;
                const variance = dailyReturns.reduce((s, v) => s + Math.pow(v - mean, 2), 0) / (dailyReturns.length - 1);
                const std = Math.sqrt(variance);
                const rfDaily = riskFreeRate / 252.0;
                runningSharpe = std > 0 ? ((mean - rfDaily) / std) * Math.sqrt(252) : 0;
              }

              const runningDuration = state.startTime ? (Date.now() - state.startTime) / 1000 : 0;
              const runningFrames = state.runningFrames + 1;

              return {
                metrics: newMetrics,
                maxDelta: Math.max(state.maxDelta, tick.delta),
                maxGamma: Math.max(state.maxGamma, tick.gamma),
                maxTheta: Math.max(state.maxTheta, Math.abs(tick.theta)),
                runningFinalPnL,
                runningPeak,
                runningMaxDrawdown,
                runningUniqueDays: newUniqueDays,
                runningDailyPnLs: newDailyPnLs,
                runningDailyTimesteps: newDailyTimesteps,
                runningSharpe,
                runningDuration,
                runningFrames,
              };
            });
          }
        } catch (err) {
          console.error('Failed to parse WebSocket telemetry update:', err);
        }
      };

      ws.onerror = () => {
        if (connectionTimeout) { clearTimeout(connectionTimeout); connectionTimeout = null; }
        if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
        set({ error: 'WebSocket connection error', isRunning: false, statusBarPhase: 'completed' });
      };

      ws.onclose = () => {
        if (connectionTimeout) { clearTimeout(connectionTimeout); connectionTimeout = null; }
        if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
        activeWs = null;
        set((state) => {
          if (state.isRunning) {
            return {
              isRunning: false,
              statusBarPhase: 'completed',
              error: state.error || 'Connection closed.'
            };
          }
          return {};
        });
      };
    } catch (err) {
      if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
      set({
        error: `Connection failure: ${err instanceof Error ? err.message : String(err)}`,
        isRunning: false,
        statusBarPhase: 'completed',
      });
    }
  },

  stopBacktest: () => {
    if (activeWs) {
      try {
        activeWs.onclose = null;
        activeWs.onerror = null;
        activeWs.close();
      } catch { /* ignore */ }
      activeWs = null;
    }
    if (finaliseTimeout) { clearTimeout(finaliseTimeout); finaliseTimeout = null; }
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
    set({ isRunning: false, statusBarPhase: 'completed' });
  },

  clearStore: () => {
    if (activeWs) {
      try {
        activeWs.onclose = null;
        activeWs.onerror = null;
        activeWs.close();
      } catch { /* ignore */ }
      activeWs = null;
    }
    if (finaliseTimeout) { clearTimeout(finaliseTimeout); finaliseTimeout = null; }
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
    set({
      isRunning: false,
      statusBarPhase: 'idle',
      metrics: [],
      summary: null,
      dailyResults: [],
      error: null,
      maxDelta: 0,
      maxGamma: 0,
      maxTheta: 0,
      runningFinalPnL: 0,
      runningPeak: -999999999.0,
      runningMaxDrawdown: 0,
      runningUniqueDays: new Set<string>(),
      runningDailyPnLs: {},
      runningDailyFees: {},
      runningDailyTrades: {},
      runningDailyTimesteps: {},
      runningSharpe: 0,
      runningDuration: 0,
      runningFrames: 0,
      runningTotalTrades: 0,
      runningTotalFees: 0,
      startTime: null,
    });
  },
}));
