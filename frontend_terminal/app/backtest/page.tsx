'use client';

import React, { useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { api, getApiBase } from "@/lib/api";
import PageLayout from "@/app/components/PageLayout";
import TerminalSelect from "@/app/components/TerminalSelect";
import { useTradeStore } from "@/lib/store/useTradeStore";
import type {
  FileDetail,
  FileInfo,
  StrategyOption,
} from "@/app/types/backtest";

// Dynamically import TelemetryChart to prevent SSR issues (window is not defined)
const TelemetryChart = dynamic(() => import("./TelemetryChart"), { ssr: false });

const labelClass =
  "w-24 shrink-0 text-right form-label whitespace-nowrap";
const inputClass =
  "w-40 form-input text-xs rounded-none";
const inputClassDate =
  "w-40 form-input text-xs rounded-none";

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
        className={`leading-none font-semibold numeric-12 ${valueClassName ?? "text-base text-[color:var(--text-primary)]"}`}
      >
        {children}
      </p>
    </div>
  );
}

function ToggleButtonGroup({
  value,
  onChange,
  options,
  disabled = false,
}: {
  value: "mid" | "bid" | "ask";
  onChange: (value: "mid" | "bid" | "ask") => void;
  options: Array<{ value: "mid" | "bid" | "ask"; label: string }>;
  disabled?: boolean;
}) {
  return (
    <div className="flex gap-1">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          disabled={disabled}
          className={`flex-1 h-7 px-2 text-xs uppercase tracking-wide border rounded-none transition-colors ${
            value === option.value
              ? "border-[color:var(--border-strong)] bg-[color:var(--surface-raised)] text-[color:var(--text-primary)]"
              : "border-[color:var(--border-subtle)] bg-[color:var(--surface-subtle)] text-[color:var(--text-soft)] hover:bg-[color:var(--surface-raised)] hover:text-[color:var(--text-primary)]"
          } disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export default function BacktestPage() {
  const [dontShowAgainChecked, setDontShowAgainChecked] = useState(false);
  const [modalConfig, setModalConfig] = useState<{
    isOpen: boolean;
    title: string;
    message: string;
    isConfirm: boolean;
    onConfirm?: () => void;
    showCheckbox?: boolean;
  }>({
    isOpen: false,
    title: "",
    message: "",
    isConfirm: false,
  });

  const [files, setFiles] = useState<FileInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [strategies, setStrategies] = useState<StrategyOption[]>([]);
  const [strategiesLoading, setStrategiesLoading] = useState(true);
  const [selectedSymbol, setSelectedSymbol] = useState<string>("");
  const [selectedDateStart, setSelectedDateStart] = useState<string>("");
  const [selectedDateEnd, setSelectedDateEnd] = useState<string>("");
  const [selectedStrategy, setSelectedStrategy] = useState<string>("");
  const [fileDetail, setFileDetail] = useState<FileDetail | null>(null);

  const [feeRate, setFeeRate] = useState<number>(0.35);
  const [slippageBps, setSlippageBps] = useState<number>(5);
  const [riskFreeRate, setRiskFreeRate] = useState<number>(0.05);
  const [ivPriceMode, setIvPriceMode] = useState<"mid" | "bid" | "ask">("mid");

  const MODEL_OPTIONS = useMemo(() => [
    { 
      value: "black_scholes", 
      label: "Black-Scholes (Baseline)",
      description: "Classical options pricing baseline utilizing mathematical Greeks." 
    },
    { 
      value: "deep_hedge_ffnn", 
      label: "FFNN (Deep Hedge)",
      description: "Feed-Forward Neural Network trained on options chain lifecycles." 
    },
    { 
      value: "deep_hedge_lstm", 
      label: "LSTM (Deep Hedge)",
      description: "Long Short-Term Memory network utilizing sequential step-by-step path history." 
    },
    { 
      value: "deep_hedge_adversarial", 
      label: "Adversarial Deep Hedge",
      description: "Minimax neural model trained against adversarial market simulations." 
    },
  ], []);
  const [hedgingModel, setHedgingModel] = useState<string>("black_scholes");

  // Select Zustand store states
  const isRunning = useTradeStore((s) => s.isRunning);
  const statusBarPhase = useTradeStore((s) => s.statusBarPhase);
  const summary = useTradeStore((s) => s.summary);
  const dailyResults = useTradeStore((s) => s.dailyResults);
  const storeError = useTradeStore((s) => s.error);
  const maxDelta = useTradeStore((s) => s.maxDelta);
  const maxGamma = useTradeStore((s) => s.maxGamma);
  const maxTheta = useTradeStore((s) => s.maxTheta);
  
  // Running trackers
  const runningFinalPnL = useTradeStore((s) => s.runningFinalPnL);
  const runningMaxDrawdown = useTradeStore((s) => s.runningMaxDrawdown);
  const runningUniqueDays = useTradeStore((s) => s.runningUniqueDays);
  const runningDailyPnLs = useTradeStore((s) => s.runningDailyPnLs);
  const runningDailyFees = useTradeStore((s) => s.runningDailyFees);
  const runningDailyTrades = useTradeStore((s) => s.runningDailyTrades);
  const runningDailyTimesteps = useTradeStore((s) => s.runningDailyTimesteps);
  const runningSharpe = useTradeStore((s) => s.runningSharpe);
  const runningDuration = useTradeStore((s) => s.runningDuration);
  const runningFrames = useTradeStore((s) => s.runningFrames);
  const runningTotalTrades = useTradeStore((s) => s.runningTotalTrades);
  const runningTotalFees = useTradeStore((s) => s.runningTotalFees);

  const startBacktest = useTradeStore((s) => s.startBacktest);
  const stopBacktest = useTradeStore((s) => s.stopBacktest);
  const clearStore = useTradeStore((s) => s.clearStore);

  const handleStopBacktest = async () => {
    try {
      const data = await api.post<{ status?: string }>("/api/backtest/cancel");
      if (data.status === "ok") {
        stopBacktest();
      }
    } catch (error) {
      console.error("Error cancelling backtest", error);
      stopBacktest(); // Still stop UI if API fails
    }
  };

  useEffect(() => {
    const fetchFiles = async () => {
      try {
        const data = await api.get<FileInfo[]>("/api/files");
        setFiles(Array.isArray(data) ? data : []);
      } catch (error) {
        console.error("Error fetching files:", error);
      } finally {
        setLoading(false);
      }
    };

    const fetchStrategies = async () => {
      try {
        const data = await api.get<{ status?: string; strategies?: StrategyOption[]; error?: string }>("/api/backtest/strategies");
        if (data.status === "ok" && data.strategies) {
          setStrategies(data.strategies);
        }
      } catch (error) {
        console.error("Error fetching strategies:", error);
      } finally {
        setStrategiesLoading(false);
      }
    };

    fetchFiles();
    fetchStrategies();
    
    // Clear telemetry store on mount
    clearStore();
  }, [clearStore]);

  const availableSymbols = useMemo(() => {
    const segments = files.filter((f) => f.type === "segment");
    return Array.from(
      new Set(segments.map((f) => f.path.split("/").pop() ?? "").filter(Boolean))
    ).sort();
  }, [files]);

  // Prefill first symbol when files are loaded
  useEffect(() => {
    if (loading || selectedSymbol !== "" || availableSymbols.length === 0) return;
    setSelectedSymbol(availableSymbols[0]);
  }, [loading, availableSymbols, selectedSymbol]);

  // Prefill first strategy when strategies are loaded
  useEffect(() => {
    if (strategiesLoading || selectedStrategy !== "" || strategies.length === 0) return;
    setSelectedStrategy(strategies[0].value);
  }, [strategiesLoading, strategies, selectedStrategy]);

  useEffect(() => {
    if (!selectedSymbol) {
      setFileDetail(null);
      setSelectedDateStart("");
      setSelectedDateEnd("");
      return;
    }
    const selected = files.find((f) => {
      if (f.type !== "segment") return false;
      const pathParts = f.path.split("/");
      const symbol = pathParts[pathParts.length - 1];
      return symbol === selectedSymbol;
    });
    if (!selected) {
      setFileDetail(null);
      setSelectedDateStart("");
      setSelectedDateEnd("");
      return;
    }
    setFileDetail({
      path: selected.path,
      size_bytes: selected.size_bytes,
      number_of_days: selected.number_of_days,
      file_count: selected.file_count,
      date_start: selected.date_start ?? null,
      date_end: selected.date_end ?? null,
    });
    if (selected.date_start && selected.date_end) {
      setSelectedDateStart(selected.date_start);
      const startDate = new Date(selected.date_start);
      const endDate = new Date(selected.date_end);
      const limitDate = new Date(startDate.getTime() + 6 * 24 * 60 * 60 * 1000);
      const targetDate = limitDate < endDate ? limitDate : endDate;
      const yyyy = targetDate.getFullYear();
      const mm = String(targetDate.getMonth() + 1).padStart(2, '0');
      const dd = String(targetDate.getDate()).padStart(2, '0');
      setSelectedDateEnd(`${yyyy}-${mm}-${dd}`);
    } else {
      setSelectedDateStart("");
      setSelectedDateEnd("");
    }
  }, [selectedSymbol, files]);

  const executeBacktest = async () => {
    clearStore();

    try {
      const data = await api.post<{ status: string; job_id?: string; error?: string }>("/api/run_backtest", {
        parquet: selectedSymbol,
        strategy: selectedStrategy,
        fee_rate: feeRate,
        slippage_bps: slippageBps,
        risk_free_rate: riskFreeRate,
        iv_price_mode: ivPriceMode,
        strategy_setting: {},
        start_date: selectedDateStart,
        end_date: selectedDateEnd,
        model_ids: hedgingModel !== "black_scholes" ? [hedgingModel] : [],
      });

      if (data.status === "error" || !data.job_id) {
        useTradeStore.setState({
          error: data.error || "Failed to start backtest",
          isRunning: false,
          statusBarPhase: "completed",
        });
      } else {
        // Enqueue stream telemetry subscription in Zustand
        startBacktest(data.job_id, selectedStrategy, feeRate, riskFreeRate, hedgingModel);
      }
    } catch (error) {
      useTradeStore.setState({
        error: `Network error: ${error instanceof Error ? error.message : "Unknown error"}`,
        isRunning: false,
        statusBarPhase: "completed",
      });
    }
  };

  const handleRunBacktest = () => {
    if (!selectedSymbol || !selectedStrategy) {
      setModalConfig({
        isOpen: true,
        title: "Configuration Error",
        message: "Please select both a symbol and a strategy before starting.",
        isConfirm: false,
      });
      return;
    }
    if (!selectedDateStart || !selectedDateEnd) {
      setModalConfig({
        isOpen: true,
        title: "Configuration Error",
        message: "Please enter both start and end dates before starting.",
        isConfirm: false,
      });
      return;
    }

    // Validate date range constraints
    if (fileDetail?.date_start && selectedDateStart < fileDetail.date_start) {
      setModalConfig({
        isOpen: true,
        title: "Date Out of Range",
        message: `Selected start date (${selectedDateStart}) is before the available start date (${fileDetail.date_start}) for this symbol.`,
        isConfirm: false,
      });
      return;
    }
    if (fileDetail?.date_end && selectedDateEnd > fileDetail.date_end) {
      setModalConfig({
        isOpen: true,
        title: "Date Out of Range",
        message: `Selected end date (${selectedDateEnd}) is after the available end date (${fileDetail.date_end}) for this symbol.`,
        isConfirm: false,
      });
      return;
    }
    if (selectedDateStart > selectedDateEnd) {
      setModalConfig({
        isOpen: true,
        title: "Configuration Error",
        message: "Start date must be on or before end date.",
        isConfirm: false,
      });
      return;
    }

    const start = new Date(selectedDateStart);
    const end = new Date(selectedDateEnd);
    const diffTime = Math.abs(end.getTime() - start.getTime());
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24)) + 1;
    
    if (diffDays > 7) {
      const skipWarning = localStorage.getItem("skip7DayWarning") === "true";
      if (skipWarning) {
        executeBacktest();
      } else {
        setModalConfig({
          isOpen: true,
          title: "Performance Warning",
          message: `Warning: Selected duration is ${diffDays} days. Running a backtest for more than 7 days may cause performance strain or timeouts.`,
          isConfirm: true,
          showCheckbox: true,
          onConfirm: executeBacktest,
        });
      }
    } else {
      executeBacktest();
    }
  };

  // On page refresh or navigate away: cancel any running backtest so backend clears the process.
  const cancelBacktestUrl = `${getApiBase()}/api/backtest/cancel`;
  useEffect(() => {
    const handleBeforeUnload = () => {
      try {
        navigator.sendBeacon(cancelBacktestUrl, new Blob([], { type: "application/json" }));
      } catch {
        // ignore
      }
    };

    window.addEventListener("beforeunload", handleBeforeUnload);

    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
      try {
        fetch(cancelBacktestUrl, { method: "POST", keepalive: true }).catch(() => {});
      } catch {
        // ignore
      }
    };
  }, [cancelBacktestUrl]);

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const showValues = summary !== null && statusBarPhase === "completed";
  const netPnl = summary ? summary.net_pnl : 0;

  return (
    <PageLayout title="Option Strategy Backtester">
      <React.Fragment>
        <div className="flex-1 min-h-0 overflow-hidden">
          <div className="h-full flex flex-col lg:flex-row gap-3 min-h-0">
            {/* Left Configuration Form */}
            <div className="w-full lg:w-[30%] flex-shrink-0">
              <div className="h-full border border-[color:var(--border-subtle)] px-3 py-2 space-y-2">
                <h2 className="text-xs uppercase tracking-[0.12em] text-[color:var(--text-muted)]">
                  Backtest Configuration
                </h2>

                <div className="space-y-3">
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <label className={labelClass}>Symbol</label>
                      <TerminalSelect
                        value={selectedSymbol}
                        onValueChange={setSelectedSymbol}
                        className={inputClass}
                        disabled={loading || isRunning || availableSymbols.length === 0}
                        showSearch={true}
                        placeholder={
                          loading
                            ? "Loading symbols..."
                            : availableSymbols.length === 0
                              ? "No symbols found"
                              : "Select a symbol..."
                        }
                        options={availableSymbols.map((symbol) => ({ value: symbol, label: symbol }))}
                      />
                    </div>

                    <div className="p-2.5 border border-[color:var(--border-subtle)] bg-[color:var(--surface-subtle)] rounded-none hover:border-[color:var(--border-strong)] transition-all-custom">
                      <p className="text-[10px] uppercase tracking-wider text-[color:var(--text-muted)] mb-1">
                        Available History
                      </p>
                      <p className="text-xs font-semibold numeric-12 text-[color:var(--state-success)]">
                        {fileDetail?.date_start && fileDetail?.date_end
                          ? `${fileDetail.date_start} ➔ ${fileDetail.date_end}`
                          : "Select a symbol to load range"}
                      </p>
                      {fileDetail?.number_of_days != null && fileDetail?.size_bytes != null && (
                        <p className="text-[10px] text-[color:var(--text-muted)] mt-1">
                          Span: <span className="text-[color:var(--text-primary)] font-medium">{fileDetail.number_of_days} Days</span> | Size: <span className="text-[color:var(--text-primary)] font-medium">{formatFileSize(fileDetail.size_bytes)}</span>
                        </p>
                      )}
                    </div>

                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <label className={labelClass}>Start Date</label>
                        <input
                          type="date"
                          value={selectedDateStart}
                          onChange={(e) => setSelectedDateStart(e.target.value)}
                          className={inputClassDate}
                          disabled={isRunning || !selectedSymbol}
                          min={fileDetail?.date_start || undefined}
                          max={fileDetail?.date_end || undefined}
                        />
                      </div>
                      <div className="flex items-center gap-2">
                        <label className={labelClass}>End Date</label>
                        <input
                          type="date"
                          value={selectedDateEnd}
                          onChange={(e) => setSelectedDateEnd(e.target.value)}
                          className={inputClassDate}
                          disabled={isRunning || !selectedSymbol}
                          min={fileDetail?.date_start || undefined}
                          max={fileDetail?.date_end || undefined}
                        />
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <label className={labelClass}>Strategy</label>
                      <TerminalSelect
                        value={selectedStrategy}
                        onValueChange={setSelectedStrategy}
                        className={inputClass}
                        disabled={isRunning || strategiesLoading}
                        placeholder={
                          strategiesLoading
                            ? "Loading strategies..."
                            : strategies.length === 0
                              ? "No strategies found"
                              : "Select a strategy..."
                        }
                        options={strategies.map((s) => {
                          let desc = "";
                          if (s.value === "StraddleTestStrategy") {
                            desc = "Sells ATM Call/Put to collect premium; delta-hedges directional risk.";
                          } else if (s.value === "IvMeanRevertStrategy") {
                            desc = "Buys/sells straddles when ATM IV deviates significantly from its mean.";
                          } else if (s.value === "IronCondorTestStrategy") {
                            desc = "Sells OTM Call/Put spreads for defined-risk premium harvesting.";
                          } else if (s.value === "StraddleInventoryScalperStrategy") {
                            desc = "Scalps micro-deltas on a rolling inventory of short ATM straddles.";
                          }
                          return { value: s.value, label: s.label, description: desc };
                        })}
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <label className={labelClass}>Fee Rate</label>
                      <input
                        value={feeRate}
                        onChange={(e) => setFeeRate(Number(e.target.value) || 0)}
                        type="number"
                        step="0.0001"
                        min="0"
                        className={inputClass}
                        disabled={isRunning}
                      />
                    </div>
                    <div className="flex items-center gap-2">
                      <label className={labelClass}>Slippage (bps)</label>
                      <input
                        value={slippageBps}
                        onChange={(e) => setSlippageBps(Number(e.target.value) || 0)}
                        type="number"
                        step="1"
                        min="0"
                        className={inputClass}
                        disabled={isRunning}
                      />
                    </div>
                    <div className="flex items-center gap-2">
                      <label className={labelClass}>Risk Free Rate</label>
                      <input
                        value={riskFreeRate}
                        onChange={(e) => setRiskFreeRate(Number(e.target.value) || 0)}
                        type="number"
                        step="0.0001"
                        className={inputClass}
                        disabled={isRunning}
                      />
                    </div>
                    <div className="flex items-center gap-2">
                      <label className={labelClass}>IV Price Mode</label>
                      <div className="flex-1">
                        <ToggleButtonGroup
                          value={ivPriceMode}
                          onChange={setIvPriceMode}
                          options={[
                            { value: "mid", label: "Mid" },
                            { value: "bid", label: "Bid" },
                            { value: "ask", label: "Ask" },
                          ]}
                          disabled={isRunning}
                        />
                      </div>
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-2">
                    <label className={labelClass}>Hedge Model</label>
                    <TerminalSelect
                      value={hedgingModel}
                      onValueChange={setHedgingModel}
                      className={inputClass}
                      disabled={isRunning}
                      options={MODEL_OPTIONS}
                    />
                  </div>

                  <div className="flex items-center justify-end pt-1 gap-2">
                    <button
                      id="btn-start-backtest"
                      onClick={handleRunBacktest}
                      disabled={
                        !selectedSymbol ||
                        !selectedDateStart ||
                        !selectedDateEnd ||
                        !selectedStrategy ||
                        isRunning
                      }
                      className="h-7 px-4 btn btn-primary disabled:text-[color:var(--text-muted)] disabled:border-[color:var(--border-subtle)] disabled:cursor-not-allowed rounded-none"
                    >
                      {isRunning ? "Running..." : "Start Backtest"}
                    </button>
                    <button
                      id="btn-stop-backtest"
                      type="button"
                      onClick={handleStopBacktest}
                      disabled={!isRunning}
                      className="h-7 px-3 btn btn-danger disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      Stop
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* Right Results Dashboard */}
            <div className="mt-3 lg:mt-0 flex-1 min-h-0 flex flex-col space-y-3 overflow-auto fade-in">
              {/* Status Banner */}
              {(statusBarPhase === "running" || statusBarPhase === "finalising") && (
                <div 
                  id="bt-status-banner" 
                  className={`w-full py-2 px-3 text-center text-xs uppercase tracking-wide font-medium border ${
                    statusBarPhase === "running" 
                      ? "pulse-running text-[color:var(--state-success)] bg-[color:var(--surface-subtle)]" 
                      : "bg-[color:var(--surface-subtle)] text-[color:var(--text-muted)] border-[color:var(--border-subtle)]"
                  }`}
                >
                  {statusBarPhase === "running" ? "Running" : "Finalising"}
                </div>
              )}

              {storeError && (
                <div className="border border-[color:var(--state-error)] bg-[color:var(--surface-subtle)] px-3 py-2">
                  <p className="text-xs text-[color:var(--state-error)]">
                    <span className="font-medium">Error:</span> {storeError}
                  </p>
                </div>
              )}

              {/* Metrics cards grid */}
              {/* Metrics cards grid */}
              {(() => {
                const isCompleted = (statusBarPhase === "completed" || statusBarPhase === "finalising") && summary !== null;
                
                const displayFinalPnL = isCompleted ? summary!.final_pnl : (statusBarPhase === "running" ? runningFinalPnL : null);
                const finalPnLColor = displayFinalPnL !== null
                  ? (displayFinalPnL >= 0 ? "text-[color:var(--state-success)]" : "text-[color:var(--state-error)]")
                  : "text-[color:var(--text-soft)]";
                const finalPnLText = displayFinalPnL !== null ? `$${displayFinalPnL.toFixed(2)}` : "—";

                const displayNetPnL = isCompleted ? summary!.net_pnl : (statusBarPhase === "running" ? (runningFinalPnL - runningTotalFees) : null);
                const netPnLColor = displayNetPnL !== null
                  ? (displayNetPnL >= 0 ? "text-[color:var(--state-success)]" : "text-[color:var(--state-error)]")
                  : "text-[color:var(--text-soft)]";
                const netPnLText = displayNetPnL !== null ? `$${displayNetPnL.toFixed(2)}` : "—";

                const displaySharpe = isCompleted ? summary!.daily_sharpe : (statusBarPhase === "running" ? runningSharpe : null);
                const sharpeText = displaySharpe !== null ? Number(displaySharpe).toFixed(3) : "—";

                const displayMaxDD = isCompleted ? summary!.max_drawdown : (statusBarPhase === "running" ? runningMaxDrawdown : null);
                const maxDDText = displayMaxDD !== null ? `$${Number(displayMaxDD).toFixed(2)}` : "—";

                const displayTrades = isCompleted ? summary!.total_trades : (statusBarPhase === "running" ? runningTotalTrades : null);
                const tradesText = displayTrades !== null ? displayTrades : "—";

                const displayFees = isCompleted ? summary!.total_fees : (statusBarPhase === "running" ? runningTotalFees : null);
                const feesText = displayFees !== null ? `$${Number(displayFees).toFixed(2)}` : "—";

                const displayDays = isCompleted ? summary!.num_days : (statusBarPhase === "running" ? runningUniqueDays.size : null);
                const daysText = displayDays !== null && displayDays >= 1 ? displayDays : "—";

                const displayDuration = isCompleted ? summary!.duration_seconds : (statusBarPhase === "running" ? runningDuration : null);
                const durationText = displayDuration !== null ? `${displayDuration.toFixed(2)}s` : "—";

                const displayFrames = isCompleted ? summary!.processed_timesteps : (statusBarPhase === "running" ? runningFrames : null);
                const framesText = displayFrames !== null ? displayFrames : "—";

                const displayRows = isCompleted ? (summary!.total_rows ?? summary!.processed_timesteps) : (statusBarPhase === "running" ? runningFrames : null);
                const rowsText = displayRows !== null ? displayRows.toLocaleString() : "—";

                return (
                  <div className="grid grid-cols-5 gap-2">
                    <MetricCard label="Final PnL" valueClassName={`text-lg ${finalPnLColor}`}>
                      {finalPnLText}
                    </MetricCard>

                    <MetricCard label="Net PnL" valueClassName={`text-lg ${netPnLColor}`}>
                      {netPnLText}
                    </MetricCard>

                    <MetricCard label="Sharpe (Daily)">
                      {sharpeText}
                    </MetricCard>

                    <MetricCard label="Max DD">
                      {maxDDText}
                    </MetricCard>

                    <MetricCard label="Total Trades">
                      {tradesText}
                    </MetricCard>

                    <MetricCard label="Total Fees">
                      {feesText}
                    </MetricCard>

                    <MetricCard label="Days">
                      {daysText}
                    </MetricCard>

                    <MetricCard label="Duration">
                      {durationText}
                    </MetricCard>

                    <MetricCard label="Max Delta">
                      {statusBarPhase === "running" || isCompleted ? maxDelta.toFixed(4) : "—"}
                    </MetricCard>

                    <MetricCard label="Max Gamma">
                      {statusBarPhase === "running" || isCompleted ? maxGamma.toFixed(4) : "—"}
                    </MetricCard>

                    <MetricCard label="Max Theta">
                      {statusBarPhase === "running" || isCompleted ? maxTheta.toFixed(4) : "—"}
                    </MetricCard>

                    <MetricCard label="Frames">
                      {framesText}
                    </MetricCard>

                    <MetricCard label="Rows">
                      {rowsText}
                    </MetricCard>
                  </div>
                );
              })()}

              {/* Status bar below metrics when completed */}
              {statusBarPhase === "completed" && summary && (
                <div id="bt-completed-banner" className="w-full py-2 px-3 mt-2 text-center text-xs uppercase tracking-wide font-medium border border-[color:var(--border-subtle)] text-[color:var(--text-muted)]">
                  Completed
                </div>
              )}

              {/* Chart container */}
              <div className="border border-[color:var(--border-subtle)] px-2 py-2">
                <div className="relative min-h-[320px] h-[340px] flex flex-col">
                  <h3 className="text-xs uppercase tracking-[0.12em] mb-2 text-[color:var(--text-muted)]">
                    Live PnL / Delta / Spot Price Telemetry Stream
                  </h3>
                  <div className="flex-1 relative">
                    <TelemetryChart />
                  </div>
                </div>
              </div>

              {/* Daily results table — shown in real-time while running, finalised at end */}
              {(() => {
                const isCompleted = statusBarPhase === 'completed' && summary !== null;
                const isActive = statusBarPhase === 'running' || statusBarPhase === 'finalising';

                // Build real-time rows from running state
                const liveRows: Array<{
                  date: string;
                  dayPnL: number;
                  netDayPnL: number;
                  fees: number;
                  trades: number;
                  timesteps: number;
                }> = [];

                if (isActive || (isCompleted && dailyResults.length === 0)) {
                  const sortedDates = Object.keys(runningDailyPnLs).sort();
                  let prevCum = 0;
                  for (const d of sortedDates) {
                    const cumPnL = runningDailyPnLs[d];
                    const dayPnL = cumPnL - prevCum;
                    const fees = runningDailyFees[d] ?? 0;
                    const trades = runningDailyTrades[d] ?? 0;
                    const timesteps = runningDailyTimesteps[d] ?? 0;
                    liveRows.push({
                      date: d,
                      dayPnL,
                      netDayPnL: dayPnL - fees,
                      fees,
                      trades,
                      timesteps,
                    });
                    prevCum = cumPnL;
                  }
                }

                const showLive = liveRows.length > 0 && (isActive || (isCompleted && dailyResults.length === 0));
                const showFinal = isCompleted && dailyResults.length > 0;

                if (!showLive && !showFinal) return null;

                return (
                  <div className="panel px-3 py-2">
                    <h3 className="text-xs uppercase tracking-[0.12em] mb-2 text-[color:var(--text-muted)] flex items-center gap-2">
                      Daily Results
                      {isActive && (
                        <span className="text-[color:var(--state-warning)] text-[10px] normal-case tracking-normal animate-pulse">
                          • live
                        </span>
                      )}
                      <span className="text-[color:var(--text-muted)] text-[10px] font-normal normal-case tracking-normal">
                        ({showFinal ? dailyResults.length : liveRows.length} days)
                      </span>
                    </h3>
                    <div className="overflow-x-auto max-h-64 overflow-y-auto">
                      <table className="table-terminal">
                        <thead className="sticky top-0 z-10" style={{ backgroundColor: 'var(--surface-subtle)' }}>
                          <tr>
                            <th className="text-left">Date</th>
                            <th className="text-right">PnL</th>
                            <th className="text-right">Net PnL</th>
                            <th className="text-right">Fees</th>
                            <th className="text-right">Trades</th>
                            <th className="text-right">Timesteps</th>
                          </tr>
                        </thead>
                        <tbody>
                          {showFinal
                            ? dailyResults.map((daily, idx) => {
                                const filePath = daily.file;
                                const fileName = filePath.split('/').pop() ?? '';
                                const raw = fileName.replace('.parquet', '');
                                const displayDate =
                                  raw.length === 8 && /^\d{8}$/.test(raw)
                                    ? `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}`
                                    : raw;
                                const netPnL = daily.net_pnl ?? daily.pnl - daily.fees;
                                return (
                                  <tr key={idx} className="table-row-hover">
                                    <td className="numeric-12 text-left text-[color:var(--text-primary)]">{displayDate}</td>
                                    <td className={`numeric-12 text-right ${daily.pnl >= 0 ? 'text-[color:var(--state-success)]' : 'text-[color:var(--state-error)]'}`}>
                                      ${daily.pnl.toFixed(2)}
                                    </td>
                                    <td className={`numeric-12 text-right ${netPnL >= 0 ? 'text-[color:var(--state-success)]' : 'text-[color:var(--state-error)]'}`}>
                                      ${netPnL.toFixed(2)}
                                    </td>
                                    <td className="numeric-12 text-right text-[color:var(--text-soft)]">${daily.fees.toFixed(2)}</td>
                                    <td className="numeric-12 text-right text-[color:var(--text-primary)]">{daily.trades}</td>
                                    <td className="numeric-12 text-right text-[color:var(--text-soft)]">{daily.timesteps.toLocaleString()}</td>
                                  </tr>
                                );
                              })
                            : liveRows.map((row, idx) => (
                                <tr key={idx} className="table-row-hover">
                                  <td className="numeric-12 text-left text-[color:var(--text-primary)]">{row.date}</td>
                                  <td className={`numeric-12 text-right ${row.dayPnL >= 0 ? 'text-[color:var(--state-success)]' : 'text-[color:var(--state-error)]'}`}>
                                    ${row.dayPnL.toFixed(2)}
                                  </td>
                                  <td className={`numeric-12 text-right ${row.netDayPnL >= 0 ? 'text-[color:var(--state-success)]' : 'text-[color:var(--state-error)]'}`}>
                                    ${row.netDayPnL.toFixed(2)}
                                  </td>
                                  <td className="numeric-12 text-right text-[color:var(--text-soft)]">${row.fees.toFixed(2)}</td>
                                  <td className="numeric-12 text-right text-[color:var(--text-primary)]">{row.trades}</td>
                                  <td className="numeric-12 text-right text-[color:var(--text-soft)]">{row.timesteps.toLocaleString()}</td>
                                </tr>
                              ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                );
              })()}

              {/* Deep Hedging Model Comparison Table */}
              {(() => {
                const metrics = useTradeStore((s) => s.metrics);
                const lastMetrics = metrics[metrics.length - 1];
                const modelResults = lastMetrics?.model_results || [];
                if (modelResults.length === 0) return null;

                const friendlyName = (id: string) => {
                  if (id === "deep_hedge_ffnn") return "Feed-Forward Neural Network (FFNN)";
                  if (id === "deep_hedge_lstm") return "Long Short-Term Memory (LSTM)";
                  if (id === "deep_hedge_adversarial") return "Adversarial Deep Hedging Model";
                  return id;
                };

                return (
                  <div className="panel px-3 py-2">
                    <h3 className="text-xs uppercase tracking-[0.12em] mb-2 text-[color:var(--text-muted)]">
                      Deep Hedging Model Comparison (Live Telemetry)
                    </h3>
                    <div className="overflow-x-auto">
                      <table className="table-terminal">
                        <thead>
                          <tr>
                            <th className="text-left">Model Name</th>
                            <th className="text-right">Latest Hedge Ratio</th>
                            <th className="text-right">Model PnL Diff</th>
                            <th className="text-right">Inference Latency</th>
                          </tr>
                        </thead>
                        <tbody>
                          {modelResults.map((mr) => {
                            const hedgeRatio = mr.hedge_ratio !== undefined && mr.hedge_ratio !== null ? mr.hedge_ratio : 0;
                            const pnlDiff = mr.pnl !== undefined && mr.pnl !== null ? mr.pnl : 0;
                            const latencyNs = mr.inference_latency_ns !== undefined && mr.inference_latency_ns !== null ? mr.inference_latency_ns : 0;
                            const latencyUs = (latencyNs / 1000).toFixed(1);
                            return (
                              <tr key={mr.model_id} className="table-row-hover">
                                <td className="text-left text-[color:var(--text-primary)] font-medium">
                                  {friendlyName(mr.model_id)}
                                </td>
                                <td className="numeric-12 text-right text-[color:var(--text-soft)]">
                                  {hedgeRatio.toFixed(4)}
                                </td>
                                <td className={`numeric-12 text-right ${pnlDiff >= 0 ? 'text-[color:var(--state-success)]' : 'text-[color:var(--state-error)]'}`}>
                                  ${pnlDiff >= 0 ? '+' : ''}{pnlDiff.toFixed(2)}
                                </td>
                                <td className="numeric-12 text-right text-[color:var(--text-soft)]">
                                  {latencyUs} μs
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                );
              })()}
            </div>
          </div>
        </div>
        {modalConfig.isOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-[color:rgba(0,0,0,0.6)] backdrop-blur-xs fade-in">
            <div className="w-[380px] border border-[color:var(--border-strong)] bg-[color:var(--surface-raised)] p-4 shadow-2xl relative">
              <h3 className="text-xs uppercase tracking-wider text-[color:var(--text-primary)] font-bold mb-2 pb-1 border-b border-[color:var(--border-subtle)]">
                {modalConfig.title}
              </h3>
              <p className="text-xs text-[color:var(--text-primary)] mb-4 leading-normal">
                {modalConfig.message}
              </p>
              
              {modalConfig.showCheckbox && (
                <div className="flex items-center gap-2 mb-4 select-none">
                  <input
                    type="checkbox"
                    id="dont-show-checkbox"
                    checked={dontShowAgainChecked}
                    onChange={(e) => setDontShowAgainChecked(e.target.checked)}
                    className="h-3.5 w-3.5 border border-[color:var(--border-subtle)] bg-[color:var(--surface-subtle)] focus:outline-none"
                  />
                  <label htmlFor="dont-show-checkbox" className="text-[10px] uppercase tracking-wide text-[color:var(--text-muted)] cursor-pointer">
                    Do not show this warning again
                  </label>
                </div>
              )}

              <div className="flex justify-end gap-2">
                {modalConfig.isConfirm && (
                  <button
                    onClick={() => {
                      setModalConfig(prev => ({ ...prev, isOpen: false }));
                      setDontShowAgainChecked(false);
                    }}
                    className="h-6 px-3 text-[10px] btn btn-ghost"
                  >
                    Cancel
                  </button>
                )}
                <button
                  onClick={() => {
                    setModalConfig(prev => ({ ...prev, isOpen: false }));
                    if (modalConfig.showCheckbox && dontShowAgainChecked) {
                      localStorage.setItem("skip7DayWarning", "true");
                    }
                    if (modalConfig.onConfirm) {
                      modalConfig.onConfirm();
                    }
                    setDontShowAgainChecked(false);
                  }}
                  className="h-6 px-3 text-[10px] btn btn-primary bg-[color:var(--surface-subtle)] hover:bg-[color:var(--surface-raised)] text-[color:var(--text-primary)] border-[color:var(--border-strong)]"
                >
                  {modalConfig.isConfirm ? "Proceed" : "OK"}
                </button>
              </div>
            </div>
          </div>
        )}
      </React.Fragment>
    </PageLayout>
  );
}
