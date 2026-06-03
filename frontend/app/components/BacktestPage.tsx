'use client';
import React, { useState, useEffect, useRef } from 'react';
import { createChart, CandlestickSeries, createSeriesMarkers, UTCTimestamp, ColorType } from 'lightweight-charts';
import { Play, AlertCircle, RefreshCw, BarChart2, TrendingUp, TrendingDown, BookOpen, Activity, ChevronDown, ChevronUp } from 'lucide-react';
import { API_BASE } from '../config';

interface Strategy { id: string; name: string; }
interface JournalEntry { ts: string; action: string; price: number; qty?: number; pnl?: number; reason: string[]; note?: string; capital: number; }
interface VizBar { ts: string; open: number; high: number; low: number; close: number; volume: number; signal: string; trade_state: string; indicators: Record<string, any>; }
interface SimTrade { symbol: string; instrument_type: string; entry_time: string; exit_time: string; qty: number; entry_price: number; exit_price: number; pnl: number; pnl_pct: number; exit_reason: string; }
interface Summary { initial_capital: number; final_capital: number; net_pnl: number; total_return_pct: number; total_trades: number; profitable_trades: number; losing_trades: number; win_rate: number; max_drawdown_pct: number; }
interface BacktestResult { status: string; message?: string; meta?: Record<string, any>; summary: Summary; equity_curve: { date: string; balance: number }[]; visualization: VizBar[]; trades: SimTrade[]; journal: JournalEntry[]; logs?: string[]; }

function parseTimestampToUTC(tsStr: string): UTCTimestamp {
  const clean = tsStr.replace('T', ' ').replace(/\.\d+$/, '');
  const parts = clean.split(/[- :]/);
  if (parts.length < 5) {
    return Math.floor(new Date(tsStr).getTime() / 1000) as UTCTimestamp;
  }
  const year = parseInt(parts[0], 10);
  const month = parseInt(parts[1], 10) - 1;
  const day = parseInt(parts[2], 10);
  const hour = parseInt(parts[3], 10);
  const minute = parseInt(parts[4], 10);
  const second = parseInt(parts[5] || '0', 10);
  return Math.floor(Date.UTC(year, month, day, hour, minute, second) / 1000) as UTCTimestamp;
}

function LightweightCandleChart({ visualization }: { visualization: VizBar[] }) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    const container = chartContainerRef.current;
    const chart = createChart(container, {
      width: container.clientWidth,
      height: 360,
      layout: {
        background: { type: ColorType.Solid, color: 'rgba(0, 0, 0, 0.4)' },
        textColor: '#d1d4dc',
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.05)' },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      },
    });

    chartRef.current = chart;

    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10B981',
      downColor: '#EF4444',
      borderVisible: false,
      wickUpColor: '#10B981',
      wickDownColor: '#EF4444',
    });

    const data = visualization.map(b => {
      const epoch = parseTimestampToUTC(b.ts);
      return {
        time: epoch,
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      };
    });

    candlestickSeries.setData(data);

    // Add signal markers
    const markers = visualization
      .map(b => {
        if (b.signal === 'BUY') {
          const epoch = parseTimestampToUTC(b.ts);
          return {
            time: epoch,
            position: 'belowBar' as const,
            color: '#10B981',
            shape: 'arrowUp' as const,
            text: 'BUY',
          };
        }
        if (b.signal === 'SELL') {
          const epoch = parseTimestampToUTC(b.ts);
          return {
            time: epoch,
            position: 'aboveBar' as const,
            color: '#EF4444',
            shape: 'arrowDown' as const,
            text: 'SELL',
          };
        }
        return null;
      })
      .filter((m): m is Exclude<typeof m, null> => m !== null);

    createSeriesMarkers(candlestickSeries, markers);
    chart.timeScale().fitContent();

    const handleResize = () => {
      chart.applyOptions({ width: container.clientWidth });
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
      chartRef.current = null;
    };
  }, [visualization]);

  const handleDownload = () => {
    if (!chartRef.current) return;
    const canvas = chartRef.current.takeScreenshot();
    const dataUrl = canvas.toDataURL('image/jpeg');
    const link = document.createElement('a');
    link.href = dataUrl;
    link.download = `spot_chart_${Date.now()}.jpeg`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div style={{ position: 'relative', width: '100%', height: '360px' }}>
      <div ref={chartContainerRef} style={{ width: '100%', height: '100%' }} />
      <button
        onClick={handleDownload}
        title="Share Chart as JPEG"
        style={{
          position: 'absolute',
          top: '10px',
          right: '10px',
          zIndex: 10,
          background: 'rgba(255, 255, 255, 0.08)',
          border: '1px solid rgba(255, 255, 255, 0.15)',
          borderRadius: '6px',
          padding: '6px 10px',
          fontSize: '11px',
          color: '#fff',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          backdropFilter: 'blur(4px)',
          transition: 'all 0.2s',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = 'rgba(255, 255, 255, 0.15)';
          e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.25)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = 'rgba(255, 255, 255, 0.08)';
          e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.15)';
        }}
      >
        📷 Share JPEG
      </button>
    </div>
  );
}

