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
  model_results?: Array<{
    model_id: string;
    hedge_ratio: number;
    pnl: number;
    cumulative_pnl: number;
    inference_latency_ns: number;
  }>;
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
  activeModelId: string | null;

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

  startBacktest: (jobId: string, strategyName: string, feeRate: number, riskFreeRate: number, modelId?: string) => void;
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
  activeModelId: null,

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

  startBacktest: (jobId: string, strategyName: string, feeRate: number, riskFreeRate: number, modelId?: string) => {
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
      activeModelId: modelId || null,
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
        // The endpoint returns { strategies: string[], records: TradeRecord[], total_count?: number, total_volume?: number, daily_trades?: dict, daily_volume?: dict }
        const res = await api.get<{
          strategies?: string[];
          records?: Array<{
            record_type: string;
            timestamp: string;
            strategy_name: string;
            price: number | null;
            volume: number | null;
          }>;
          total_count?: number;
          total_volume?: number;
          daily_trades?: { [date: string]: number };
          daily_volume?: { [date: string]: number };
        }>(`/api/orders-trades/db?strategy=${encodeURIComponent(strategyName)}&record_type=Trade&limit=5000`);

        const allRecords = res?.records ?? [];
        const trades = allRecords.filter((r) => r.record_type === 'Trade');
        const totalTrades = res?.total_count ?? trades.length;
        let totalFees = res?.total_volume !== undefined ? (res.total_volume * _feeRate) : 0;
        
        const perDay: { [date: string]: { fees: number; trades: number } } = {};

        if (res?.total_volume === undefined) {
          for (const t of trades) {
            const fee = (Number(t.volume) || 0) * _feeRate;
            totalFees += fee;
          }
        }

        for (const t of trades) {
          const fee = (Number(t.volume) || 0) * _feeRate;
          // Parse date from timestamp
          try {
            const d = new Date(t.timestamp).toISOString().slice(0, 10);
            if (!perDay[d]) perDay[d] = { fees: 0, trades: 0 };
            perDay[d].fees += fee;
            perDay[d].trades += 1;
          } catch { /* ignore */ }
        }

        set((state) => {
          let newDailyFees = { ...state.runningDailyFees };
          let newDailyTrades = { ...state.runningDailyTrades };

          if (res?.daily_trades !== undefined && res?.daily_volume !== undefined) {
            newDailyTrades = res.daily_trades;
            newDailyFees = {};
            for (const [d, v] of Object.entries(res.daily_volume)) {
              newDailyFees[d] = v * _feeRate;
            }
          } else {
            // Merge per-day fees and trades into running state
            for (const [d, v] of Object.entries(perDay)) {
              newDailyFees[d] = v.fees;
              newDailyTrades[d] = v.trades;
            }
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
            
            const daily = (data.daily_results as DailyResult[]) || [];
            
            set((state) => {
              let newMetrics = [...state.metrics];
              if (newMetrics.length === 0 && daily.length > 0) {
                let cumPnL = 0;
                newMetrics = daily.map((d) => {
                  cumPnL += d.pnl;
                  const dateParts = d.file.split('/').pop()?.replace('.parquet', '') || '';
                  let ts = Date.now();
                  if (dateParts.length === 8 && /^\d{8}$/.test(dateParts)) {
                    ts = new Date(`${dateParts.slice(0, 4)}-${dateParts.slice(4, 6)}-${dateParts.slice(6, 8)}`).getTime();
                  } else if (dateParts.includes('-') && dateParts.length === 10) {
                    ts = new Date(dateParts).getTime();
                  }
                  return {
                    tick_timestamp_ns: ts * 1e6,
                    spot_price: 0,
                    implied_vol: 0,
                    cumulative_pnl: cumPnL,
                    pnl: d.pnl,
                    delta: 0,
                    gamma: 0,
                    theta: 0,
                    vega: 0,
                    rho: 0,
                    model_results: state.activeModelId && state.activeModelId !== 'black_scholes' ? [
                      {
                        model_id: state.activeModelId,
                        hedge_ratio: 0,
                        pnl: d.pnl,
                        cumulative_pnl: cumPnL,
                        inference_latency_ns: 0,
                      }
                    ] : [],
                  };
                });
              }
              return {
                summary: data.result as BacktestSummary,
                dailyResults: daily,
                metrics: newMetrics,
                isRunning: false,
                statusBarPhase: 'finalising',
              };
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

              let activeModelResult = null;
              if (state.activeModelId && state.activeModelId !== 'black_scholes' && data.model_results) {
                activeModelResult = data.model_results.find((mr: any) => mr.model_id === state.activeModelId);
              }

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
                model_results: data.model_results || [],
              };

              const newMetrics = [...state.metrics, tick];
              if (newMetrics.length > 10000) newMetrics.shift();

              // Running PnL metrics
              const activePnL = activeModelResult ? Number(activeModelResult.cumulative_pnl) : tick.cumulative_pnl;
              const activeDelta = activeModelResult ? Number(activeModelResult.hedge_ratio) : tick.delta;

              const hasPnL = activePnL !== null && activePnL !== undefined && !isNaN(activePnL) && isFinite(activePnL);
              const runningFinalPnL = hasPnL ? activePnL : state.runningFinalPnL;
              const runningPeak = hasPnL
                ? (state.runningPeak === -999999999.0 ? activePnL : Math.max(state.runningPeak, activePnL))
                : state.runningPeak;
              const runningMaxDrawdown = hasPnL
                ? Math.max(state.runningMaxDrawdown, runningPeak - activePnL)
                : state.runningMaxDrawdown;

              let dateStr = '';
              try {
                const ms = tick.tick_timestamp_ns / 1e6;
                if (!isNaN(ms) && isFinite(ms) && ms > 0) {
                  dateStr = new Date(ms).toISOString().slice(0, 10);
                }
              } catch (e) {
                console.error('Error parsing tick timestamp:', tick.tick_timestamp_ns, e);
              }

              const newUniqueDays = new Set(state.runningUniqueDays);
              if (dateStr) newUniqueDays.add(dateStr);

              const newDailyPnLs = { ...state.runningDailyPnLs };
              if (dateStr && hasPnL) newDailyPnLs[dateStr] = activePnL;

              const newDailyTimesteps = { ...state.runningDailyTimesteps };
              if (dateStr) newDailyTimesteps[dateStr] = (newDailyTimesteps[dateStr] ?? 0) + 1;

              // Sharpe
              let runningSharpe = 0;
              try {
                const sortedDates = Object.keys(newDailyPnLs).filter(Boolean).sort();
                const dailyReturns: number[] = [];
                let prevP = 0;
                for (const dStr of sortedDates) {
                  const currP = newDailyPnLs[dStr];
                  if (!isNaN(currP) && isFinite(currP)) {
                    dailyReturns.push(currP - prevP);
                    prevP = currP;
                  }
                }
                if (dailyReturns.length > 1) {
                  const mean = dailyReturns.reduce((s, v) => s + v, 0) / dailyReturns.length;
                  const variance = dailyReturns.reduce((s, v) => s + Math.pow(v - mean, 2), 0) / (dailyReturns.length - 1);
                  const std = Math.sqrt(variance);
                  const rfDaily = riskFreeRate / 252.0;
                  runningSharpe = (isFinite(std) && std > 0) ? ((mean - rfDaily) / std) * Math.sqrt(252) : 0;
                }
              } catch (e) {
                console.error('Error calculating Sharpe ratio:', e);
              }

              const runningDuration = state.startTime ? (Date.now() - state.startTime) / 1000 : 0;
              const runningFrames = state.runningFrames + 1;

              const runningTotalTrades = data.total_trades !== undefined ? Number(data.total_trades) : state.runningTotalTrades;
              const runningTotalFees = data.total_fees !== undefined ? Number(data.total_fees) : state.runningTotalFees;

              const newDailyTrades = { ...state.runningDailyTrades };
              if (data.daily_trades) {
                for (const [d, v] of Object.entries(data.daily_trades)) {
                  newDailyTrades[d] = Number(v);
                }
              }
              const newDailyFees = { ...state.runningDailyFees };
              if (data.daily_fees) {
                for (const [d, v] of Object.entries(data.daily_fees)) {
                  newDailyFees[d] = Number(v);
                }
              }

              const hasDelta = activeDelta !== null && activeDelta !== undefined && !isNaN(activeDelta) && isFinite(activeDelta);
              const nextMaxDelta = hasDelta ? Math.max(state.maxDelta, Math.abs(activeDelta)) : state.maxDelta;

              const hasGamma = tick.gamma !== null && tick.gamma !== undefined && !isNaN(tick.gamma) && isFinite(tick.gamma);
              const nextMaxGamma = hasGamma ? Math.max(state.maxGamma, Math.abs(tick.gamma)) : state.maxGamma;

              const hasTheta = tick.theta !== null && tick.theta !== undefined && !isNaN(tick.theta) && isFinite(tick.theta);
              const nextMaxTheta = hasTheta ? Math.max(state.maxTheta, Math.abs(tick.theta)) : state.maxTheta;

              return {
                metrics: newMetrics,
                maxDelta: nextMaxDelta,
                maxGamma: nextMaxGamma,
                maxTheta: nextMaxTheta,
                runningFinalPnL,
                runningPeak,
                runningMaxDrawdown,
                runningUniqueDays: newUniqueDays,
                runningDailyPnLs: newDailyPnLs,
                runningDailyTimesteps: newDailyTimesteps,
                runningSharpe: isNaN(runningSharpe) || !isFinite(runningSharpe) ? 0 : runningSharpe,
                runningDuration,
                runningFrames,
                runningTotalTrades,
                runningTotalFees,
                runningDailyTrades: newDailyTrades,
                runningDailyFees: newDailyFees,
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
      activeModelId: null,
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
