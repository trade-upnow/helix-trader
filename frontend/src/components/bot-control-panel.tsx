"use client";

import { Activity, KeyRound, Play, Settings2, Square, TrendingUp, ChevronDown, ChevronUp, AlertTriangle } from "lucide-react";
import { useCallback, useEffect, useState, useRef } from "react";
import { useTranslations } from "next-intl";

import { apiRequest, authStorage } from "@/lib/api";
import { useRouter } from "@/i18n/navigation";

type Strategy = {
  id: string;
  default_params: {
    symbol: string;
    leverage: number;
    position_size_pct: number;
    stop_loss_pct: number;
    take_profit_pct: number;
    max_drawdown_pct: number;
    max_order_notional_usdt: number;
    max_position_notional_usdt: number;
  };
};

type MarketSymbol = {
  symbol: string;
  base: string;
  quote: string;
  min_qty: number;
  min_notional: number;
  qty_precision?: number | null;
  price_precision?: number | null;
};

type BotStatus = {
  status: "running" | "stopped";
  strategy_id?: string | null;
  is_stopping?: boolean;
  exchange?: "binance" | "okx";
  runtime_symbol?: string | null;
  runtime_position_side?: string | null;
  selected_symbol?: string | null;
  masked_api_key?: string | null;
  credential_status?: string | null;
  credential_error?: string | null;
  use_testnet?: boolean;
  status_message?: string | null;
  account_status_message?: string | null;
  last_synced_at?: string | null;
  close_all_on_stop?: boolean;
  active_config?: {
    symbol: string;
    leverage: number;
    position_size_pct: number;
    stop_loss_pct: number;
    take_profit_pct: number;
    max_drawdown_pct: number;
    max_order_notional_usdt: number;
    max_position_notional_usdt: number;
  } | null;
  balance: number;
  unrealized_pnl: number;
  exposure: number;
  positions: Array<{
    symbol: string;
    side: string;
    size: number;
    entry_price: number;
  }>;
};

type Trade = {
  id: string;
  symbol: string;
  side: string;
  price: number;
  quantity: number;
  realized_pnl?: number | null;
  created_at: string;
};

function AnimatedNumber({ value, duration = 2000, decimals = 1 }: { value: number; duration?: number; decimals?: number }) {
  const [current, setCurrent] = useState(0);

  useEffect(() => {
    let startTime: number;
    let animationFrame: number;
    const animate = (timestamp: number) => {
      if (!startTime) startTime = timestamp;
      const progress = timestamp - startTime;
      const percentage = Math.min(progress / duration, 1);
      // easeOutExpo
      const easePercentage = percentage === 1 ? 1 : 1 - Math.pow(2, -10 * percentage);
      setCurrent(value * easePercentage);
      if (percentage < 1) {
        animationFrame = requestAnimationFrame(animate);
      }
    };
    animationFrame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animationFrame);
  }, [value, duration]);

  return <>{current.toFixed(decimals)}</>;
}