function LightweightOptionChart({ visualization, type }: { visualization: VizBar[], type: 'CE' | 'PE' }) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    const container = chartContainerRef.current;
    const chart = createChart(container, {
      width: container.clientWidth,
      height: 260,
      layout: {
        background: { type: ColorType.Solid, color: 'rgba(0, 0, 0, 0.4)' },
        textColor: '#d1d4dc',
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.05)' },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      },
    });

    chartRef.current = chart;

    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: type === 'CE' ? '#60A5FA' : '#FB923C', // Gorgeous Blue for CE, Orange for PE!
      downColor: '#EF4444',
      borderVisible: false,
      wickUpColor: type === 'CE' ? '#60A5FA' : '#FB923C',
      wickDownColor: '#EF4444',
    });

    const data = visualization.map((b, idx) => {
      const epoch = parseTimestampToUTC(b.ts);

      const open = type === 'CE'
        ? (b.indicators?.ce_open ?? b.indicators?.ce_premium ?? 10)
        : (b.indicators?.pe_open ?? b.indicators?.pe_premium ?? 10);
      const high = type === 'CE'
        ? (b.indicators?.ce_high ?? b.indicators?.ce_premium ?? 10)
        : (b.indicators?.pe_high ?? b.indicators?.pe_premium ?? 10);
      const low = type === 'CE'
        ? (b.indicators?.ce_low ?? b.indicators?.ce_premium ?? 10)
        : (b.indicators?.pe_low ?? b.indicators?.pe_premium ?? 10);
      const close = type === 'CE'
        ? (b.indicators?.ce_close ?? b.indicators?.ce_premium ?? 10)
        : (b.indicators?.pe_close ?? b.indicators?.pe_premium ?? 10);

      return {
        time: epoch,
        open,
        high,
        low,
        close,
      };
    });

    candlestickSeries.setData(data);

    // Add option specific signal markers
    const markers = visualization
      .map(b => {
        const optionType = b.indicators?.selected_option_type;
        if (optionType !== type) return null;

        if (b.signal === 'BUY') {
          const epoch = parseTimestampToUTC(b.ts);
          return {
            time: epoch,
            position: 'belowBar' as const,
            color: '#10B981',
            shape: 'arrowUp' as const,
            text: 'BUY',
          };
        }
        if (b.signal === 'SELL') {
          const epoch = parseTimestampToUTC(b.ts);
          return {
            time: epoch,
            position: 'aboveBar' as const,
            color: '#EF4444',
            shape: 'arrowDown' as const,
            text: 'SELL',
          };
        }
        return null;
      })
      .filter((m): m is Exclude<typeof m, null> => m !== null);

    createSeriesMarkers(candlestickSeries, markers);
    chart.timeScale().fitContent();

    const handleResize = () => {
      chart.applyOptions({ width: container.clientWidth });
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
      chartRef.current = null;
    };
  }, [visualization, type]);

  const handleDownload = () => {
    if (!chartRef.current) return;
    const canvas = chartRef.current.takeScreenshot();
    const dataUrl = canvas.toDataURL('image/jpeg');
    const link = document.createElement('a');
    link.href = dataUrl;
    link.download = `option_chart_${type}_${Date.now()}.jpeg`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div style={{ position: 'relative', width: '100%', height: '260px' }}>
      <div ref={chartContainerRef} style={{ width: '100%', height: '100%' }} />
      <button
        onClick={handleDownload}
        title="Share Option Chart as JPEG"
        style={{
          position: 'absolute',
          top: '10px',
          right: '10px',
          zIndex: 10,
          background: 'rgba(255, 255, 255, 0.08)',
          border: '1px solid rgba(255, 255, 255, 0.15)',
          borderRadius: '6px',
          padding: '6px 10px',
          fontSize: '11px',
          color: '#fff',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          backdropFilter: 'blur(4px)',
          transition: 'all 0.2s',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = 'rgba(255, 255, 255, 0.15)';
          e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.25)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = 'rgba(255, 255, 255, 0.08)';
          e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.15)';
        }}
      >
        📷 Share JPEG
      </button>
    </div>
  );
}

const SYMBOLS = ['NSE:NIFTY 50', 'NSE:NIFTY BANK', 'NSE:RELIANCE', 'NSE:TCS', 'NSE:INFY', 'NSE:HDFCBANK', 'NSE:ICICIBANK', 'NSE:SBIN', 'NSE:WIPRO', 'NSE:BAJFINANCE', 'NSE:TATAMOTORS'];

const getLotSize = (symbol: string): number => {
  const s = symbol.toUpperCase();
  if (s.includes('BANKNIFTY') || s.includes('NIFTY BANK') || s.includes('BANK')) return 15;
  if (s.includes('FINNIFTY') || s.includes('FIN NIFTY')) return 40;
  if (s.includes('SENSEX')) return 10;
  if (s.includes('NIFTY')) return 50;
  return 1;
};

