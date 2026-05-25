'use client';

import React, { useState, useEffect } from 'react';
import { 
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid 
} from 'recharts';
import { LineChart, RefreshCw } from 'lucide-react';
import { API_BASE } from '../config';

interface HistoricalChartProps {
  symbol?: string;
  refreshTrigger?: number;
}

export default function HistoricalChart({ symbol = 'NSE:NIFTY 50', refreshTrigger = 0 }: HistoricalChartProps) {
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

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

  return (
    <div className="glass-panel animate-slide-in" style={{ padding: '20px', minHeight: '340px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <LineChart size={18} className="glow-green" />
          <div>
            <h3 style={{ fontSize: '15px', fontWeight: 700 }}>Interactive Spot Price Chart</h3>
            <p style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Daily trend for {symbol}</p>
          </div>
        </div>
        
        <button 
          onClick={fetchChartData}
          className="btn-glass" 
          style={{ padding: '6px 10px', fontSize: '11px', borderRadius: '6px', display: 'flex', alignItems: 'center', gap: '6px' }}
        >
          <RefreshCw size={12} className={loading ? 'spin-anim' : ''} /> {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

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
          <ResponsiveContainer width="100%" height={230}>
            <AreaChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="colorClose" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#8B5CF6" stopOpacity={0.4}/>
                  <stop offset="95%" stopColor="#8B5CF6" stopOpacity={0.0}/>
                </linearGradient>
              </defs>
              
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" vertical={false} />
              
              <XAxis 
                dataKey="date" 
                stroke="var(--text-muted)" 
                tickLine={false} 
                fontSize={10} 
                dy={10}
                tickFormatter={(tick) => {
                  try {
                    const parts = tick.split('-');
                    return `${parts[2]}/${parts[1]}`;
                  } catch (e) {
                    return tick;
                  }
                }}
              />
              
              <YAxis 
                domain={['auto', 'auto']} 
                stroke="var(--text-muted)" 
                tickLine={false} 
                fontSize={10} 
                dx={-5}
                tickFormatter={(val) => `₹${val.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`}
              />
              
              <Tooltip 
                contentStyle={{ 
                  background: '#0D121D', 
                  border: '1px solid rgba(255, 255, 255, 0.08)', 
                  borderRadius: '8px', 
                  fontSize: '12px',
                  color: 'var(--text-primary)',
                  boxShadow: 'var(--shadow-premium)'
                }}
                labelStyle={{ fontWeight: 700, color: '#8B5CF6', marginBottom: '4px' }}
                formatter={(val: any) => [`₹${parseFloat(val).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`, 'Close Spot']}
              />
              
              <Area 
                type="monotone" 
                dataKey="close" 
                stroke="#8B5CF6" 
                strokeWidth={2} 
                fillOpacity={1} 
                fill="url(#colorClose)" 
              />
            </AreaChart>
          </ResponsiveContainer>
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