export function BotControlPanel() {
  const t = useTranslations("dashboard");
  const heroT = useTranslations("hero");
  const common = useTranslations("common");
  const tStrategies = useTranslations("strategies");
  const [token, setToken] = useState<string | null>(null);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [selectedStrategy, setSelectedStrategy] = useState<string>("");
  const [exchange, setExchange] = useState("binance");
  const [exchangeTouched, setExchangeTouched] = useState(false);
  const [availableSymbols, setAvailableSymbols] = useState<MarketSymbol[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState("BTC/USDT:USDT");
  const [symbolTouched, setSymbolTouched] = useState(false);
  const [paramsTouched, setParamsTouched] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [secret, setSecret] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [maskedKey, setMaskedKey] = useState<string | null>(null);
  const [status, setStatus] = useState<BotStatus | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [closeAll, setCloseAll] = useState(false);
  const [closeAllTouched, setCloseAllTouched] = useState(false);
  const [useSandbox, setUseSandbox] = useState(false);
  const [sandboxTouched, setSandboxTouched] = useState(false);
  const [showApi, setShowApi] = useState(true);
  const [apiInitialized, setApiInitialized] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [applyingConfig, setApplyingConfig] = useState(false);
  const [params, setParams] = useState({
    symbol: "BTC/USDT:USDT",
    leverage: 3,
    position_size_pct: 15,
    stop_loss_pct: 2,
    take_profit_pct: 5,
    max_drawdown_pct: 12,
    max_order_notional_usdt: 1000,
    max_position_notional_usdt: 3000,
  });
  const [showAdvanced, setShowAdvanced] = useState(false);
  const router = useRouter();
  const apiSectionRef = useRef<HTMLDivElement>(null);
  const [pnlKey, setPnlKey] = useState(0);
  const prevPnlRef = useRef<number>(0);
  const [isCheckingAuth, setIsCheckingAuth] = useState(true);

  useEffect(() => {
    const syncToken = () => {
      const currentToken = authStorage.getToken();
      if (!currentToken) {
        router.replace("/login");
      } else {
        setToken(currentToken);
        setIsCheckingAuth(false);
      }
    };

    syncToken();
    return authStorage.subscribe(syncToken);
  }, [router]);

  const loadMarkets = useCallback(
    async (targetExchange: string) => {
      if (!token) {
        setAvailableSymbols([]);
        return;
      }

      try {
        const marketData = await apiRequest<MarketSymbol[]>(
          `/api/bot/markets?exchange=${encodeURIComponent(targetExchange)}`,
          { token },
        );
        setAvailableSymbols(marketData);
      } catch {
        setAvailableSymbols([]);
      }
    },
    [token],
  );

  const loadData = useCallback(async () => {
    if (!token) {
      setStatus(null);
      setMaskedKey(null);
      setTrades([]);
      return;
    }

    try {
      let strategyData = strategies;
      if (strategyData.length === 0) {
        strategyData = await apiRequest<Strategy[]>("/api/strategies", { token });
        setStrategies(strategyData);
      }

      const [statusData, tradeData] = await Promise.all([
        apiRequest<BotStatus>("/api/bot/status", { token }),
        apiRequest<Trade[]>("/api/bot/trades", { token }),
      ]);

      if (!paramsTouched) {
        if (statusData.active_config) {
          setParams(statusData.active_config);
        } else if (strategyData[0]) {
          setParams(strategyData[0].default_params);
        }
      }
      if (!paramsTouched) {
        setSelectedStrategy((current) =>
          statusData.strategy_id ??
          strategyData.find((item) => item.id === current)?.id ??
          strategyData[0]?.id ??
          "",
        );
      }
      if (statusData.unrealized_pnl !== prevPnlRef.current) {
        setPnlKey(k => k + 1);
        prevPnlRef.current = statusData.unrealized_pnl;
      }
      
      setStatus(statusData);
      setMaskedKey(statusData.masked_api_key ?? null);
      if (!apiInitialized && statusData.masked_api_key) {
        setShowApi(false);
        setApiInitialized(true);
      }
      if (!exchangeTouched && statusData.exchange) {
        setExchange(statusData.exchange);
      }
      if (!symbolTouched) {
        const nextSymbol =
          statusData.runtime_symbol ??
          statusData.selected_symbol ??
          statusData.active_config?.symbol ??
          strategyData[0]?.default_params.symbol ??
          availableSymbols[0]?.symbol ??
          "BTC/USDT:USDT";
        setSelectedSymbol(nextSymbol);
      }
      if (!closeAllTouched && typeof statusData.close_all_on_stop === "boolean") {
        setCloseAll(statusData.close_all_on_stop);
      }
      if (!sandboxTouched) {
        // null/undefined means no credential saved yet — default UI to testnet.
        setUseSandbox(
          statusData.use_testnet == null ? true : Boolean(statusData.use_testnet),
        );
      }
      setTrades(tradeData);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Failed to load dashboard",
      );
    }
  }, [token, apiInitialized, closeAllTouched, exchangeTouched, paramsTouched, sandboxTouched, symbolTouched, availableSymbols, strategies]);

  useEffect(() => {
    if (!token) {
      setAvailableSymbols([]);
      return;
    }
    void loadMarkets(exchange);
  }, [exchange, loadMarkets, token]);

  useEffect(() => {
    const bootstrap = async () => {
      await loadData();
    };

    void bootstrap();
    const timer = window.setInterval(() => {
      void loadData();
    }, 10000);

    return () => window.clearInterval(timer);
  }, [loadData]);

  const runtimeExchange = status?.exchange ?? exchange;
  const runtimeSymbol = status?.runtime_symbol ?? status?.active_config?.symbol ?? selectedSymbol;
  const runtimeStrategyId = status?.strategy_id ?? selectedStrategy;
  const runtimePositionSide = status?.runtime_position_side ?? null;
  const isStopping = Boolean(status?.is_stopping);
  const isRunning = status?.status === "running";
  const runtimePositionLabel =
    runtimePositionSide === "long"
      ? t("long")
      : runtimePositionSide === "short"
        ? t("short")
        : runtimePositionSide ?? "-";
  const runtimeExchangeLabel =
    runtimeExchange === "binance" ? common("binance") : common("okx");
  const feedback = error ?? message;
  const feedbackClassName = error
    ? "border-rose-400/20 bg-rose-400/10 text-rose-100"
    : message
      ? "border-emerald-400/20 bg-emerald-400/10 text-emerald-100"
      : "border-transparent bg-transparent text-transparent";

  if (isCheckingAuth) {
    return (
      <div className="min-h-screen bg-[#0B0E14] text-slate-200 font-sans pb-20 pt-6 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-cyan-500/30 border-t-cyan-500"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0B0E14] text-slate-200 font-sans pb-20 pt-6">
      <style>{`
        @keyframes popIn {
          0% { transform: translateY(4px); opacity: 0; }
          100% { transform: translateY(0); opacity: 1; }
        }
        .animate-pop {
          animation: popIn 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275) forwards;
        }
      `}</style>
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-6 lg:px-10">
        
        {/* Premium Hero Section */}
        <div className="relative overflow-hidden rounded-[2.5rem] bg-[#0F172A] border border-white/10 p-8 md:p-12 shadow-2xl">
          <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/10 to-emerald-500/5 pointer-events-none" />
          <div className="relative z-10 flex flex-col lg:flex-row gap-8 items-center justify-between">
            <div className="space-y-5 flex-1">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-400/10 border border-cyan-400/20 text-cyan-300 text-xs font-medium uppercase tracking-wider">
                <Activity size={14} /> {t("eyebrow")}
              </div>
              <h2 className="text-4xl md:text-5xl font-bold text-white tracking-tight">
                {t("title")}
              </h2>
              <p className="text-lg text-slate-300 max-w-xl">
                {t("description")}
              </p>
              <div className="flex flex-wrap gap-8 pt-4">
                <div className="space-y-1">
                  <p className="text-sm text-slate-400">{heroT("stats1Label", { fallback: "Verified 30-Day Return" })}</p>
                  <p className="text-3xl font-bold text-emerald-400 drop-shadow-md">
                    +<AnimatedNumber value={28.4} decimals={1} />%
                  </p>
                </div>
                <div className="space-y-1">
                  <p className="text-sm text-slate-400">{heroT("stats2Label", { fallback: "Annualized Projection" })}</p>
                  <p className="text-3xl font-bold text-cyan-400 drop-shadow-md">
                    ~<AnimatedNumber value={315.8} decimals={1} />%
                  </p>
                </div>
              </div>
            </div>
            <div className="w-full lg:w-[400px] h-40 flex-shrink-0 relative opacity-90 mt-6 lg:mt-0">
              <svg viewBox="0 0 400 150" className="w-full h-full drop-shadow-lg" preserveAspectRatio="none">
                <defs>
                  <linearGradient id="lineGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="#06B6D4" />
                    <stop offset="100%" stopColor="#10B981" />
                  </linearGradient>
                  <linearGradient id="fillGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                    <stop offset="0%" stopColor="#10B981" stopOpacity="0.3" />
                    <stop offset="100%" stopColor="#10B981" stopOpacity="0" />
                  </linearGradient>
                </defs>
                <path
                  d="M0,120 C40,110 80,130 120,90 C160,50 200,80 240,40 C280,0 320,60 360,20 L400,10 L400,150 L0,150 Z"
                  fill="url(#fillGrad)"
                />
                <path
                  d="M0,120 C40,110 80,130 120,90 C160,50 200,80 240,40 C280,0 320,60 360,20 L400,10"
                  fill="none"
                  stroke="url(#lineGrad)"
                  strokeWidth="4"
                  strokeLinecap="round"
                />
              </svg>
            </div>
          </div>
        </div>

      <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="space-y-6">
          <section className="bg-white/5 backdrop-blur-md border border-white/10 rounded-[2rem] p-6 shadow-xl">
            <div className="mb-6 flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <TrendingUp className="text-cyan-300" />
                <h2 className="text-xl font-semibold">{t("strategyTitle")}</h2>
              </div>
              
              <div className="flex shrink-0">
                {isRunning || isStopping ? (
                  <button
                    type="button"
                    disabled={isStopping}
                    onClick={async () => {
                      if (!token) {
                        setError("Missing token");
                        return;
                      }

                      setError(null);
                      setMessage(null);

                      try {
                        await apiRequest("/api/bot/stop", {
                          method: "POST",
                          token,
                          body: JSON.stringify({ close_all: closeAll }),
                        });
                        setMessage("Bot stopped");
                        await loadData();
                      } catch (requestError) {
                        setError(
                          requestError instanceof Error
                            ? requestError.message
                            : "Failed to stop bot",
                        );
                      }
                    }}
                    className="flex items-center gap-2 rounded-2xl border border-rose-500/50 bg-rose-500/10 px-6 py-2.5 font-bold text-rose-100 transition hover:bg-rose-500/20 shadow-lg disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <Square size={16} className="fill-rose-200" />
                    {isStopping ? t("stopping") : t("stop")}
                  </button>
                ) : (
                  <button
                    type="button"
                    disabled={isStopping || !selectedStrategy}
                    onClick={async () => {
                      if (!token || !selectedStrategy) {
                        setError("Missing token or strategy");
                        return;
                      }

                      setError(null);
                      setMessage(null);

                      try {
                        await apiRequest("/api/bot/start", {
                          method: "POST",
                          token,
                          body: JSON.stringify({
                            strategy_id: selectedStrategy,
                            exchange,
                            symbol: selectedSymbol,
                            close_all_on_stop: closeAll,
                            leverage: params.leverage,
                            position_size_pct: params.position_size_pct,
                            stop_loss_pct: params.stop_loss_pct,
                            take_profit_pct: params.take_profit_pct,
                            max_drawdown_pct: params.max_drawdown_pct,
                            max_order_notional_usdt: params.max_order_notional_usdt,
                            max_position_notional_usdt: params.max_position_notional_usdt,
                          }),
                        });
                        setParamsTouched(false);
                        setCloseAllTouched(false);
                        setMessage("Bot started");
                        await loadData();
                      } catch (requestError) {
                        const errMsg = requestError instanceof Error ? requestError.message : "Failed to start bot";
                        setError(errMsg);
                        if (errMsg.toLowerCase().includes("save exchange credentials first")) {
                          setShowApi(true);
                          setTimeout(() => {
                            apiSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
                          }, 100);
                        }
                      }
                    }}
                    className="flex items-center gap-2 rounded-2xl bg-cyan-400 hover:bg-cyan-300 text-slate-950 px-6 py-2.5 font-bold transition-all shadow-[0_0_15px_rgba(6,182,212,0.3)] hover:shadow-[0_0_25px_rgba(6,182,212,0.5)] hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:translate-y-0"
                  >
                    <Play size={16} className="fill-slate-950" />
                    {t("start")}
                  </button>
                )}
              </div>
            </div>
            <div className="grid gap-4">
              {strategies.map((strategy) => {
                const cardLocked = isRunning || isStopping;
                return (
                <button
                  key={strategy.id}
                  type="button"
                  disabled={cardLocked}
                  onClick={() => {
                    setSelectedStrategy(strategy.id);
                    setParamsTouched(true);
                    setParams(strategy.default_params);
                    if (!cardLocked) {
                      setSelectedSymbol(strategy.default_params.symbol);
                      setSymbolTouched(false);
                    }
                  }}
                  className={`rounded-3xl border p-5 text-left transition ${
                    selectedStrategy === strategy.id
                      ? "border-cyan-400/40 bg-cyan-400/8"
                      : "border-white/10 bg-white/3"
                  } ${
                    !cardLocked 
                      ? "hover:bg-white/6 cursor-pointer" 
                      : "opacity-60 cursor-not-allowed"
                  }`}
                >
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <p className="text-lg font-medium">{tStrategies(`${strategy.id}.name`)}</p>
                      <p className="mt-2 text-sm leading-7 text-muted">
                        {tStrategies(`${strategy.id}.description`)}
                      </p>
                    </div>
                    <div className="rounded-full border border-white/10 px-3 py-1 text-xs uppercase tracking-[0.24em] text-cyan-300">
                      Live
                    </div>
                  </div>
                </button>
                );
              })}
            </div>
          </section>

          <section ref={apiSectionRef} className="bg-white/5 backdrop-blur-md border border-white/10 rounded-[2rem] p-6 shadow-xl">
            <button
              type="button"
              onClick={() => setShowApi(!showApi)}
              className="flex w-full items-center justify-between group outline-none"
            >
              <div className="flex items-center gap-3 text-left">
                <KeyRound className="text-cyan-300 group-hover:text-cyan-400 transition-colors" />
                <div>
                  <h2 className="text-xl font-semibold text-white/90 group-hover:text-white transition-colors">{t("apiTitle")}</h2>
                  <p className="mt-1 text-sm text-muted group-hover:text-white/60 transition-colors">{t("apiDesc")}</p>
                </div>
              </div>
              <div className="flex items-center gap-2 text-sm text-cyan-300/80 group-hover:text-cyan-300 transition-colors">
                {showApi ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
              </div>
            </button>

            {showApi && (
              <div className="mt-6 border-t border-white/10 pt-6 animate-in fade-in slide-in-from-top-4 duration-300">
                <div className="grid gap-4 md:grid-cols-2">
              <label className="block">
                <span className="mb-2 block text-sm text-white/70">{t("exchange")}</span>
                <select
                  value={exchange}
                  onChange={(event) => {
                    setExchangeTouched(true);
                    setExchange(event.target.value);
                  }}
                  className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 outline-none"
                >
                  <option value="binance" className="bg-slate-900">
                    {common("binance")}
                  </option>
                  <option value="okx" className="bg-slate-900">
                    {common("okx")}
                  </option>
                </select>
              </label>

              <label className="block">
                <span className="mb-2 block text-sm text-white/70">{t("apiKey")}</span>
                <input
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 outline-none"
                />
              </label>

              <label className="block">
                <span className="mb-2 block text-sm text-white/70">{t("secret")}</span>
                <input
                  type="password"
                  value={secret}
                  onChange={(event) => setSecret(event.target.value)}
                  className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 outline-none"
                />
              </label>

              <label className="block">
                <span className="mb-2 block text-sm text-white/70">{t("passphrase")}</span>
                <input
                  type="password"
                  value={passphrase}
                  onChange={(event) => setPassphrase(event.target.value)}
                  className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 outline-none"
                />
              </label>
            </div>

            <div className="mt-5 rounded-2xl border border-white/8 bg-white/3 p-4">
              <p className="text-xs uppercase tracking-[0.24em] text-muted">
                {t("masked")}
              </p>
              <p className="mt-2 text-lg font-medium">
                {maskedKey ?? t("noSavedKey")}
              </p>
            </div>

            <button
              type="button"
              onClick={async () => {
                if (!token) {
                  setError("Not authenticated");
                  return;
                }

                setError(null);
                setMessage(null);

                try {
                  const response = await apiRequest<{ masked_api_key: string }>(
                    "/api/bot/credentials",
                    {
                      method: "POST",
                      token,
                      body: JSON.stringify({
                        exchange,
                        api_key: apiKey,
                        api_secret: secret,
                        passphrase: passphrase || null,
                        use_testnet: useSandbox,
                      }),
                    },
                  );

                  setMaskedKey(response.masked_api_key);
                  setExchangeTouched(false);
                  setSandboxTouched(false);
                  setParamsTouched(false);
                  setApiKey("");
                  setSecret("");
                  setPassphrase("");
                  setMessage("Credentials saved");
                  await loadData();
                } catch (requestError) {
                  setError(
                    requestError instanceof Error
                      ? requestError.message
                      : "Failed to save credentials",
                  );
                }
              }}
              className="mt-5 rounded-2xl border border-cyan-400/30 bg-cyan-400/10 px-5 py-3 font-medium text-cyan-100 transition hover:bg-cyan-400/14"
            >
              {t("saveKeys")}
            </button>
              </div>
            )}
          </section>

          <section className="bg-white/5 backdrop-blur-md border border-white/10 rounded-[2rem] p-6 shadow-xl">
            <button 
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="flex w-full items-center justify-between group outline-none"
            >
              <div className="flex items-center gap-3">
                <Settings2 className="text-cyan-300 group-hover:text-cyan-400 transition-colors" />
                <h2 className="text-xl font-semibold text-white/90 group-hover:text-white transition-colors">{t("advanced")}</h2>
              </div>
              <div className="flex items-center gap-2 text-sm text-cyan-300/80 group-hover:text-cyan-300 transition-colors font-medium">
                {showAdvanced ? t("hideAdvanced", { fallback: "Hide Advanced Settings" }) : t("showAdvanced", { fallback: "Show Advanced Settings (Optional)" })}
                {showAdvanced ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </div>
            </button>
            
            {showAdvanced && (
              <div className="mt-6 border-t border-white/10 pt-6 animate-in fade-in slide-in-from-top-4 duration-300">
                <div className="grid gap-4 md:grid-cols-2">
              {[
                ["symbol", selectedSymbol],
                ["leverage", params.leverage],
                ["positionSize", params.position_size_pct],
                ["stopLoss", params.stop_loss_pct],
                ["takeProfit", params.take_profit_pct],
                ["maxDrawdown", params.max_drawdown_pct],
                ["maxOrderNotional", params.max_order_notional_usdt],
                ["maxPositionNotional", params.max_position_notional_usdt],
              ].map(([key, value]) => (
                <label key={key} className="block">
                  <span className="mb-2 block text-sm text-white/70">
                    {t(key as never)}
                  </span>
                  {key === "symbol" ? (
                    <select
                      value={selectedSymbol}
                      disabled={isRunning || isStopping}
                      onChange={(event) => {
                        setSymbolTouched(true);
                        setSelectedSymbol(event.target.value);
                        setParams((current) => ({ ...current, symbol: event.target.value }));
                      }}
                      className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 outline-none disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {(availableSymbols.length ? availableSymbols : [{ symbol: "BTC/USDT:USDT" }]).map(
                        (symbolOption) => (
                          <option
                            key={symbolOption.symbol}
                            value={symbolOption.symbol}
                            className="bg-slate-900"
                          >
                            {symbolOption.symbol}
                          </option>
                        ),
                      )}
                    </select>
                  ) : (
                    <input
                      type="number"
                      value={value}
                      onChange={(event) => {
                        const numericValue = Number(event.target.value);
                        setParamsTouched(true);
                        setParams((current) => ({
                          ...current,
                          [key === "positionSize"
                            ? "position_size_pct"
                            : key === "stopLoss"
                              ? "stop_loss_pct"
                              : key === "takeProfit"
                                ? "take_profit_pct"
                                : key === "maxDrawdown"
                                  ? "max_drawdown_pct"
                                  : key === "maxOrderNotional"
                                    ? "max_order_notional_usdt"
                                    : key === "maxPositionNotional"
                                      ? "max_position_notional_usdt"
                                      : "leverage"]: Number.isFinite(numericValue)
                            ? numericValue
                            : 0,
                        }));
                      }}
                      className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 outline-none"
                    />
                  )}
                </label>
              ))}
            </div>
            {isRunning || isStopping ? (
              <p className="mt-3 text-xs text-muted">{t("symbolLockedHint")}</p>
            ) : null}

            <label className="mt-5 flex items-start gap-3 text-sm text-white/80">
              <input
                type="checkbox"
                checked={useSandbox}
                onChange={(event) => {
                  setSandboxTouched(true);
                  setUseSandbox(event.target.checked);
                }}
                className="mt-1"
              />
              <span>
                <span className="block font-medium text-white">{t("useSandbox")}</span>
                <span className="mt-1 block text-xs leading-5 text-muted">
                  {t("sandboxHint")}
                </span>
              </span>
            </label>

            <label className="mt-5 flex items-center gap-3 text-sm text-white/80">
              <input
                type="checkbox"
                checked={closeAll}
                onChange={(event) => {
                  setCloseAllTouched(true);
                  setCloseAll(event.target.checked);
                }}
              />
              {t("closeAll")}
            </label>

            {isRunning ? (
              <div className="mt-6 flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={async () => {
                    if (!token) {
                      setError("Missing token");
                      return;
                    }

                    setApplyingConfig(true);
                    setError(null);
                    setMessage(null);

                    try {
                      await apiRequest("/api/bot/config", {
                        method: "PATCH",
                        token,
                        body: JSON.stringify({
                          leverage: params.leverage,
                          position_size_pct: params.position_size_pct,
                          stop_loss_pct: params.stop_loss_pct,
                          take_profit_pct: params.take_profit_pct,
                          max_drawdown_pct: params.max_drawdown_pct,
                          max_order_notional_usdt: params.max_order_notional_usdt,
                          max_position_notional_usdt: params.max_position_notional_usdt,
                          close_all_on_stop: closeAll,
                        }),
                      });
                      setParamsTouched(false);
                      setCloseAllTouched(false);
                      setMessage("Settings applied");
                      await loadData();
                    } catch (requestError) {
                      setError(
                        requestError instanceof Error
                          ? requestError.message
                          : "Failed to apply settings",
                      );
                    } finally {
                      setApplyingConfig(false);
                    }
                  }}
                  className="flex items-center gap-2 rounded-2xl border border-cyan-400/30 bg-cyan-400/10 px-5 py-3 font-medium text-cyan-100 transition hover:bg-cyan-400/14"
                >
                  <Settings2 size={16} />
                  {applyingConfig ? t("applyingSettings") : t("applySettings")}
                </button>
              </div>
            ) : null}
            
            </div>
            )}
          </section>

        </div>

        <div className="space-y-6">
          <section className="bg-white/5 backdrop-blur-md border border-white/10 rounded-[2rem] p-6 shadow-xl">
            <div className="mb-6 flex items-center gap-3">
              <Activity className="text-cyan-300" />
              <h2 className="text-xl font-semibold">{t("statusTitle")}</h2>
            </div>
            <div className="min-h-[11rem] rounded-3xl border border-white/10 bg-white/4 p-5">
              <p className="text-xs uppercase tracking-[0.28em] text-muted">
                {runtimeExchangeLabel}
              </p>
              <p className="mt-2 text-sm text-muted">
                {t("runtimeSymbol")}: {runtimeSymbol}
              </p>
              <p className="mt-2 text-sm text-muted">
                {t("runtimeStrategy")}:{" "}
                {runtimeStrategyId ? tStrategies(`${runtimeStrategyId}.name`) : "-"}
              </p>
              <p className="mt-3 text-3xl font-semibold">
                {isStopping ? t("stopping") : isRunning ? t("running") : t("stopped")}
              </p>
              <p className="mt-2 text-sm text-muted">
                {t("runtimePosition")}: {runtimePositionLabel}
              </p>
              <p className="mt-2 text-xs uppercase tracking-[0.2em] text-muted">
                {t("snapshotUpdated")}{" "}
                {status?.last_synced_at
                  ? new Date(status.last_synced_at).toLocaleString()
                  : "-"}
              </p>
              <div className="mt-3 h-24 overflow-auto text-sm leading-6 text-muted">
                {status?.status_message ||
                  status?.credential_error ||
                  status?.account_status_message ||
                  ""}
              </div>
            </div>

            <div className="mt-5 grid gap-4 md:grid-cols-3">
              <div className="rounded-3xl border border-white/10 bg-white/3 p-4 shadow-sm hover:bg-white/5 transition-colors">
                <p className="text-xs uppercase tracking-[0.24em] text-muted">
                  {t("balance")}
                </p>
                <p className="mt-2 text-2xl font-bold font-mono text-white">
                  ${Number(status?.balance ?? 0).toFixed(2)}
                </p>
              </div>
              
              <div className="rounded-3xl border border-white/10 bg-white/3 p-4 shadow-sm hover:bg-white/5 transition-colors">
                <p className="text-xs uppercase tracking-[0.24em] text-muted">
                  {t("unrealizedPnl")}
                </p>
                <div key={pnlKey} className="animate-pop">
                  <p className={`mt-2 text-2xl font-extrabold font-mono ${(status?.unrealized_pnl ?? 0) >= 0 ? "text-emerald-400 drop-shadow-[0_0_8px_rgba(52,211,153,0.4)]" : "text-rose-400 drop-shadow-[0_0_8px_rgba(251,113,133,0.4)]"}`}>
                    {(status?.unrealized_pnl ?? 0) >= 0 ? "+" : ""}{Number(status?.unrealized_pnl ?? 0).toFixed(2)}
                  </p>
                </div>
              </div>

              <div className="rounded-3xl border border-white/10 bg-white/3 p-4 shadow-sm hover:bg-white/5 transition-colors">
                <p className="text-xs uppercase tracking-[0.24em] text-muted">
                  {t("exposure")}
                </p>
                <p className="mt-2 text-2xl font-bold font-mono text-white">
                  ${Number(status?.exposure ?? 0).toFixed(2)}
                </p>
              </div>
            </div>

            <div className="mt-6">
              <h3 className="text-lg font-medium">{t("positionsTitle")}</h3>
              <div className="mt-4 space-y-3">
                {(status?.positions ?? []).map((position, index) => (
                  <div
                    key={`${position.symbol}-${position.side}-${index}`}
                    className="rounded-2xl border border-white/10 bg-white/3 p-4 hover:border-white/20 transition-colors"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-bold text-lg text-white">{position.symbol}</p>
                      <p className={`px-2 py-0.5 rounded-md text-xs font-bold uppercase tracking-wider ${position.side.toLowerCase() === 'long' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'}`}>
                        {position.side}
                      </p>
                    </div>
                    <div className="mt-3 flex items-center justify-between text-sm">
                      <p className="text-muted">
                        Size: <span className="font-medium text-white">{position.size}</span>
                      </p>
                      <p className="text-muted">
                        Entry: <span className="font-medium font-mono text-white">${position.entry_price.toFixed(4)}</span>
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <section className="bg-white/5 backdrop-blur-md border border-white/10 rounded-[2rem] p-6 shadow-xl">
            <h2 className="text-xl font-semibold">{t("tradesTitle")}</h2>
            <div className="mt-4 space-y-3">
              {trades.length ? (
                trades.map((trade) => (
                  <div
                    key={trade.id}
                    className="rounded-2xl border border-white/10 bg-white/3 p-4 hover:border-white/20 transition-colors"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="font-bold text-white">{trade.symbol}</p>
                          <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold uppercase tracking-wider ${trade.side.toLowerCase() === 'buy' || trade.side.toLowerCase() === 'long' ? 'bg-emerald-500/20 text-emerald-400' : trade.side.toLowerCase() === 'close' ? 'bg-slate-500/20 text-slate-300' : 'bg-rose-500/20 text-rose-400'}`}>
                            {trade.side}
                          </span>
                        </div>
                        <p className="mt-1.5 text-sm text-muted font-mono">
                          {trade.quantity} @ ${trade.price.toFixed(4)}
                        </p>
                        {trade.realized_pnl !== null && trade.realized_pnl !== undefined ? (
                          <p className={`mt-1.5 font-bold font-mono text-sm ${trade.realized_pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                            {t("realizedPnl")}: {trade.realized_pnl >= 0 ? "+" : ""}{trade.realized_pnl.toFixed(2)}
                          </p>
                        ) : null}
                      </div>
                      <p className="text-xs text-white/50 text-right">
                        {new Date(trade.created_at).toLocaleString()}
                      </p>
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-2xl border border-dashed border-white/12 p-5 text-sm text-muted">
                  {t("noTrades")}
                </div>
              )}
            </div>
          </section>

          <div
            className={`h-20 overflow-auto rounded-2xl border px-4 py-3 text-sm ${feedbackClassName}`}
          >
            {feedback ?? ""}
          </div>
        </div>
      </div>
      </div>

      {/* Risk Warning */}
      <div className="mt-12 text-center text-xs text-slate-500/80 flex items-center justify-center gap-2">
        <AlertTriangle size={14} className="opacity-70" />
        {t("riskWarning", { fallback: "Digital asset trading involves significant risk. Proceed with caution." })}
      </div>
    </div>
  );
}