export default function BacktestPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [stratId, setStratId] = useState('');
  const [symbol, setSymbol] = useState('NSE:NIFTY 50');
  const [instrType, setInstrType] = useState('STOCK');
  const [strikePrice, setStrikePrice] = useState('');
  const [expiryDate, setExpiryDate] = useState('');
  const [dateMode, setDateMode] = useState<'last' | 'range' | 'single'>('last');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [singleDay, setSingleDay] = useState('');
  const [interval, setInterval] = useState('5minute');
  const [days, setDays] = useState(30);
  const [capital, setCapital] = useState(100000);
  const [lots, setLots] = useState(1);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<'chart' | 'viz' | 'trades' | 'journal' | 'logs'>('chart');
  const [expandedJournal, setExpandedJournal] = useState<number | null>(null);
  const [optionChartType, setOptionChartType] = useState<'CE' | 'PE'>('CE');

  const [telegramSending, setTelegramSending] = useState(false);
  const [telegramSent, setTelegramSent] = useState(false);
  const [telegramError, setTelegramError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/strategies`).then(r => r.json()).then(d => { setStrategies(d); if (d.length > 0) setStratId(d[0].id); }).catch(() => { });
  }, []);

  const run = async () => {
    if (!stratId) { setError('No strategy selected.'); return; }
    setRunning(true); setError(null); setResult(null);
    setTelegramSent(false); setTelegramError(null);
    try {
      const body: any = { strategy_id: stratId, symbol, instrument_type: instrType, days, initial_capital: capital, lots };
      if (instrType !== 'STOCK') { body.strike_price = parseFloat(strikePrice) || undefined; body.expiry_date = expiryDate || undefined; }
      if (dateMode === 'range' && fromDate && toDate) { body.from_date = fromDate; body.to_date = toDate; }
      if (dateMode === 'single' && singleDay) { body.single_day = singleDay; body.interval = interval; }
      const res = await fetch(`${API_BASE}/api/backtest`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const data: BacktestResult = await res.json();
      if (data.status === 'ERROR') setError(data.message || 'Simulation failed.');
      else { setResult(data); setActiveSection(data.meta?.is_intraday ? 'chart' : 'viz'); }
    } catch { setError('Could not reach backend server.'); }
    finally { setRunning(false); }
  };

  const sendToTelegram = async () => {
    if (!result || !result.summary) return;
    setTelegramSending(true);
    setTelegramSent(false);
    setTelegramError(null);
    try {
      const activeStrategy = strategies.find(s => s.id === stratId);
      const strategyName = activeStrategy ? activeStrategy.name : 'Unknown Strategy';
      const body = {
        strategy_name: strategyName,
        symbol: symbol,
        from_date: result.meta?.from ? result.meta.from.substring(0, 10) : (fromDate || 'N/A'),
        to_date: result.meta?.to ? result.meta.to.substring(0, 10) : (toDate || 'N/A'),
        initial_capital: result.summary.initial_capital,
        total_trades: result.summary.total_trades,
        win_rate: result.summary.win_rate,
        profitable_trades: result.summary.profitable_trades,
        losing_trades: result.summary.losing_trades,
        net_pnl: result.summary.net_pnl,
        final_capital: result.summary.final_capital,
        trades: result.trades.map(t => ({
          symbol: t.symbol,
          option_type: t.instrument_type,
          entry_time: t.entry_time,
          exit_time: t.exit_time,
          quantity: t.qty,
          entry_price: t.entry_price,
          exit_price: t.exit_price,
          pnl: t.pnl,
          exit_reason: t.exit_reason
        }))
      };

      const res = await fetch(`${API_BASE}/api/backtest/telegram-report`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const data = await res.json();
      if (data.status === 'SUCCESS') {
        setTelegramSent(true);
        setTimeout(() => setTelegramSent(false), 3000);
      } else {
        setTelegramError(data.message || 'Failed to dispatch report.');
      }
    } catch {
      setTelegramError('Could not reach backend server.');
    } finally {
      setTelegramSending(false);
    }
  };

  const pnlColor = (v: number) => v >= 0 ? '#10B981' : '#EF4444';
  const signalColor = (s: string) => s === 'BUY' ? '#10B981' : s === 'SELL' ? '#EF4444' : 'rgba(255,255,255,0.15)';

  return (
    <div style={{ margin: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>

      {/* ── Header ── */}
      <div className="glass-panel" style={{ padding: '24px' }}>
        <h2 style={{ fontSize: '20px', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
          <BarChart2 size={22} style={{ color: 'var(--accent-yellow)' }} /> Historical Backtest Simulator
        </h2>
        <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Replay real broker data through your strategy rules. No mock data — Zerodha Kite session required.</p>
      </div>

      {/* ── Config ── */}
      <div className="glass-panel" style={{ padding: '24px', display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(200px,1fr))', gap: '16px' }}>

        {/* Strategy */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <label style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '.05em' }}>Strategy</label>
          <select value={stratId} onChange={e => setStratId(e.target.value)} className="input-glass" style={{ padding: '10px', fontSize: '13px', background: 'rgba(0,0,0,0.3)' }}>
            {strategies.length === 0 ? <option value="">No strategies</option> : strategies.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>

        {/* Symbol */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <label style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '.05em' }}>Symbol</label>
          <select value={symbol} onChange={e => setSymbol(e.target.value)} className="input-glass" style={{ padding: '10px', fontSize: '13px', background: 'rgba(0,0,0,0.3)' }}>
            {SYMBOLS.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>

        {/* Instrument Type */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <label style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '.05em' }}>Instrument</label>
          <select value={instrType} onChange={e => setInstrType(e.target.value)} className="input-glass" style={{ padding: '10px', fontSize: '13px', background: 'rgba(0,0,0,0.3)' }}>
            <option value="STOCK">Stock / Index (Spot)</option>
            <option value="CE">Call Option (CE)</option>
            <option value="PE">Put Option (PE)</option>
          </select>
        </div>

        {/* Strike + Expiry (options only) */}
        {instrType !== 'STOCK' && <>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '.05em' }}>Strike Price</label>
            <input type="number" value={strikePrice} onChange={e => setStrikePrice(e.target.value)} placeholder="e.g. 22000" className="input-glass" style={{ padding: '10px', fontSize: '13px' }} />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '.05em' }}>Expiry Date</label>
            <input type="date" value={expiryDate} onChange={e => setExpiryDate(e.target.value)} className="input-glass" style={{ padding: '10px', fontSize: '13px' }} />
          </div>
        </>}

        {/* ── Date Mode ── */}
        <div style={{ gridColumn: 'span 2', display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <label style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '.05em' }}>Date Mode</label>

          {/* Mode selector pills */}
          <div style={{ display: 'flex', gap: '6px' }}>
            {[
              { id: 'last', label: '📅 Last N Days' },
              { id: 'range', label: '📆 Date Range' },
              { id: 'single', label: '🕯️ Single Day' },
            ].map(m => (
              <button key={m.id} onClick={() => setDateMode(m.id as any)}
                style={{
                  padding: '8px 16px', borderRadius: '20px', fontSize: '12px', fontWeight: 600, border: 'none', cursor: 'pointer',
                  background: dateMode === m.id ? 'var(--accent-yellow)' : 'rgba(255,255,255,0.07)',
                  color: dateMode === m.id ? '#000' : 'var(--text-secondary)',
                  transition: 'all .2s ease',
                }}>
                {m.label}
              </button>
            ))}
          </div>

          {/* Last N Days — quick chip grid */}
          {dateMode === 'last' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                {[
                  { v: 5, l: '5D' }, { v: 10, l: '10D' }, { v: 15, l: '15D' },
                  { v: 20, l: '20D' }, { v: 30, l: '1M' }, { v: 60, l: '2M' },
                  { v: 90, l: '3M' }, { v: 180, l: '6M' }, { v: 365, l: '1Y' },
                ].map(d => (
                  <button key={d.v} onClick={() => setDays(d.v)}
                    style={{
                      padding: '6px 14px', borderRadius: '16px', fontSize: '12px', fontWeight: 600, border: 'none', cursor: 'pointer',
                      background: days === d.v ? '#6366F1' : 'rgba(255,255,255,0.06)',
                      color: days === d.v ? '#fff' : 'var(--text-secondary)',
                      transition: 'all .15s ease',
                    }}>
                    {d.l}
                  </button>
                ))}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', padding: '6px 10px', background: 'rgba(255,255,255,0.03)', borderRadius: '6px' }}>
                📌 Fetching last <strong style={{ color: '#fff' }}>{days} calendar days</strong> of <strong style={{ color: '#fff' }}>daily</strong> candles up to today
              </div>
            </div>
          )}

          {/* Date Range — styled from/to pickers */}
          {dateMode === 'range' && (
            <div style={{ display: 'flex', gap: '14px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
              {[
                { label: 'From Date', val: fromDate, set: setFromDate },
                { label: 'To Date', val: toDate, set: setToDate },
              ].map(field => (
                <div key={field.label} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <label style={{ fontSize: '10px', color: 'var(--text-muted)', fontWeight: 600 }}>{field.label}</label>
                  <div style={{ position: 'relative' }}>
                    <input type="date" value={field.val} onChange={e => field.set(e.target.value)}
                      style={{
                        padding: '9px 36px 9px 12px', borderRadius: '8px', fontSize: '13px', fontWeight: 500,
                        background: 'rgba(99,102,241,0.08)', border: '1px solid rgba(99,102,241,0.3)',
                        color: '#fff', cursor: 'pointer', outline: 'none',
                        appearance: 'none', WebkitAppearance: 'none',
                      }}
                    />
                    <span style={{ position: 'absolute', right: '10px', top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none', fontSize: '14px' }}>📅</span>
                  </div>
                </div>
              ))}
              {fromDate && toDate && (
                <div style={{ padding: '8px 12px', borderRadius: '8px', background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.2)', fontSize: '12px', color: '#818CF8' }}>
                  {Math.round((new Date(toDate).getTime() - new Date(fromDate).getTime()) / 86400000)} calendar days · daily candles
                </div>
              )}
            </div>
          )}

          {/* Single Day — date picker + interval grid */}
          {dateMode === 'single' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', gap: '14px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <label style={{ fontSize: '10px', color: 'var(--text-muted)', fontWeight: 600 }}>Select Trading Date</label>
                  <div style={{ position: 'relative' }}>
                    <input type="date" value={singleDay} onChange={e => setSingleDay(e.target.value)}
                      max={new Date().toISOString().split('T')[0]}
                      style={{
                        padding: '9px 36px 9px 12px', borderRadius: '8px', fontSize: '13px', fontWeight: 500,
                        background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.35)',
                        color: '#fff', cursor: 'pointer', outline: 'none',
                        appearance: 'none', WebkitAppearance: 'none', minWidth: '170px',
                      }}
                    />
                    <span style={{ position: 'absolute', right: '10px', top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none', fontSize: '14px' }}>🗓️</span>
                  </div>
                </div>

                {singleDay && (
                  <div style={{ padding: '8px 14px', borderRadius: '8px', background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)', fontSize: '12px', color: '#F59E0B', fontWeight: 600 }}>
                    {new Date(singleDay).toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
                  </div>
                )}
              </div>

              {/* Interval chip grid */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <label style={{ fontSize: '10px', color: 'var(--text-muted)', fontWeight: 600 }}>Candle Interval</label>
                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                  {[
                    { v: 'minute', l: '1m' },
                    { v: '3minute', l: '3m' },
                    { v: '5minute', l: '5m' },
                    { v: '10minute', l: '10m' },
                    { v: '15minute', l: '15m' },
                    { v: '30minute', l: '30m' },
                    { v: '60minute', l: '1h' },
                  ].map(iv => (
                    <button key={iv.v} onClick={() => setInterval(iv.v)}
                      style={{
                        padding: '6px 14px', borderRadius: '16px', fontSize: '12px', fontWeight: 700, border: 'none', cursor: 'pointer',
                        background: interval === iv.v ? '#F59E0B' : 'rgba(255,255,255,0.06)',
                        color: interval === iv.v ? '#000' : 'var(--text-secondary)',
                        transition: 'all .15s ease',
                      }}>
                      {iv.l}
                    </button>
                  ))}
                </div>
              </div>

              {singleDay && (
                <div style={{ padding: '10px 14px', borderRadius: '8px', background: 'rgba(245,158,11,0.05)', border: '1px solid rgba(245,158,11,0.15)', fontSize: '11px', color: 'var(--text-secondary)', lineHeight: '1.7' }}>
                  <strong style={{ color: '#F59E0B' }}>📊 Intraday Simulation</strong><br />
                  Fetching <strong style={{ color: '#fff' }}>{interval}</strong> candles from <strong style={{ color: '#fff' }}>09:15</strong> to <strong style={{ color: '#fff' }}>15:30 IST</strong> on <strong style={{ color: '#fff' }}>{singleDay}</strong> via Kite v3 historical API.
                  Results will display a full intraday candlestick chart with signal markers.
                </div>
              )}
            </div>
          )}
        </div>

        {/* Capital */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <label style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '.05em' }}>Initial Capital (₹)</label>
          <input type="number" value={capital} onChange={e => setCapital(Number(e.target.value))} className="input-glass" style={{ padding: '10px', fontSize: '13px' }} />
        </div>

        {/* Lots */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <label style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '.05em' }}>Lots to Trade</label>
          <input type="number" min={1} value={lots} onChange={e => setLots(Math.max(1, Number(e.target.value)))} className="input-glass" style={{ padding: '10px', fontSize: '13px' }} />
        </div>

        {/* Run button */}
        <div style={{ display: 'flex', alignItems: 'flex-end' }}>
          <button onClick={run} disabled={running || strategies.length === 0} className="btn-primary"
            style={{ padding: '12px 28px', borderRadius: '8px', display: 'flex', alignItems: 'center', gap: '8px', background: 'var(--accent-yellow)', color: '#000', fontWeight: 700, cursor: running ? 'not-allowed' : 'pointer', width: '100%', justifyContent: 'center' }}>
            {running ? <><RefreshCw size={15} className="animate-spin" /> Simulating...</> : <><Play size={15} /> Run Backtest</>}
          </button>
        </div>
      </div>

      {/* ── Error ── */}
      {error && (
        <div style={{ display: 'flex', gap: '10px', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', borderRadius: '8px', padding: '14px 18px', color: '#EF4444', fontSize: '13px' }}>
          <AlertCircle size={18} style={{ flexShrink: 0 }} /><span>{error}</span>
        </div>
      )}

      {/* ── Loading ── */}
      {running && (
        <div className="glass-panel animate-pulse" style={{ padding: '60px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '16px' }}>
          <BarChart2 size={48} style={{ color: 'var(--accent-yellow)' }} className="animate-spin" />
          <span style={{ fontSize: '14px', color: 'var(--text-secondary)', fontWeight: 500 }}>Replaying strategy over real broker candles...</span>
        </div>
      )}

      {/* ── Results ── */}
      {result && result.summary && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }} className="animate-slide-in">

          {/* Meta info bar */}
          {result.meta && (
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '16px', flexWrap: 'wrap', padding: '12px 18px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.06)', fontSize: '12px', color: 'var(--text-secondary)' }}>
              <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                <span>📌 <strong>{result.meta.symbol}</strong> · {result.meta.instrument_type}</span>
                <span>📅 {result.meta.from} → {result.meta.to}</span>
                <span>🕯️ {result.meta.candles_used} candles</span>
              </div>
              <div>
                <button onClick={sendToTelegram} disabled={telegramSending}
                  style={{
                    padding: '6px 14px', borderRadius: '16px', fontSize: '11px', fontWeight: 700, cursor: telegramSending ? 'not-allowed' : 'pointer',
                    background: telegramSent ? '#10B981' : 'rgba(99,102,241,0.15)',
                    color: telegramSent ? '#fff' : '#818CF8',
                    border: telegramSent ? '1px solid #10B981' : '1px solid rgba(99,102,241,0.3)',
                    transition: 'all .15s ease',
                    display: 'flex', alignItems: 'center', gap: '6px'
                  }}>
                  {telegramSending ? '📤 Dispatching...' : telegramSent ? '✅ Dispatched to Telegram!' : '✈️ Send Report to Telegram'}
                </button>
              </div>
            </div>
          )}

          {telegramError && (
            <div style={{ display: 'flex', gap: '10px', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', borderRadius: '8px', padding: '10px 14px', color: '#EF4444', fontSize: '12px' }}>
              <AlertCircle size={15} style={{ flexShrink: 0 }} /><span>{telegramError}</span>
            </div>
          )}

          {/* KPI cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(180px,1fr))', gap: '14px' }}>
            {[
              { label: 'Net P&L', val: `${result.summary.net_pnl >= 0 ? '+' : ''}₹${result.summary.net_pnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`, sub: `${result.summary.total_return_pct}% return`, color: pnlColor(result.summary.net_pnl), border: true },
              { label: 'Final Capital', val: `₹${result.summary.final_capital.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`, sub: `Started ₹${result.summary.initial_capital.toLocaleString('en-IN')}`, color: '#fff' },
              { label: 'Win Rate', val: `${result.summary.win_rate}%`, sub: `${result.summary.profitable_trades}W / ${result.summary.losing_trades}L`, color: '#6366F1' },
              { label: 'Total Trades', val: `${result.summary.total_trades}`, sub: `Max drawdown ${result.summary.max_drawdown_pct}%`, color: '#F59E0B' },
            ].map(k => (
              <div key={k.label} className="glass-card" style={{ padding: '18px', borderLeft: k.border ? `3px solid ${k.color}` : undefined }}>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{k.label}</span>
                <p style={{ fontSize: '22px', fontWeight: 800, color: k.color, margin: '4px 0 2px' }}>{k.val}</p>
                <span style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>{k.sub}</span>
              </div>
            ))}
          </div>

          {/* Equity curve */}
          <div className="glass-card" style={{ padding: '20px' }}>
            <h3 style={{ fontSize: '13px', fontWeight: 700, marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <TrendingUp size={15} style={{ color: 'var(--accent-yellow)' }} /> Capital Equity Curve
            </h3>
            {(() => {
              const pts = result.equity_curve.filter((_, i) => i % Math.max(1, Math.floor(result.equity_curve.length / 60)) === 0);
              if (pts.length === 0) return <p style={{ color: 'var(--text-muted)', fontSize: '12px' }}>No equity data</p>;
              const balances = pts.map(p => p.balance);
              const minBal = Math.min(...balances);
              const maxBal = Math.max(...balances);
              const range = maxBal - minBal || 1; // avoid division by zero
              const initCap = result.summary.initial_capital;
              return (
                <>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px', fontSize: '10px', color: 'var(--text-muted)' }}>
                    <span>₹{maxBal.toLocaleString('en-IN', { minimumFractionDigits: 0 })}</span>
                    <span style={{ color: pts[pts.length - 1].balance >= initCap ? '#10B981' : '#EF4444', fontWeight: 700 }}>
                      {pts[pts.length - 1].balance >= initCap ? '▲' : '▼'} ₹{(pts[pts.length - 1].balance - initCap).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                  <div style={{ position: 'relative', height: '140px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                    {/* Zero line (initial capital) */}
                    {minBal < initCap && maxBal > initCap && (
                      <div style={{
                        position: 'absolute', left: 0, right: 0, bottom: `${((initCap - minBal) / range) * 100}%`,
                        borderTop: '1px dashed rgba(255,255,255,0.15)', zIndex: 1
                      }}>
                        <span style={{ position: 'absolute', right: 0, top: '-14px', fontSize: '9px', color: 'var(--text-muted)' }}>Initial</span>
                      </div>
                    )}
                    <svg width="100%" height="100%" preserveAspectRatio="none" viewBox={`0 0 ${pts.length} 100`}>
                      <defs>
                        <linearGradient id="eqGradUp" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#10B981" stopOpacity="0.4" />
                          <stop offset="100%" stopColor="#10B981" stopOpacity="0.05" />
                        </linearGradient>
                        <linearGradient id="eqGradDn" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#EF4444" stopOpacity="0.4" />
                          <stop offset="100%" stopColor="#EF4444" stopOpacity="0.05" />
                        </linearGradient>
                      </defs>
                      {/* Area fill */}
                      <path
                        d={`M0,${100 - ((pts[0].balance - minBal) / range) * 100} ${pts.map((p, i) => `L${i},${100 - ((p.balance - minBal) / range) * 100}`).join(' ')} L${pts.length - 1},100 L0,100 Z`}
                        fill={pts[pts.length - 1].balance >= initCap ? 'url(#eqGradUp)' : 'url(#eqGradDn)'}
                      />
                      {/* Line */}
                      <polyline
                        points={pts.map((p, i) => `${i},${100 - ((p.balance - minBal) / range) * 100}`).join(' ')}
                        fill="none"
                        stroke={pts[pts.length - 1].balance >= initCap ? '#10B981' : '#EF4444'}
                        strokeWidth="1.5"
                        vectorEffect="non-scaling-stroke"
                      />
                    </svg>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '6px', fontSize: '10px', color: 'var(--text-muted)' }}>
                    <span>{pts[0]?.date?.split(' ')[0] || ''}</span>
                    <span>₹{minBal.toLocaleString('en-IN', { minimumFractionDigits: 0 })}</span>
                    <span>{pts[pts.length - 1]?.date?.split(' ')[0] || ''}</span>
                  </div>
                </>
              );
            })()}
          </div>

          {/* Section tabs */}
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {result.meta?.is_intraday && (
              <button onClick={() => setActiveSection('chart')} className={activeSection === 'chart' ? 'btn-primary' : 'btn-glass'}
                style={{ padding: '8px 18px', borderRadius: '6px', fontSize: '12px', fontWeight: 600 }}>
                📈 Intraday Chart
              </button>
            )}
            {(['viz', 'trades', 'journal'] as const).map(s => (
              <button key={s} onClick={() => setActiveSection(s)} className={activeSection === s ? 'btn-primary' : 'btn-glass'}
                style={{ padding: '8px 18px', borderRadius: '6px', fontSize: '12px', fontWeight: 600 }}>
                {s === 'viz' ? '📊 Signal Overlay' : s === 'trades' ? '💼 Trade Ledger' : '📓 Trade Journal'}
              </button>
            ))}
            {result.logs && (
              <button onClick={() => setActiveSection('logs')} className={activeSection === 'logs' ? 'btn-primary' : 'btn-glass'}
                style={{ padding: '8px 18px', borderRadius: '6px', fontSize: '12px', fontWeight: 600 }}>
                💻 System Logs
              </button>
            )}
          </div>

          {/* Intraday Candlestick Chart */}
          {activeSection === 'chart' && result.meta?.is_intraday && (
            <div className="glass-card" style={{ padding: '20px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px', marginBottom: '14px' }}>
                <div>
                  <h3 style={{ fontSize: '13px', fontWeight: 700, marginBottom: '4px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    📈 {result.meta.symbol} — {result.meta.interval} candles on {result.meta.from?.substring(0, 10)}
                  </h3>
                  <p style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    {result.visualization.length} bars · Green body = bullish · Red body = bearish · ▲ BUY / ▼ SELL markers indicate signal triggers
                  </p>
                </div>

                {/* Strike / Option Chain Resolution badging */}
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  {result.meta?.selected_ce_strike && (
                    <div style={{ display: 'flex', flexDirection: 'column', background: 'rgba(96, 165, 250, 0.08)', border: '1px solid rgba(96, 165, 250, 0.2)', padding: '5px 12px', borderRadius: '6px' }}>
                      <span style={{ fontSize: '9px', color: 'rgba(96, 165, 250, 0.7)', fontWeight: 600, textTransform: 'uppercase' }}>Selected CE Strike</span>
                      <span style={{ fontSize: '12px', color: '#60A5FA', fontWeight: 800 }}>{result.meta.symbol.split(':')[1] || 'NIFTY'} CE {result.meta.selected_ce_strike}</span>
                    </div>
                  )}
                  {result.meta?.selected_pe_strike && (
                    <div style={{ display: 'flex', flexDirection: 'column', background: 'rgba(251, 146, 60, 0.08)', border: '1px solid rgba(251, 146, 60, 0.2)', padding: '5px 12px', borderRadius: '6px' }}>
                      <span style={{ fontSize: '9px', color: 'rgba(251, 146, 60, 0.7)', fontWeight: 600, textTransform: 'uppercase' }}>Selected PE Strike</span>
                      <span style={{ fontSize: '12px', color: '#FB923C', fontWeight: 800 }}>{result.meta.symbol.split(':')[1] || 'NIFTY'} PE {result.meta.selected_pe_strike}</span>
                    </div>
                  )}
                  {result.meta?.expiry_date && (
                    <div style={{ display: 'flex', flexDirection: 'column', background: 'rgba(168, 85, 247, 0.08)', border: '1px solid rgba(168, 85, 247, 0.2)', padding: '5px 12px', borderRadius: '6px' }}>
                      <span style={{ fontSize: '9px', color: 'rgba(168, 85, 247, 0.7)', fontWeight: 600, textTransform: 'uppercase' }}>Option Expiry</span>
                      <span style={{ fontSize: '12px', color: '#C084FC', fontWeight: 800 }}>{result.meta.expiry_date}</span>
                    </div>
                  )}
                </div>
              </div>
              {/* Candlestick chart using tradingview lightweight-charts */}
              <div style={{ background: 'rgba(0,0,0,0.2)', borderRadius: '8px', overflow: 'hidden', border: '1px solid rgba(255,255,255,0.05)', marginBottom: '16px' }}>
                <LightweightCandleChart visualization={result.visualization} />
              </div>
              <div style={{ display: 'flex', gap: '16px', marginTop: '8px', fontSize: '11px' }}>
                <span><span style={{ color: '#10B981', fontWeight: 700 }}>▲ BUY</span> Entry triggered</span>
                <span><span style={{ color: '#EF4444', fontWeight: 700 }}>▼ SELL</span> Exit triggered</span>
                <span style={{ color: 'rgba(16,185,129,0.7)' }}>█ Bullish</span>
                <span style={{ color: 'rgba(239,68,68,0.7)' }}>█ Bearish</span>
              </div>

              {/* Option Chain Candlestick Chart */}
              {result.visualization[0]?.indicators?.ce_premium !== undefined && (
                <div style={{ marginTop: '24px', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '20px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                    <div>
                      <h4 style={{ fontSize: '13px', fontWeight: 700, marginBottom: '2px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Activity size={15} style={{ color: '#6366F1' }} /> ATM Option Premium Candlesticks
                      </h4>
                      <p style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                        TradingView candlestick series mapping simulated OHLC values for option premiums.
                      </p>
                    </div>

                    {/* Toggle Buttons */}
                    <div style={{ display: 'flex', gap: '6px', background: 'rgba(255,255,255,0.03)', padding: '2px', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.06)' }}>
                      <button
                        onClick={() => setOptionChartType('CE')}
                        style={{
                          padding: '6px 14px',
                          fontSize: '11px',
                          fontWeight: 700,
                          borderRadius: '4px',
                          border: 'none',
                          cursor: 'pointer',
                          background: optionChartType === 'CE' ? 'rgba(96, 165, 250, 0.15)' : 'transparent',
                          color: optionChartType === 'CE' ? '#60A5FA' : 'var(--text-muted)',
                          transition: 'all 0.2s',
                        }}
                      >
                        🔵 Call Option (CE)
                      </button>
                      <button
                        onClick={() => setOptionChartType('PE')}
                        style={{
                          padding: '6px 14px',
                          fontSize: '11px',
                          fontWeight: 700,
                          borderRadius: '4px',
                          border: 'none',
                          cursor: 'pointer',
                          background: optionChartType === 'PE' ? 'rgba(251, 146, 60, 0.15)' : 'transparent',
                          color: optionChartType === 'PE' ? '#FB923C' : 'var(--text-muted)',
                          transition: 'all 0.2s',
                        }}
                      >
                        🟠 Put Option (PE)
                      </button>
                    </div>
                  </div>

                  <div style={{ background: 'rgba(0,0,0,0.2)', borderRadius: '8px', overflow: 'hidden', border: '1px solid rgba(255,255,255,0.05)' }}>
                    <LightweightOptionChart visualization={result.visualization} type={optionChartType} />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Visualization timeline */}
          {activeSection === 'viz' && (
            <div className="glass-card" style={{ padding: '18px' }}>
              <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '12px' }}>Every bar annotated. Green = BUY entry, Red = SELL exit, Grey = holding/observing.</p>
              <div style={{ overflowX: 'auto' }}>
                <div style={{ display: 'flex', gap: '4px', alignItems: 'flex-end', height: '160px', minWidth: `${result.visualization.length * 14}px`, paddingBottom: '8px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                  {result.visualization.map((bar, i) => {
                    const range = bar.high - bar.low;
                    const bodyH = Math.abs(bar.close - bar.open);
                    const allRange = Math.max(...result.visualization.map(b => b.high)) - Math.min(...result.visualization.map(b => b.low));
                    const scale = allRange > 0 ? 140 / allRange : 1;
                    const barH = Math.max(2, bodyH * scale);
                    const bullish = bar.close >= bar.open;
                    const color = bar.signal === 'BUY' ? '#10B981' : bar.signal === 'SELL' ? '#EF4444' : (bullish ? 'rgba(16,185,129,0.4)' : 'rgba(239,68,68,0.35)');
                    return (
                      <div key={i} style={{ flex: '0 0 12px', display: 'flex', flexDirection: 'column', alignItems: 'center', cursor: 'pointer' }} title={`${bar.ts}\nO:${bar.open} H:${bar.high} L:${bar.low} C:${bar.close}\nSignal: ${bar.signal}`}>
                        {bar.signal !== 'HOLD' && (
                          <span style={{ fontSize: '7px', fontWeight: 900, color: signalColor(bar.signal), marginBottom: '2px' }}>{bar.signal === 'BUY' ? '▲' : '▼'}</span>
                        )}
                        <div style={{ width: '8px', height: `${Math.max(4, barH)}px`, background: color, borderRadius: '2px', border: bar.signal !== 'HOLD' ? `1px solid ${signalColor(bar.signal)}` : 'none' }} />
                      </div>
                    );
                  })}
                </div>
              </div>
              <div style={{ display: 'flex', gap: '16px', marginTop: '10px', fontSize: '11px' }}>
                <span><span style={{ color: '#10B981', fontWeight: 700 }}>▲ BUY</span> – Entry triggered</span>
                <span><span style={{ color: '#EF4444', fontWeight: 700 }}>▼ SELL</span> – Exit triggered</span>
                <span style={{ color: 'var(--text-muted)' }}>Hover bars for OHLC details</span>
              </div>
            </div>
          )}

          {/* Trade Ledger */}
          {activeSection === 'trades' && (
            <div className="glass-card" style={{ padding: '18px' }}>
              {result.trades.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)', fontSize: '13px' }}>No trades triggered in this period.</div>
              ) : (
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
                        {['Entry Time', 'Exit Time', 'Symbol', 'Type', 'Lots', 'Lot Size', 'Qty', 'Buy ₹', 'Sell ₹', '1 Lot Cost', 'Total Buy Price', 'P&L', 'P&L %', 'Exit Reason'].map(h => (
                          <th key={h} style={{ padding: '10px 12px', textAlign: 'left', color: 'var(--text-muted)', fontWeight: 600, whiteSpace: 'nowrap' }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {result.trades.map((t, i) => {
                        const lotSize = getLotSize(t.symbol);
                        const lotsCount = t.qty / lotSize;
                        return (
                          <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                            <td style={{ padding: '10px 12px', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{t.entry_time}</td>
                            <td style={{ padding: '10px 12px', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{t.exit_time}</td>
                            <td style={{ padding: '10px 12px', fontWeight: 600 }}>{t.symbol}</td>
                            <td style={{ padding: '10px 12px' }}><span style={{ fontSize: '10px', padding: '2px 7px', borderRadius: '10px', background: 'rgba(99,102,241,0.15)', color: '#818CF8' }}>{t.instrument_type}</span></td>
                            <td style={{ padding: '10px 12px', textAlign: 'center', fontWeight: 600, color: 'var(--accent-yellow)' }}>{lotsCount % 1 === 0 ? lotsCount : lotsCount.toFixed(1)}</td>
                            <td style={{ padding: '10px 12px', textAlign: 'center', color: 'var(--text-muted)' }}>{lotSize}</td>
                            <td style={{ padding: '10px 12px', textAlign: 'center' }}>{t.qty}</td>
                            <td style={{ padding: '10px 12px', color: 'var(--text-secondary)' }}>₹{t.entry_price.toFixed(2)}</td>
                            <td style={{ padding: '10px 12px', fontWeight: 600 }}>₹{t.exit_price.toFixed(2)}</td>
                            <td style={{ padding: '10px 12px', color: 'var(--text-secondary)' }}>₹{(lotSize * t.entry_price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                            <td style={{ padding: '10px 12px', fontWeight: 600, color: 'var(--text-secondary)' }}>₹{(t.qty * t.entry_price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                            <td style={{ padding: '10px 12px', fontWeight: 700, color: pnlColor(t.pnl) }}>{t.pnl >= 0 ? '+' : ''}₹{t.pnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                            <td style={{ padding: '10px 12px', color: pnlColor(t.pnl_pct) }}>{t.pnl_pct >= 0 ? '+' : ''}{t.pnl_pct}%</td>
                            <td style={{ padding: '10px 12px' }}>
                              <span style={{ fontSize: '10px', padding: '2px 8px', borderRadius: '10px', fontWeight: 700, background: t.exit_reason === 'STOP_LOSS' ? 'rgba(239,68,68,0.1)' : t.exit_reason === 'TARGET' ? 'rgba(16,185,129,0.1)' : 'rgba(245,158,11,0.1)', color: t.exit_reason === 'STOP_LOSS' ? '#EF4444' : t.exit_reason === 'TARGET' ? '#10B981' : '#F59E0B' }}>
                                {t.exit_reason}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* Trade Journal */}
          {activeSection === 'journal' && (
            <div className="glass-card" style={{ padding: '18px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px' }}>Detailed reasoning for every trade action — why the strategy bought or sold on each bar.</p>
              {result.journal.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)', fontSize: '13px' }}>No triggered actions in this period.</div>
              ) : result.journal.map((j, i) => (
                <div key={i} style={{ border: `1px solid ${j.action === 'BUY' ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)'}`, borderRadius: '8px', overflow: 'hidden' }}>
                  <button onClick={() => setExpandedJournal(expandedJournal === i ? null : i)} style={{ width: '100%', background: 'transparent', border: 'none', cursor: 'pointer', padding: '12px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                      <span style={{ fontSize: '11px', padding: '3px 10px', borderRadius: '10px', fontWeight: 700, background: j.action === 'BUY' ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)', color: j.action === 'BUY' ? '#10B981' : '#EF4444' }}>
                        {j.action === 'BUY' ? '▲ BUY' : '▼ SELL'}
                      </span>
                      <span style={{ fontSize: '12px', fontWeight: 600 }}>{j.ts}</span>
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>@ ₹{j.price?.toFixed(2)}</span>
                      {j.pnl !== undefined && <span style={{ fontSize: '12px', fontWeight: 700, color: pnlColor(j.pnl) }}>{j.pnl >= 0 ? '+' : ''}₹{j.pnl.toFixed(2)}</span>}
                    </div>
                    {expandedJournal === i ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </button>
                  {expandedJournal === i && (
                    <div style={{ padding: '0 16px 14px', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                      {j.note && <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '10px', marginBottom: '8px', lineHeight: '1.6' }}>{j.note}</p>}
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600 }}>CONDITIONS EVALUATED:</span>
                        {j.reason.map((r, ri) => (
                          <span key={ri} style={{ fontSize: '11px', padding: '4px 8px', borderRadius: '4px', background: 'rgba(255,255,255,0.04)', color: r.includes('✓') ? '#10B981' : 'var(--text-secondary)', fontFamily: 'monospace' }}>{r}</span>
                        ))}
                      </div>
                      <div style={{ marginTop: '8px', fontSize: '11px', color: 'var(--text-muted)' }}>
                        Capital after action: <strong style={{ color: '#fff' }}>₹{j.capital?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</strong>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
          {/* System Logs */}
          {activeSection === 'logs' && (
            <div className="glass-card" style={{ padding: '18px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px' }}>Intraday execution logs from the backtest engine including API resolutions and candle loads.</p>
              {!result.logs || result.logs.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)', fontSize: '13px' }}>No execution logs generated.</div>
              ) : (
                <div style={{
                  background: '#0c0f17',
                  border: '1px solid rgba(255,255,255,0.06)',
                  borderRadius: '6px',
                  padding: '14px',
                  maxHeight: '400px',
                  overflowY: 'auto',
                  fontFamily: 'SFMono-Regular, Consolas, Liberation Mono, Menlo, monospace',
                  fontSize: '11px',
                  lineHeight: '1.6',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '4px'
                }}>
                  {result.logs.map((log, i) => {
                    const isWarning = log.includes('WARNING');
                    return (
                      <div key={i} style={{ color: isWarning ? '#F59E0B' : '#a1a1aa' }}>
                        {log}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

        </div>
      )}
    </div>
  );
}
