'use client';

import React, { useState, useEffect, useRef } from 'react';
import { 
  Activity, 
  TrendingUp, 
  Shield, 
  Settings, 
  Briefcase, 
  Calendar, 
  BarChart2, 
  Play,
  ChevronLeft,
  ChevronRight,
  Bot,
  BookOpen,
  LayoutDashboard,
  Sliders,
  Terminal,
  Server,
  Zap,
  Pause,
  Square
} from 'lucide-react';
import confetti from 'canvas-confetti';

import { Strategy, StrategyInstance, Trade, OptionChainItem, IndicatorCondition, StrategyType } from './types';
import { API_BASE, WS_BASE } from './config';
import Header from './components/Header';
import OptionChain from './components/OptionChain';
import ActivePositions from './components/ActivePositions';
import ActiveAlgorithms from './components/ActiveAlgorithms';
import ActivationModal from './components/ActivationModal';
import CustomBuilder from './components/CustomBuilder';
import TradeLedger from './components/TradeLedger';
import SettingsPage from './components/SettingsPage';
import PortfolioPage from './components/PortfolioPage';
import HistoricalChart from './components/HistoricalChart';
import BacktestPage from './components/BacktestPage';
import Watchlist from './components/Watchlist';

export default function StockerDashboard() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [serverHealth, setServerHealth] = useState(true);
  const [refreshChartKey, setRefreshChartKey] = useState(0);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  const handleSelectTab = (tabName: string) => {
    setActiveTab(tabName);
    setMobileSidebarOpen(false);
  };

  // Dynamic Workspace Toggle inside the Algorithms section
  const [isBuildingStrategy, setIsBuildingStrategy] = useState(false);

  // Core Data States
  const [spotPrice, setSpotPrice] = useState(23909.55);
  const [optionChain, setOptionChain] = useState<OptionChainItem[]>([]);
  const [positions, setPositions] = useState<Trade[]>([]);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [instances, setInstances] = useState<StrategyInstance[]>([]);
  const [activeStrategyToActivate, setActiveStrategyToActivate] = useState<Strategy | null>(null);
  const [tradeHistory, setTradeHistory] = useState<Trade[]>([]);

  // Credentials States
  const [telegramToken, setTelegramToken] = useState('');
  const [telegramChatId, setTelegramChatId] = useState('');
  const [kiteApiKey, setKiteApiKey] = useState('');
  const [kiteApiSecret, setKiteApiSecret] = useState('');
  const [aliceClientId, setAliceClientId] = useState('');
  const [aliceApiKey, setAliceApiKey] = useState('');
  const [dhanClientId, setDhanClientId] = useState('');
  const [dhanAccessToken, setDhanAccessToken] = useState('');
  const [dhanTotpSecret, setDhanTotpSecret] = useState('');
  const [activeBroker, setActiveBroker] = useState('kite');
  const [engineStatus, setEngineStatus] = useState<'RUNNING' | 'PAUSED' | 'STOPPED'>('RUNNING');
  const [isPaperRunning, setIsPaperRunning] = useState(false);
  const [isLiveRunning, setIsLiveRunning] = useState(false);

  // Broker Portfolio Balance States
  const [portfolio, setPortfolio] = useState({
    broker_name: 'kite',
    is_live: false,
    cash_balance: 500000.0,
    used_margin: 120000.0,
    collateral_margin: 50000.0,
    available_margin: 430000.0
  });

  // Strategy live running logs
  const [strategyLogs, setStrategyLogs] = useState<any[]>([]);

  // Strategy Builder Workspace States
  const [strategyId, setStrategyId] = useState('');
  const [strategyName, setStrategyName] = useState('Nifty Dynamic Scalp');
  const [strategyType, setStrategyType] = useState<StrategyType>('orb_breakout');
  const [isPaperTrade, setIsPaperTrade] = useState(true);
  const [symbolTarget, setSymbolTarget] = useState('NSE:NIFTY 50');
  const [quantity, setQuantity] = useState(50);
  const [optType, setOptType] = useState('CE');
  const [strikeSel, setStrikeSel] = useState('ATM');
  const [slPct, setSlPct] = useState(10.0);
  const [targetPct, setTargetPct] = useState(10.0);
  // ORB-specific state
  const [premiumMin, setPremiumMin] = useState(100);
  const [premiumMax, setPremiumMax] = useState(200);
  const [postBreakoutTf, setPostBreakoutTf] = useState('5minute');
  
  // Custom Option strategy parameters
  const [strikeOffset, setStrikeOffset] = useState<number>(0);
  const [expiryType, setExpiryType] = useState<string>('CURRENT_WEEKLY');
  const [trailSlPct, setTrailSlPct] = useState<number>(0.0);
  
  // Entry & Exit Conditions builders
  const [entryConditions, setEntryConditions] = useState<IndicatorCondition[]>([
    { indicator: 'EMA', period: 9, comparison: 'CROSS_ABOVE', target: 'INDICATOR', target_indicator: 'EMA', target_period: 20 }
  ]);
  const [exitConditions, setExitConditions] = useState<IndicatorCondition[]>([
    { indicator: 'RSI', period: 14, comparison: 'CROSS_BELOW', target: 'VALUE', value: 30 }
  ]);

  const wsRef = useRef<WebSocket | null>(null);

  // Global theme state
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');

  useEffect(() => {
    if (typeof window !== 'undefined') {
      const savedTheme = localStorage.getItem('stocker-theme') as 'dark' | 'light' || 'dark';
      setTheme(savedTheme);
      document.documentElement.setAttribute('data-theme', savedTheme);
    }
  }, []);

  const handleToggleTheme = () => {
    const nextTheme = theme === 'dark' ? 'light' : 'dark';
    setTheme(nextTheme);
    localStorage.setItem('stocker-theme', nextTheme);
    document.documentElement.setAttribute('data-theme', nextTheme);
  };

  const fetchEngineStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/engine/status`);
      if (res.ok) {
        const data = await res.json();
        setEngineStatus(data.status);
        setIsPaperRunning(data.is_paper_running);
        setIsLiveRunning(data.is_live_running);
      }
    } catch (err) {
      console.error("Failed to fetch engine status:", err);
    }
  };

  const pauseEngine = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/engine/pause`, { method: 'POST' });
      if (res.ok) {
        setEngineStatus('PAUSED');
      } else {
        alert('Failed to pause trading engine.');
      }
    } catch (err) {
      console.error(err);
      alert('Error pausing engine.');
    }
  };

  const stopEngine = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/engine/stop`, { method: 'POST' });
      if (res.ok) {
        setEngineStatus('STOPPED');
      } else {
        alert('Failed to stop trading engine.');
      }
    } catch (err) {
      console.error(err);
      alert('Error stopping engine.');
    }
  };

  const resumeEngine = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/engine/resume`, { method: 'POST' });
      if (res.ok) {
        setEngineStatus('RUNNING');
      } else {
        alert('Failed to resume trading engine.');
      }
    } catch (err) {
      console.error(err);
      alert('Error resuming engine.');
    }
  };

  // ---------------------------------------------------------
  // Backend Integrations (Fetch & Save)
  // ---------------------------------------------------------
  
  useEffect(() => {
    setStrategyId('strat_' + Math.random().toString(36).substring(2, 7));
    fetchStrategies();
    fetchInstances();
    fetchTradeHistory();
    fetchCredentials();
    fetchPortfolio();
    fetchEngineStatus();
    connectWebSocket();
    
    // Automatically detect and exchange request_token from Zerodha Kite login redirect!
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      const reqToken = params.get('request_token');
      if (reqToken) {
        handleSelectTab('settings');
        fetch(`${API_BASE}/api/broker/zerodha-login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ request_token: reqToken })
        })
        .then(res => res.json())
        .then(result => {
          if (result.status === 'SUCCESS') {
            confetti({
              particleCount: 150,
              spread: 80,
              origin: { y: 0.6 }
            });
            alert('🎉 Zerodha Kite live trading session successfully activated!');
            window.history.replaceState({}, document.title, window.location.pathname);
            fetchPortfolio();
          } else {
            alert('❌ Zerodha Daily Login Failed: ' + result.message);
          }
        })
        .catch(() => {
          alert('❌ Failed to establish secure connection with local trading gateway.');
        });
      }
    }
    
    const interval = setInterval(fetchPortfolio, 5000);
    
    return () => {
      if (wsRef.current) wsRef.current.close();
      clearInterval(interval);
    };
  }, []);

  const connectWebSocket = () => {
    try {
      const ws = new WebSocket(`${WS_BASE}/api/ws`);
      wsRef.current = ws;

      ws.onopen = () => {
        setWsConnected(true);
        setServerHealth(true);
        console.log('Stocker Real-time Tick WS Connected.');
      };

      ws.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        if (payload.type === 'STREAM_TICK') {
          setSpotPrice(payload.spot_price);
          setOptionChain(payload.option_chain);
          setPositions(payload.positions);
          if (payload.strategy_logs) {
            setStrategyLogs(payload.strategy_logs);
          }
          if (payload.engine_status) {
            setEngineStatus(payload.engine_status);
          }
          if (payload.hasOwnProperty('is_paper_running')) {
            setIsPaperRunning(payload.is_paper_running);
          }
          if (payload.hasOwnProperty('is_live_running')) {
            setIsLiveRunning(payload.is_live_running);
          }
        }
      };

      ws.onclose = () => {
        setWsConnected(false);
        console.log('WS Disconnected. Attempting reconnection in 5s...');
        setTimeout(connectWebSocket, 5000);
      };

      ws.onerror = () => {
        setWsConnected(false);
      };
    } catch (e) {
      setWsConnected(false);
    }
  };

  const calculateTotalPnL = (mode: 'PAPER' | 'LIVE') => {
    const closedPnL = tradeHistory
      .filter((t) => t.mode.toUpperCase() === mode)
      .reduce((sum, t) => sum + (t.pnl || 0), 0);
      
    const activePnL = positions
      .filter((t) => t.mode.toUpperCase() === mode)
      .reduce((sum, t) => sum + (t.pnl || 0), 0);
      
    return closedPnL + activePnL;
  };

  const fetchPortfolio = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/broker/portfolio`);
      if (res.ok) {
        const data = await res.json();
        setPortfolio(data);
      }
    } catch (e) {
      console.log('Failed to fetch broker portfolio margins.');
    }
  };

  const fetchCredentials = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/credentials`);
      if (res.ok) {
        const creds = await res.json();
        const tg = creds.find((c: any) => c.broker_name === 'telegram');
        const kt = creds.find((c: any) => c.broker_name === 'kite');
        const ab = creds.find((c: any) => c.broker_name === 'aliceblue');
        
        if (tg) {
          setTelegramToken(tg.api_key);
          setTelegramChatId(tg.api_secret || '');
        }
        if (kt) {
          setKiteApiKey(kt.api_key);
          setKiteApiSecret(kt.api_secret || '');
        }
        if (ab) {
          setAliceClientId(ab.api_key);
          setAliceApiKey(ab.api_secret || '');
        }
        const dh = creds.find((c: any) => c.broker_name === 'dhan');
        if (dh) {
          setDhanClientId(dh.api_key);
          setDhanAccessToken(dh.api_secret || '');
          setDhanTotpSecret(dh.totp_secret || '');
        }

        const activeCred = creds.find((c: any) => c.broker_name !== 'telegram' && c.active);
        if (activeCred) {
          setActiveBroker(activeCred.broker_name);
        }
      }
    } catch (e) {
      console.log('Credentials fetch skipped or backend offline');
    }
  };

  const fetchStrategies = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/strategies`);
      if (res.ok) {
        const data = await res.json();
        setStrategies(data);
      }
    } catch (e) {
      setServerHealth(false);
    }
  };

  const fetchInstances = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/strategy-instances`);
      if (res.ok) {
        const data = await res.json();
        setInstances(data);
      }
    } catch (e) {
      setServerHealth(false);
    }
  };

  const fetchTradeHistory = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/trades`);
      if (res.ok) {
        const data = await res.json();
        setTradeHistory(data);
      }
    } catch (e) {
      setServerHealth(false);
    }
  };

  const saveCredentials = async (broker: string, key: string, secret: string, totpSecret?: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/credentials`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          broker_name: broker,
          api_key: key,
          api_secret: secret,
          totp_secret: totpSecret
        })
      });
      if (res.ok) {
        confetti({ particleCount: 60, spread: 60, colors: ['#10B981', '#6366F1'] });
        fetchCredentials();
      }
    } catch (e) {
      alert('Failed to connect to API backend to store credentials.');
    }
  };

  const handleSelectActiveBroker = async (broker: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/credentials/select-active?broker_name=${broker}`, {
        method: 'POST'
      });
      if (res.ok) {
        confetti({ particleCount: 50, spread: 40, colors: ['#8B5CF6', '#10B981'] });
        setActiveBroker(broker);
        fetchCredentials();
      }
    } catch (e) {
      console.error('Error switching active broker', e);
    }
  };

  const handleCreateNewStrategyClick = () => {
    setStrategyId('strat_' + Math.random().toString(36).substring(2, 7));
    setStrategyName('Nifty Dynamic Scalp');
    setIsPaperTrade(true);
    setSymbolTarget('NSE:NIFTY 50');
    setQuantity(50);
    setOptType('CE');
    setStrikeSel('ATM');
    setStrikeOffset(0);
    setExpiryType('CURRENT_WEEKLY');
    setTrailSlPct(0.0);
    setSlPct(4.0);
    setTargetPct(8.0);
    setEntryConditions([
      { indicator: 'EMA', period: 9, comparison: 'CROSS_ABOVE', target: 'INDICATOR', target_indicator: 'EMA', target_period: 20 }
    ]);
    setExitConditions([
      { indicator: 'RSI', period: 14, comparison: 'CROSS_BELOW', target: 'VALUE', value: 30 }
    ]);
    handleSelectTab('builder');
    setIsBuildingStrategy(true);
  };

  const handleEditStrategy = (strat: Strategy) => {
    try {
      const config = JSON.parse(strat.config_json);
      const action = config.action || {};
      const rules = config.rules || {};
      const sType = config.strategy_type || 'custom';
      
      setStrategyId(strat.id);
      setStrategyName(strat.name);
      setStrategyType(sType);
      setIsPaperTrade(strat.paper_trade);
      setSymbolTarget(config.symbols?.[0] || 'NSE:NIFTY 50');
      setQuantity(action.quantity || 50);
      setStrikeSel(config.option_selection?.strike_selection || action.strike_selection || 'ATM');
      setStrikeOffset(action.strike_offset || 0);
      setExpiryType(action.expiry_type || 'CURRENT_WEEKLY');
      setTrailSlPct(action.trail_sl_pct || 0.0);

      if (sType === 'orb_breakout') {
        setOptType('AUTO');
        const risk = config.risk || {};
        setSlPct(risk.stop_loss_pct || 10.0);
        setTargetPct(risk.target_pct || 10.0);
        const optSel = config.option_selection || {};
        setPremiumMin(optSel.premium_min || 100);
        setPremiumMax(optSel.premium_max || 200);
        setPostBreakoutTf(config.timeframes?.post_1030_tf || '5minute');
      } else {
        setOptType(action.option_type || 'CE');
        const slCond = rules.exit?.conditions?.find((c: any) => c.indicator === 'STOP_LOSS_PCT');
        const tgtCond = rules.exit?.conditions?.find((c: any) => c.indicator === 'TARGET_PCT');
        if (slCond) setSlPct(slCond.value || 4.0);
        if (tgtCond) setTargetPct(tgtCond.value || 8.0);
        
        const filteredEntry = rules.entry?.conditions || [];
        const filteredExit = (rules.exit?.conditions || []).filter(
          (c: any) => c.indicator !== 'STOP_LOSS_PCT' && c.indicator !== 'TARGET_PCT'
        );
        
        setEntryConditions(filteredEntry);
        setExitConditions(filteredExit.length > 0 ? filteredExit : [
          { indicator: 'RSI', period: 14, comparison: 'CROSS_BELOW', target: 'VALUE', value: 30 }
        ]);
      }
      
      handleSelectTab('builder');
      setIsBuildingStrategy(true);
    } catch (e) {
      alert('Failed to parse strategy schema parameters.');
    }
  };

  const saveStrategy = async () => {
    let config: any;

    if (strategyType === 'orb_breakout') {
      config = {
        strategy_type: 'orb_breakout',
        symbols: [symbolTarget],
        timeframes: {
          opening_candle_tf: 'minute',
          pre_1030_tf: 'minute',
          post_1030_tf: postBreakoutTf,
        },
        opening_range: { candle_time: '09:15' },
        option_selection: {
          strike_selection: strikeSel,
          premium_min: premiumMin,
          premium_max: premiumMax,
          shift_to_otm_if_exceeded: true,
        },
        risk: {
          target_pct: targetPct,
          stop_loss_pct: slPct,
        },
        action: {
          instrument_type: 'OPTION',
          quantity: quantity,
          expiry_type: 'WEEKLY',
          paper_trade: isPaperTrade,
        },
        timeline: {
          start_time: '09:15',
          end_time: '15:15',
          days_of_week: [1, 2, 3, 4, 5],
        },
      };
    } else {
      config = {
        strategy_type: 'custom',
        symbols: [symbolTarget],
        timeline: {
          start_time: '09:20',
          end_time: '15:15',
          days_of_week: [1, 2, 3, 4, 5]
        },
        rules: {
          entry: {
            operator: 'AND',
            conditions: entryConditions
          },
          exit: {
            operator: 'OR',
            conditions: [
              ...exitConditions,
              { indicator: 'STOP_LOSS_PCT', comparison: 'LESS_THAN', target: 'VALUE', value: slPct },
              { indicator: 'TARGET_PCT', comparison: 'GREATER_THAN', target: 'VALUE', value: targetPct }
            ]
          }
        },
        action: {
          instrument_type: 'OPTION',
          option_type: optType,
          strike_selection: strikeSel,
          strike_offset: strikeOffset,
          expiry_type: expiryType,
          trail_sl_pct: trailSlPct,
          quantity: quantity,
          paper_trade: isPaperTrade
        }
      };
    }

    try {
      const res = await fetch(`${API_BASE}/api/strategies`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: strategyId,
          name: strategyName,
          paper_trade: isPaperTrade,
          config: config
        })
      });

      if (res.ok) {
        confetti({ particleCount: 100, spread: 80, origin: { y: 0.6 } });
        setStrategyId('strat_' + Math.random().toString(36).substring(2, 7));
        fetchStrategies();
        setIsBuildingStrategy(false);
      } else {
        const errData = await res.json().catch(() => ({}));
        const errMsg = errData.detail 
          ? (typeof errData.detail === 'string' ? errData.detail : JSON.stringify(errData.detail, null, 2)) 
          : 'Unknown server validation error.';
        alert(`Failed to deploy strategy model:\n${errMsg}`);
      }
    } catch (e) {
      alert('Error creating strategy: backend server unreachable.');
    }
  };

  const toggleStrategy = async (id: string, active: boolean) => {
    try {
      await fetch(`${API_BASE}/api/strategies/${id}/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active })
      });
      fetchStrategies();
    } catch (e) {
      console.error(e);
    }
  };

  const deleteStrategy = async (id: string) => {
    if (!confirm('Are you sure you want to delete this trading strategy?')) return;
    try {
      await fetch(`${API_BASE}/api/strategies/${id}`, { method: 'DELETE' });
      fetchStrategies();
    } catch (e) {
      console.error(e);
    }
  };

  const deployInstance = async (data: {
    template_id: string;
    symbol: string;
    instrument_type: string;
    quantity: number;
    stop_loss_pct: number;
    target_pct: number;
    premium_min: number;
    premium_max: number;
    paper_trade: boolean;
  }) => {
    try {
      const res = await fetch(`${API_BASE}/api/strategy-instances`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      if (res.ok) {
        confetti({ particleCount: 100, spread: 80, origin: { y: 0.6 } });
        fetchInstances();
        setActiveStrategyToActivate(null);
      } else {
        const errData = await res.json().catch(() => ({}));
        alert(`Failed to activate instance: ${errData.detail || 'Unknown server error.'}`);
      }
    } catch (e) {
      alert('Error deploying instance: backend server unreachable.');
    }
  };

  const toggleInstance = async (id: number, active: boolean) => {
    try {
      const res = await fetch(`${API_BASE}/api/strategy-instances/${id}/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active })
      });
      if (res.ok) {
        fetchInstances();
      }
    } catch (e) {
      console.error(e);
    }
  };

  const deleteInstance = async (id: number) => {
    if (!confirm('Are you sure you want to stop and delete this active running instance?')) return;
    try {
      const res = await fetch(`${API_BASE}/api/strategy-instances/${id}`, { method: 'DELETE' });
      if (res.ok) {
        fetchInstances();
      }
    } catch (e) {
      console.error(e);
    }
  };

  const sendTelegramStatus = async (id: number) => {
    try {
      const res = await fetch(`${API_BASE}/api/strategies/${id}/telegram-status`, {
        method: 'POST'
      });
      const data = await res.json();
      if (data.status === 'SUCCESS') {
        alert('Strategy status bulletin sent to Telegram successfully!');
      } else {
        alert(`Failed to send status update: ${data.message || 'Unknown error'}`);
      }
    } catch (e) {
      console.error(e);
      alert(`Error connecting to status endpoint: ${e}`);
    }
  };

  const sendTelegramLedger = async (filteredTrades: any[]) => {
    if (filteredTrades.length === 0) {
      alert('No trades in the filtered ledger to send!');
      return;
    }
    try {
      const tradeIds = filteredTrades.map((t) => t.id);
      const res = await fetch(`${API_BASE}/api/trades/telegram-report`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trade_ids: tradeIds })
      });
      const data = await res.json();
      if (data.status === 'SUCCESS') {
        alert('Trade History Ledger summary dispatched to Telegram successfully!');
      } else {
        alert(`Failed to send Ledger report: ${data.message || 'Unknown error'}`);
      }
    } catch (e) {
      console.error(e);
      alert(`Error connecting to ledger report API: ${e}`);
    }
  };

  const resetPaperRecords = async () => {
    if (!confirm('This will wipe all paper positions, logs, and summaries to restart fresh. Proceed?')) return;
    try {
      const res = await fetch(`${API_BASE}/api/paper-reset`, { method: 'POST' });
      if (res.ok) {
        confetti({ particleCount: 150, spread: 100 });
        fetchTradeHistory();
        setPositions([]);
      }
    } catch (e) {
      alert('Error clearing database records.');
    }
  };

  const triggerTestTelegram = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/test-telegram`, { method: 'POST' });
      if (res.ok) {
        alert('Test notification dispatched. Check your Telegram chat!');
      }
    } catch (e) {
      alert('Error communicating with Telegram Bot service.');
    }
  };

  const handleStrikeSelect = (type: 'CE' | 'PE', strikeSelection: string) => {
    setOptType(type);
    setStrikeSel(strikeSelection);
    handleSelectTab('builder');
    setIsBuildingStrategy(true);
  };

  const handleForceExit = async (tradeId: number) => {
    if (!confirm('Are you sure you want to force exit this active position immediately?')) return;
    try {
      const res = await fetch(`${API_BASE}/api/trades/${tradeId}/exit`, { method: 'POST' });
      if (res.ok) {
        confetti({ particleCount: 80, spread: 60, colors: ['#EF4444', '#F59E0B'] });
        fetchTradeHistory();
      } else {
        alert('Failed to execute manual force exit.');
      }
    } catch (e) {
      alert('Error communicating with execution engine.');
    }
  };

  return (
    <div className="app-container">
      {/* Mobile Sidebar Overlay Backdrop */}
      {mobileSidebarOpen && (
        <div 
          className="sidebar-overlay" 
          onClick={() => setMobileSidebarOpen(false)}
        />
      )}

      {/* Collapsible Left Sidebar */}
      <aside className={`sidebar ${sidebarCollapsed ? 'collapsed' : ''} ${mobileSidebarOpen ? 'mobile-open' : ''}`}>
        {/* Brand / Logo */}
        <div className="sidebar-logo-container">
          <Activity size={24} className="glow-green" />
          <span className="sidebar-logo-text gradient-text" style={{ fontWeight: 800 }}>STOCKER</span>
          {!sidebarCollapsed && (
            <span style={{ fontSize: '9px', padding: '1px 6px', background: 'rgba(99, 102, 241, 0.15)', color: '#8B5CF6', borderRadius: '8px', border: '1px solid rgba(99, 102, 241, 0.3)', marginLeft: '6px' }}>v1.5</span>
          )}
        </div>

        {/* Navigation Menus */}
        <nav className="sidebar-menu">
          {/* Menu Group: Trading Desk */}
          <div className="sidebar-menu-group">
            <span className="sidebar-menu-title">Trading Desk</span>
            <button 
              onClick={() => handleSelectTab('dashboard')} 
              className={`sidebar-item ${activeTab === 'dashboard' ? 'active' : ''}`}
              title="Market Dashboard"
            >
              <LayoutDashboard size={18} />
              <span className="sidebar-item-label">Market Dashboard</span>
            </button>
            <button 
              onClick={() => handleSelectTab('ledger')} 
              className={`sidebar-item ${activeTab === 'ledger' ? 'active' : ''}`}
              title="Trade History & Ledger"
            >
              <BookOpen size={18} />
              <span className="sidebar-item-label">Trade History & Ledger</span>
            </button>
            <button 
              onClick={() => handleSelectTab('portfolio')} 
              className={`sidebar-item ${activeTab === 'portfolio' ? 'active' : ''}`}
              title="Broker Portfolio"
            >
              <Briefcase size={18} />
              <span className="sidebar-item-label">Broker Portfolio</span>
            </button>
          </div>

          {/* Menu Group: Strategy Engine */}
          <div className="sidebar-menu-group">
            <span className="sidebar-menu-title">Strategy Engine</span>
            <button 
              onClick={() => { handleSelectTab('builder'); setIsBuildingStrategy(false); }} 
              className={`sidebar-item ${activeTab === 'builder' ? 'active' : ''}`}
              title="Trading Algorithms"
            >
              <Sliders size={18} />
              <span className="sidebar-item-label">Trading Algorithms</span>
            </button>
            <button 
              onClick={() => handleSelectTab('backtest')} 
              className={`sidebar-item ${activeTab === 'backtest' ? 'active' : ''}`}
              title="Backtest Simulator"
            >
              <BarChart2 size={18} />
              <span className="sidebar-item-label">Backtest Simulator</span>
            </button>
          </div>

          {/* Menu Group: System */}
          <div className="sidebar-menu-group">
            <span className="sidebar-menu-title">System</span>
            <button 
              onClick={() => handleSelectTab('settings')} 
              className={`sidebar-item ${activeTab === 'settings' ? 'active' : ''}`}
              title="System Settings"
            >
              <Settings size={18} />
              <span className="sidebar-item-label">System Settings</span>
            </button>
          </div>
        </nav>

        {/* Sidebar Footer */}
        <div className="sidebar-footer">
          {sidebarCollapsed ? (
            <div title={wsConnected ? 'LIVE FEED ACTIVE' : 'CONNECTION OFFLINE'} style={{ display: 'flex', justifyContent: 'center' }}>
              <span className={`pulsar ${wsConnected ? '' : 'red'}`} style={{ width: '10px', height: '10px' }} />
            </div>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', background: 'rgba(255,255,255,0.02)', padding: '8px 12px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.04)' }}>
              <span className={`pulsar ${wsConnected ? '' : 'red'}`} style={{ width: '8px', height: '8px' }} />
              <span style={{ color: wsConnected ? 'var(--text-primary)' : 'var(--accent-red)', fontWeight: 600 }}>
                {wsConnected ? 'FEED ONLINE' : 'FEED OFFLINE'}
              </span>
            </div>
          )}

          <button 
            className="sidebar-collapse-btn" 
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            title={sidebarCollapsed ? 'Expand Sidebar' : 'Collapse Sidebar'}
          >
            {sidebarCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          </button>
        </div>
      </aside>

      {/* Main Content Workspace */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
        <Header 
          wsConnected={wsConnected} 
          positionsCount={positions.length} 
          onRefresh={() => { fetchStrategies(); fetchInstances(); fetchTradeHistory(); setRefreshChartKey(k => k + 1); }} 
          onOpenSettings={() => handleSelectTab('settings')} 
          spotPrice={spotPrice}
          activeTab={activeTab}
          portfolio={portfolio}
          onToggleMobileSidebar={() => setMobileSidebarOpen(prev => !prev)}
          theme={theme}
          onToggleTheme={handleToggleTheme}
        />

        {!serverHealth && (
          <div className="glass-panel" style={{ margin: '16px 24px 0 24px', padding: '12px 20px', border: '1px solid rgba(244, 63, 94, 0.4)', background: 'rgba(244, 63, 94, 0.1)', display: 'flex', alignItems: 'center', gap: '12px', color: 'var(--accent-red)' }}>
            <span style={{ fontSize: '13px', fontWeight: 500 }}>Backend Stocker engine is unreachable. Please verify that the FastAPI backend server is running on port 8000.</span>
          </div>
        )}

        <main style={{ flex: 1, overflowY: 'auto', paddingBottom: '30px' }}>
        
        {/* ================= TAB: DASHBOARD ================= */}
        {activeTab === 'dashboard' && (
          <div className="dashboard-grid animate-slide-in">
            
            {/* Left Hand Options & Market Feed */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
              
              {/* Top Row: Spot Price & Dual P&L Boards */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
                
                {/* Index Spot Price */}
                <div className="glass-panel" style={{ 
                  padding: '20px', 
                  display: 'flex', 
                  flexDirection: 'column', 
                  justifyContent: 'center',
                  borderLeft: '4px solid var(--accent-green)',
                  background: 'radial-gradient(circle at top right, rgba(16, 185, 129, 0.05), transparent)'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>NIFTY INDEX SPOT</span>
                    {(() => {
                      const openBaseline = 23812.50;
                      const diffVal = spotPrice - openBaseline;
                      const diffPct = (diffVal / openBaseline) * 100;
                      const isDiffPos = diffVal >= 0;
                      return (
                        <span style={{ fontSize: '10px', color: isDiffPos ? 'var(--accent-green)' : 'var(--accent-red)', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '3px' }}>
                          {isDiffPos ? '▲' : '▼'} {isDiffPos ? '+' : ''}{diffVal.toFixed(2)} ({diffPct.toFixed(2)}%)
                        </span>
                      );
                    })()}
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginTop: '4px' }}>
                    <p style={{ fontSize: '28px', fontWeight: 800, fontFamily: 'var(--font-display)', margin: 0 }} className="glow-green">
                      ₹{spotPrice.toFixed(2)}
                    </p>
                    <span style={{ fontSize: '11px', color: 'var(--accent-yellow)', fontWeight: 600 }}>3 Days Expiry</span>
                  </div>
                </div>

                {/* Paper Sandbox P&L */}
                {(() => {
                  const pnl = calculateTotalPnL('PAPER');
                  const isPos = pnl >= 0;
                  return (
                    <div className="glass-panel" style={{ 
                      padding: '20px', 
                      display: 'flex', 
                      flexDirection: 'column', 
                      justifyContent: 'center', 
                      borderLeft: isPos ? '4px solid var(--accent-green)' : '4px solid var(--accent-red)',
                      background: isPos 
                        ? 'radial-gradient(circle at top right, rgba(16, 185, 129, 0.06), transparent)' 
                        : 'radial-gradient(circle at top right, rgba(244, 63, 94, 0.06), transparent)'
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>PAPER SANDBOX P&L</span>
                        <span style={{ fontSize: '9px', background: 'rgba(139, 92, 246, 0.15)', color: '#8B5CF6', padding: '1px 6px', borderRadius: '8px', fontWeight: 700 }}>SANDBOX</span>
                      </div>
                      <p style={{ fontSize: '28px', fontWeight: 800, fontFamily: 'var(--font-display)', marginTop: '4px', margin: 0, color: isPos ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                        {isPos ? '+' : ''}₹{pnl.toFixed(2)}
                      </p>
                    </div>
                  );
                })()}

                {/* Live Realtime P&L */}
                {(() => {
                  const pnl = calculateTotalPnL('LIVE');
                  const isPos = pnl >= 0;
                  const activeBrokerName = activeBroker === 'kite' ? 'Zerodha' : 'AliceBlue';
                  return (
                    <div className="glass-panel" style={{ 
                      padding: '20px', 
                      display: 'flex', 
                      flexDirection: 'column', 
                      justifyContent: 'center', 
                      borderLeft: isPos ? '4px solid var(--accent-green)' : '4px solid var(--accent-red)',
                      background: isPos 
                        ? 'radial-gradient(circle at top right, rgba(16, 185, 129, 0.06), transparent)' 
                        : 'radial-gradient(circle at top right, rgba(244, 63, 94, 0.06), transparent)'
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>LIVE TRADING P&L</span>
                        <span style={{ fontSize: '9px', background: 'rgba(16, 185, 129, 0.15)', color: 'var(--accent-green)', padding: '1px 6px', borderRadius: '8px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '3px' }}>
                          <span style={{ width: '4px', height: '4px', borderRadius: '50%', background: 'var(--accent-green)', display: 'inline-block' }} className="pulse-slow" /> {activeBrokerName}
                        </span>
                      </div>
                      <p style={{ fontSize: '28px', fontWeight: 800, fontFamily: 'var(--font-display)', marginTop: '4px', margin: 0, color: isPos ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                        {isPos ? '+' : ''}₹{pnl.toFixed(2)}
                      </p>
                    </div>
                  );
                })()}

              </div>

              {/* Broker Portfolio Margin board */}
              <div className="glass-panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h3 style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Shield size={14} style={{ color: portfolio.is_live ? '#10B981' : '#EF4444' }} /> Live Broker Balances & Portfolio Margins
                  </h3>
                  <span style={{ 
                    fontSize: '10px', 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: '6px', 
                    color: portfolio.is_live ? '#10B981' : '#EF4444', 
                    background: portfolio.is_live ? 'rgba(16, 185, 129, 0.08)' : 'rgba(239, 68, 68, 0.08)', 
                    padding: '4px 10px', 
                    borderRadius: '6px',
                    border: portfolio.is_live ? '1px solid rgba(16, 185, 129, 0.2)' : '1px solid rgba(239, 68, 68, 0.2)'
                  }}>
                    <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: portfolio.is_live ? '#10B981' : '#EF4444', display: 'inline-block' }}></span>
                    {portfolio.is_live ? `CONNECTED: ${portfolio.broker_name.toUpperCase()}` : 'BROKER DISCONNECTED'}
                  </span>
                </div>
                
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '12px' }}>
                  
                  <div style={{ background: 'rgba(0,0,0,0.2)', padding: '12px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.02)' }}>
                    <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Cash Balance</span>
                    <p style={{ fontSize: '18px', fontWeight: 700, marginTop: '4px', fontFamily: 'monospace', color: portfolio.is_live ? '#fff' : 'var(--text-muted)' }}>
                      {portfolio.is_live ? `₹${portfolio.cash_balance.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'}
                    </p>
                  </div>

                  <div style={{ background: 'rgba(0,0,0,0.2)', padding: '12px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.02)' }}>
                    <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Available Margin</span>
                    <p style={{ fontSize: '18px', fontWeight: 700, marginTop: '4px', color: portfolio.is_live ? '#10B981' : 'var(--text-muted)', fontFamily: 'monospace' }}>
                      {portfolio.is_live ? `₹${portfolio.available_margin.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'}
                    </p>
                  </div>

                  <div style={{ background: 'rgba(0,0,0,0.2)', padding: '12px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.02)' }}>
                    <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Used Margin</span>
                    <p style={{ fontSize: '18px', fontWeight: 700, marginTop: '4px', color: portfolio.is_live ? '#EF4444' : 'var(--text-muted)', fontFamily: 'monospace' }}>
                      {portfolio.is_live ? `₹${portfolio.used_margin.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'}
                    </p>
                  </div>

                  <div style={{ background: 'rgba(0,0,0,0.2)', padding: '12px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.02)' }}>
                    <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Collateral</span>
                    <p style={{ fontSize: '18px', fontWeight: 700, marginTop: '4px', color: portfolio.is_live ? '#F59E0B' : 'var(--text-muted)', fontFamily: 'monospace' }}>
                      {portfolio.is_live ? `₹${portfolio.collateral_margin.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'}
                    </p>
                  </div>

                </div>
              </div>

              {/* Interactive Spot Price Chart */}
              <HistoricalChart 
                symbol={symbolTarget} 
                refreshTrigger={refreshChartKey} 
                theme={theme}
              />

              {/* Options Chain Grid */}
              <OptionChain 
                spotPrice={spotPrice} 
                optionChain={optionChain} 
                onStrikeSelect={handleStrikeSelect} 
              />
            </div>

            {/* Right Hand Running Trades & Strategy Status */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
              
              {/* Active Positions Board */}
              <ActivePositions positions={positions} onForceExit={handleForceExit} />

              {/* Stock Watchlist */}
              <Watchlist 
                onSelectSymbol={(sym) => setSymbolTarget(sym)} 
                selectedSymbol={symbolTarget} 
              />

              {/* Deployed Algos Controller */}
              <ActiveAlgorithms 
                templates={strategies}
                instances={instances}
                onActivateClick={(strat) => setActiveStrategyToActivate(strat)}
                onToggleInstance={toggleInstance}
                onDeleteInstance={deleteInstance}
                onCreateNewClick={handleCreateNewStrategyClick}
                onDeleteTemplate={deleteStrategy}
                onSendTelegramStatus={sendTelegramStatus}
                strategyLogs={strategyLogs}
                hideBlueprints={true}
              />

              {/* Telemetry Console */}
              <div className="glass-card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h3 style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '8px', margin: 0 }}>
                    <Activity size={14} style={{ color: '#8B5CF6' }} /> Stocker Engine Telemetry
                  </h3>
                  <span style={{ 
                    fontSize: '10px', 
                    fontWeight: 700, 
                    padding: '2px 8px', 
                    borderRadius: '4px',
                    background: engineStatus === 'RUNNING' ? 'rgba(16, 185, 129, 0.15)' : engineStatus === 'PAUSED' ? 'rgba(245, 158, 11, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                    color: engineStatus === 'RUNNING' ? 'var(--accent-green)' : engineStatus === 'PAUSED' ? 'var(--accent-yellow)' : 'var(--accent-red)',
                    border: '1px solid var(--border-glass)'
                  }}>
                    {engineStatus}
                  </span>
                </div>
                
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                    <span style={{ fontSize: '9px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Tick Pipeline</span>
                    <span style={{ fontSize: '12px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-primary)' }}>
                      {engineStatus === 'RUNNING' ? (
                        <>
                          <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#10B981', display: 'inline-block' }} className="pulse-slow" /> Active (24 ticks/s)
                        </>
                      ) : engineStatus === 'PAUSED' ? (
                        <>
                          <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--accent-yellow)', display: 'inline-block' }} /> Paused (0 ticks/s)
                        </>
                      ) : (
                        <>
                          <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--accent-red)', display: 'inline-block' }} /> Inactive (Stopped)
                        </>
                      )}
                    </span>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                    <span style={{ fontSize: '9px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Engine Latency</span>
                    <span style={{ fontSize: '12px', fontWeight: 700, color: engineStatus === 'RUNNING' ? '#10B981' : 'var(--text-muted)', fontFamily: 'monospace' }}>
                      {engineStatus === 'RUNNING' ? '12 ms' : '--'}
                    </span>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                    <span style={{ fontSize: '9px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Paper Sandbox Target</span>
                    <span style={{ fontSize: '12px', fontWeight: 700, color: isPaperRunning ? 'var(--accent-green)' : 'var(--text-muted)' }}>
                      {isPaperRunning ? '🟢 Active Sandbox' : '⚫ No Active Sandbox'}
                    </span>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                    <span style={{ fontSize: '9px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Live Routing Target</span>
                    <span style={{ fontSize: '12px', fontWeight: 700, color: isLiveRunning ? 'var(--accent-green)' : 'var(--text-muted)' }}>
                      {isLiveRunning ? '⚡ Active Live Routing' : '⚫ No Active Live'}
                    </span>
                  </div>
                </div>

                {/* Engine Controller Buttons */}
                <div style={{ display: 'flex', gap: '10px', marginTop: '10px' }}>
                  {engineStatus === 'RUNNING' && (
                    <>
                      <button 
                        onClick={pauseEngine}
                        className="btn-glass"
                        style={{ flex: 1, padding: '8px', fontSize: '11px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px', color: 'var(--accent-yellow)', border: '1px solid rgba(245, 158, 11, 0.2)', cursor: 'pointer' }}
                      >
                        <Pause size={12} /> Pause Engine
                      </button>
                      <button 
                        onClick={stopEngine}
                        className="btn-glass"
                        style={{ flex: 1, padding: '8px', fontSize: '11px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px', color: 'var(--accent-red)', border: '1px solid rgba(244, 63, 94, 0.2)', cursor: 'pointer' }}
                      >
                        <Square size={12} /> Stop Engine
                      </button>
                    </>
                  )}
                  {engineStatus === 'PAUSED' && (
                    <>
                      <button 
                        onClick={resumeEngine}
                        className="btn-primary"
                        style={{ flex: 1, padding: '8px', fontSize: '11px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px', cursor: 'pointer' }}
                      >
                        <Play size={12} /> Resume Engine
                      </button>
                      <button 
                        onClick={stopEngine}
                        className="btn-glass"
                        style={{ flex: 1, padding: '8px', fontSize: '11px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px', color: 'var(--accent-red)', border: '1px solid rgba(244, 63, 94, 0.2)', cursor: 'pointer' }}
                      >
                        <Square size={12} /> Stop Engine
                      </button>
                    </>
                  )}
                  {engineStatus === 'STOPPED' && (
                    <button 
                      onClick={resumeEngine}
                      className="btn-primary"
                      style={{ flex: 1, padding: '8px', fontSize: '11px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px', cursor: 'pointer' }}
                    >
                      <Play size={12} /> Resume / Start Engine
                    </button>
                  )}
                </div>
              </div>

              {/* Log Board */}
              <div className="terminal-window" style={{ display: 'flex', flexDirection: 'column', flex: 1, maxHeight: '280px' }}>
                <div className="terminal-header">
                  <div style={{ display: 'flex', alignItems: 'center' }}>
                    <span className="terminal-dot red" />
                    <span className="terminal-dot yellow" />
                    <span className="terminal-dot green" />
                    <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px', marginLeft: '6px' }}>
                      <Activity size={13} style={{ color: '#8B5CF6' }} /> Indicator evaluation console logs
                    </span>
                  </div>
                  <span style={{ fontSize: '10px', color: 'var(--text-muted)', fontFamily: 'monospace' }}>bash - indicators.sh</span>
                </div>
                
                <div style={{ 
                  flex: 1, padding: '16px', 
                  fontFamily: 'monospace', fontSize: '11px', color: '#10B981', overflowY: 'auto', 
                  display: 'flex', flexDirection: 'column', gap: '4px'
                }}>
                  {strategyLogs.length === 0 ? (
                    <>
                      <p style={{ color: 'var(--text-muted)', margin: 0 }}>[SYSTEM BOOT] Stocker active indicator loops loaded.</p>
                      <p style={{ color: 'var(--text-muted)', margin: 0 }}>[WS] Connected and listening to live option tick streams...</p>
                      <p style={{ color: '#8B5CF6', margin: 0 }}>[ENGINE] Waiting for strategy activation to stream live rule evaluation ticks...</p>
                    </>
                  ) : (
                    strategyLogs.slice().reverse().map((log, index) => {
                      let color = '#F3F4F6';
                      if (log.message.includes('[TRIGGER]')) color = '#10B981';
                      else if (log.message.includes('[EVAL]')) color = '#F59E0B';
                      else if (log.message.includes('[TICK]')) color = '#6B7280';
                      
                      return (
                        <p key={index} style={{ color, margin: 0, lineHeight: '1.4' }}>
                          <span style={{ color: '#8B5CF6', marginRight: '6px' }}>[{log.timestamp}]</span>
                          <span style={{ color: '#6366F1', fontWeight: 600, marginRight: '4px' }}>[{log.strategy_name}]</span>
                          {log.message}
                        </p>
                      );
                    })
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ================= TAB: ALGORITHMS ================= */}
        {activeTab === 'builder' && (
          !isBuildingStrategy ? (
            <ActiveAlgorithms
              templates={strategies}
              instances={instances}
              onActivateClick={(strat) => setActiveStrategyToActivate(strat)}
              onToggleInstance={toggleInstance}
              onDeleteInstance={deleteInstance}
              onCreateNewClick={handleCreateNewStrategyClick}
              onDeleteTemplate={deleteStrategy}
              onSendTelegramStatus={sendTelegramStatus}
              strategyLogs={strategyLogs}
            />
          ) : (
            <CustomBuilder
              strategyName={strategyName}
              setStrategyName={setStrategyName}
              strategyType={strategyType}
              setStrategyType={setStrategyType}
              isPaperTrade={isPaperTrade}
              setIsPaperTrade={setIsPaperTrade}
              symbolTarget={symbolTarget}
              setSymbolTarget={setSymbolTarget}
              optType={optType}
              setOptType={setOptType}
              strikeSel={strikeSel}
              setStrikeSel={setStrikeSel}
              strikeOffset={strikeOffset}
              setStrikeOffset={setStrikeOffset}
              expiryType={expiryType}
              setExpiryType={setExpiryType}
              trailSlPct={trailSlPct}
              setTrailSlPct={setTrailSlPct}
              quantity={quantity}
              setQuantity={setQuantity}
              slPct={slPct}
              setSlPct={setSlPct}
              targetPct={targetPct}
              setTargetPct={setTargetPct}
              premiumMin={premiumMin}
              setPremiumMin={setPremiumMin}
              premiumMax={premiumMax}
              setPremiumMax={setPremiumMax}
              postBreakoutTf={postBreakoutTf}
              setPostBreakoutTf={setPostBreakoutTf}
              entryConditions={entryConditions}
              setEntryConditions={setEntryConditions}
              exitConditions={exitConditions}
              setExitConditions={setExitConditions}
              onDeploy={saveStrategy}
              onCancel={() => setIsBuildingStrategy(false)}
            />
          )
        )}

        {/* ================= TAB: LEDGER ================= */}
        {activeTab === 'ledger' && (
          <TradeLedger 
            tradeHistory={tradeHistory} 
            onClear={resetPaperRecords} 
            onSendTelegramLedger={sendTelegramLedger}
          />
        )}

        {/* ================= TAB: PORTFOLIO ================= */}
        {activeTab === 'backtest' && (
          <BacktestPage theme={theme} />
        )}
        {activeTab === 'portfolio' && (
          <PortfolioPage 
            onGoToSettings={() => handleSelectTab('settings')}
          />
        )}

        {/* ================= TAB: SETTINGS ================= */}
        {activeTab === 'settings' && (
          <SettingsPage 
            telegramToken={telegramToken}
            setTelegramToken={setTelegramToken}
            telegramChatId={telegramChatId}
            setTelegramChatId={setTelegramChatId}
            kiteApiKey={kiteApiKey}
            setKiteApiKey={setKiteApiKey}
            kiteApiSecret={kiteApiSecret}
            setKiteApiSecret={setKiteApiSecret}
            aliceClientId={aliceClientId}
            setAliceClientId={setAliceClientId}
            aliceApiKey={aliceApiKey}
            setAliceApiKey={setAliceApiKey}
            dhanClientId={dhanClientId}
            setDhanClientId={setDhanClientId}
            dhanAccessToken={dhanAccessToken}
            setDhanAccessToken={setDhanAccessToken}
            dhanTotpSecret={dhanTotpSecret}
            setDhanTotpSecret={setDhanTotpSecret}
            onSaveCredentials={saveCredentials}
            onTestTelegram={triggerTestTelegram}
            activeBroker={activeBroker}
            onSelectActiveBroker={handleSelectActiveBroker}
          />
        )}
      </main>
      </div>

      {activeStrategyToActivate && (
        <ActivationModal
          strategy={activeStrategyToActivate}
          onClose={() => setActiveStrategyToActivate(null)}
          onDeploy={deployInstance}
        />
      )}

    </div>
  );
}
