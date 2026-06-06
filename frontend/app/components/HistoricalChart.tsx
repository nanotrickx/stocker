'use client';

import React, { useState, useEffect, useRef } from 'react';
import { createChart, ColorType, CandlestickSeries } from 'lightweight-charts';
import { LineChart, RefreshCw } from 'lucide-react';
import { API_BASE } from '../config';

interface HistoricalChartProps {
  symbol?: string;
  refreshTrigger?: number;
  theme?: string;
}

export default function HistoricalChart({ symbol = 'NSE:NIFTY 50', refreshTrigger = 0, theme = 'dark' }: HistoricalChartProps) {
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);

  const fetchChartData = async () => {
    setLoading(true);
    setError(false);
    try {
      const res = await fetch(`${API_BASE}/api/historical-data?symbol=${encodeURIComponent(symbol)}`);
      if (res.ok) {
        const candles = await res.json();
        setData(candles);
      } else {
        setError(true);
      }
    } catch (e) {
      console.error('Failed to load chart candles:', e);
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchChartData();
  }, [symbol, refreshTrigger]);

  useEffect(() => {
    if (!chartContainerRef.current || data.length === 0) return;

    // Initialize Lightweight Chart
    const isLight = theme === 'light';
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: isLight ? '#4B5563' : '#9CA3AF',
        fontSize: 10,
        fontFamily: 'var(--font-sans)'
      },
      grid: {
        vertLines: { color: isLight ? 'rgba(0, 0, 0, 0.05)' : 'rgba(255, 255, 255, 0.02)' },
        horzLines: { color: isLight ? 'rgba(0, 0, 0, 0.05)' : 'rgba(255, 255, 255, 0.02)' }
      },
      rightPriceScale: {
        borderVisible: false,
        textColor: isLight ? '#4B5563' : '#9CA3AF'
      },
      timeScale: {
        borderVisible: false,
        timeVisible: true,
        secondsVisible: false
      },
      width: chartContainerRef.current.clientWidth,
      height: 230,
      crosshair: {
        vertLine: {
          color: 'rgba(99, 102, 241, 0.4)',
          width: 1,
          style: 3, // dashed
          labelVisible: true
        },
        horzLine: {
          color: 'rgba(99, 102, 241, 0.4)',
          width: 1,
          style: 3, // dashed
          labelVisible: true
        }
      }
    });

    chartRef.current = chart;

    // Add Candlestick Series
    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10B981',
      downColor: '#EF4444',
      borderUpColor: '#10B981',
      borderDownColor: '#EF4444',
      wickUpColor: '#10B981',
      wickDownColor: '#EF4444'
    });

    // Format data: lightweight-charts requires time key to be sorted YYYY-MM-DD
    const formattedData = data
      .map(item => ({
        time: item.date,
        open: item.open,
        high: item.high,
        low: item.low,
        close: item.close
      }))
      .sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime());

    candlestickSeries.setData(formattedData);

    // Auto-fit content
    chart.timeScale().fitContent();

    // Handle container resize
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
      chartRef.current = null;
    };
  }, [data]);

  // Extract selected stock info for stats display
  const latestCandle = data.length > 0 ? data[data.length - 1] : null;
  const prevCandle = data.length > 1 ? data[data.length - 2] : null;

  const lastDayEnd = prevCandle ? prevCandle.close : (latestCandle ? latestCandle.open : 0);
  const latestPrice = latestCandle ? latestCandle.close : 0;
  const change = latestPrice - lastDayEnd;
  const pct = lastDayEnd !== 0 ? (change / lastDayEnd) * 100 : 0;

  const openPrice = latestCandle ? latestCandle.open : 0;
  const high = latestCandle ? latestCandle.high : 0;
  const low = latestCandle ? latestCandle.low : 0;
  const volume = latestCandle ? latestCandle.volume : 0;

  return (
    <div className="glass-panel animate-slide-in" style={{ padding: '20px', minHeight: '340px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <LineChart size={18} className="glow-green" />
          <div>
            <h3 style={{ fontSize: '15px', fontWeight: 700 }}>Interactive Spot Price Chart</h3>
            <p style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>TradingView candlestick trend for {symbol}</p>
          </div>
        </div>
        
        <button 
          onClick={fetchChartData}
          disabled={loading}
          className="btn-glass" 
          style={{ padding: '6px 10px', fontSize: '11px', borderRadius: '6px', display: 'flex', alignItems: 'center', gap: '6px', cursor: loading ? 'not-allowed' : 'pointer' }}
        >
          <RefreshCw size={12} className={loading ? 'spin-anim' : ''} /> {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {/* Selected Stock Info Banner */}
      {!loading && !error && latestCandle && (
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: 'repeat(auto-fit, minmax(90px, 1fr))', 
          gap: '12px', 
          background: 'var(--sub-panel-bg)', 
          padding: '12px 16px', 
          borderRadius: '8px', 
          border: '1px solid var(--border-glass)' 
        }}>
          <div>
            <span style={{ fontSize: '10px', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Last Day End</span>
            <span style={{ fontSize: '13px', fontWeight: 700, fontFamily: 'monospace', color: 'var(--text-primary)' }}>
              ₹{lastDayEnd.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>
          <div>
            <span style={{ fontSize: '10px', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Latest Close</span>
            <span style={{ fontSize: '13px', fontWeight: 800, fontFamily: 'monospace', color: change >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
              ₹{latestPrice.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>
          <div>
            <span style={{ fontSize: '10px', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Net Change</span>
            <span style={{ fontSize: '12px', fontWeight: 700, fontFamily: 'monospace', color: change >= 0 ? 'var(--accent-green)' : 'var(--accent-red)', display: 'flex', alignItems: 'center', gap: '2px' }}>
              {change >= 0 ? '+' : ''}{change.toFixed(2)} ({change >= 0 ? '+' : ''}{pct.toFixed(2)}%)
            </span>
          </div>
          <div>
            <span style={{ fontSize: '10px', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Day Range (H/L)</span>
            <span style={{ fontSize: '11px', fontWeight: 600, fontFamily: 'monospace', color: 'var(--text-secondary)' }}>
              ₹{high.toLocaleString('en-IN', { maximumFractionDigits: 1 })} / ₹{low.toLocaleString('en-IN', { maximumFractionDigits: 1 })}
            </span>
          </div>
          <div>
            <span style={{ fontSize: '10px', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Volume</span>
            <span style={{ fontSize: '11px', fontWeight: 600, fontFamily: 'monospace', color: 'var(--text-secondary)' }}>
              {volume.toLocaleString('en-IN')}
            </span>
          </div>
        </div>
      )}

      <div style={{ flex: 1, minHeight: '230px', position: 'relative' }}>
        {loading && data.length === 0 ? (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
            ⏳ Loading historical candle streams...
          </div>
        ) : error && data.length === 0 ? (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent-red)', fontSize: '13px' }}>
            ⚠️ Error communicating with uvicorn chart server.
          </div>
        ) : (
          <div ref={chartContainerRef} style={{ width: '100%', height: '230px' }} />
        )}
      </div>

      <style jsx global>{`
        @keyframes rotateSpin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        .spin-anim {
          animation: rotateSpin 1s linear infinite;
        }
      `}</style>
    </div>
  );
}
