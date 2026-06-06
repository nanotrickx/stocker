'use client';

import React, { useState, useEffect } from 'react';
import { RefreshCw, TrendingUp, TrendingDown, Star, LineChart, Plus, Trash2, X } from 'lucide-react';
import { API_BASE } from '../config';

interface WatchlistItem {
  symbol: string;
  name: string;
}

interface WatchlistProps {
  onSelectSymbol: (symbol: string) => void;
  selectedSymbol: string;
}

const DEFAULT_WATCHLIST: WatchlistItem[] = [
  { symbol: 'NSE:RELIANCE', name: 'Reliance Industries' },
  { symbol: 'NSE:TCS', name: 'Tata Consultancy Services' },
  { symbol: 'NSE:INFY', name: 'Infosys Ltd' },
  { symbol: 'NSE:HDFCBANK', name: 'HDFC Bank Ltd' },
  { symbol: 'NSE:ICICIBANK', name: 'ICICI Bank Ltd' },
  { symbol: 'NSE:SBIN', name: 'State Bank of India' },
  { symbol: 'NSE:TATAMOTORS', name: 'Tata Motors Ltd' }
];

const SYMBOL_NAMES: Record<string, string> = {
  'NSE:RELIANCE': 'Reliance Industries',
  'NSE:TCS': 'Tata Consultancy Services',
  'NSE:INFY': 'Infosys Ltd',
  'NSE:HDFCBANK': 'HDFC Bank Ltd',
  'NSE:ICICIBANK': 'ICICI Bank Ltd',
  'NSE:SBIN': 'State Bank of India',
  'NSE:TATAMOTORS': 'Tata Motors Ltd',
  'NSE:BHARTIARTL': 'Bharti Airtel Ltd',
  'NSE:ITC': 'ITC Ltd',
  'NSE:LT': 'Larsen & Toubro Ltd',
  'NSE:HINDUNILVR': 'Hindustan Unilever Ltd',
  'NSE:AXISBANK': 'Axis Bank Ltd',
  'NSE:KOTAKBANK': 'Kotak Mahindra Bank Ltd',
  'NSE:MARUTI': 'Maruti Suzuki India Ltd',
  'NSE:WIPRO': 'Wipro Ltd',
  'NSE:NIFTY 50': 'Nifty 50 Index',
  'NSE:NIFTY BANK': 'Nifty Bank Index'
};

export default function Watchlist({ onSelectSymbol, selectedSymbol }: WatchlistProps) {
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>(DEFAULT_WATCHLIST);
  const [quotes, setQuotes] = useState<Record<string, { price: number; change: number; pct: number }>>({});
  const [loading, setLoading] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newSymbolInput, setNewSymbolInput] = useState('');

  // 1. Load watchlist from localStorage on mount
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('stocker_watchlist');
      if (saved) {
        try {
          setWatchlist(JSON.parse(saved));
        } catch (e) {
          console.error('Failed to parse saved watchlist:', e);
        }
      }
    }
  }, []);

  // 2. Save watchlist when it changes
  useEffect(() => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('stocker_watchlist', JSON.stringify(watchlist));
    }
  }, [watchlist]);

  const fetchQuotes = async () => {
    if (watchlist.length === 0) {
      setQuotes({});
      return;
    }
    setLoading(true);
    try {
      const results = await Promise.all(
        watchlist.map(async (item) => {
          try {
            // Fetch 2 days of historical data to compute daily price difference
            const res = await fetch(`${API_BASE}/api/historical-data?symbol=${encodeURIComponent(item.symbol)}&days=2`);
            if (res.ok) {
              const data = await res.json();
              if (data && data.length >= 2) {
                const latest = data[data.length - 1];
                const prev = data[data.length - 2];
                const change = latest.close - prev.close;
                const pct = (change / prev.close) * 100;
                return {
                  symbol: item.symbol,
                  price: latest.close,
                  change: change,
                  pct: pct
                };
              } else if (data && data.length === 1) {
                const latest = data[0];
                return {
                  symbol: item.symbol,
                  price: latest.close,
                  change: 0,
                  pct: 0
                };
              }
            }
          } catch (e) {
            console.error('Error fetching watchlist quote for', item.symbol, e);
          }
          return null;
        })
      );

      const newQuotes: Record<string, { price: number; change: number; pct: number }> = {};
      results.forEach((r) => {
        if (r) {
          newQuotes[r.symbol] = {
            price: r.price,
            change: r.change,
            pct: r.pct
          };
        }
      });
      setQuotes(newQuotes);
    } catch (e) {
      console.error('Error updating watchlist quotes', e);
    } finally {
      setLoading(false);
    }
  };

  // 3. Fetch quotes on watchlist change or register polling interval
  useEffect(() => {
    fetchQuotes();
    const interval = setInterval(fetchQuotes, 20000); // refresh every 20 seconds
    return () => clearInterval(interval);
  }, [watchlist]);

  const handleAddSymbol = (e: React.FormEvent) => {
    e.preventDefault();
    let sym = newSymbolInput.trim().toUpperCase();
    if (!sym) return;

    // Standardize symbol format
    if (!sym.startsWith('NSE:')) {
      sym = `NSE:${sym}`;
    }

    // Check for duplicates
    if (watchlist.some((item) => item.symbol === sym)) {
      alert('Symbol is already in your watchlist!');
      return;
    }

    const displayName = SYMBOL_NAMES[sym] || sym.replace('NSE:', '');
    setWatchlist((prev) => [...prev, { symbol: sym, name: displayName }]);
    setNewSymbolInput('');
    setShowAddForm(false);
  };

  const handleRemoveSymbol = (e: React.MouseEvent, symbolToRemove: string) => {
    e.stopPropagation(); // Avoid selecting the card
    setWatchlist((prev) => prev.filter((item) => item.symbol !== symbolToRemove));
  };

  return (
    <div className="glass-panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      
      {/* Watchlist Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '8px', margin: 0 }}>
          <Star size={16} style={{ color: 'var(--accent-yellow)' }} /> Stocks Watchlist
        </h3>
        <div style={{ display: 'flex', gap: '6px' }}>
          <button 
            onClick={() => setShowAddForm(!showAddForm)} 
            className="btn-glass"
            style={{ 
              width: '28px', 
              height: '28px', 
              borderRadius: '6px', 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center',
              padding: 0,
              cursor: 'pointer',
              color: showAddForm ? 'var(--accent-yellow)' : 'inherit'
            }}
            title="Add Stock to Watchlist"
          >
            {showAddForm ? <X size={12} /> : <Plus size={12} />}
          </button>
          <button 
            onClick={fetchQuotes} 
            disabled={loading}
            className="btn-glass"
            style={{ 
              width: '28px', 
              height: '28px', 
              borderRadius: '6px', 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center',
              padding: 0,
              cursor: loading ? 'not-allowed' : 'pointer'
            }}
            title="Refresh watchlist quotes"
          >
            <RefreshCw size={12} className={loading ? 'spin-anim' : ''} />
          </button>
        </div>
      </div>

      {/* Add Stock Form */}
      {showAddForm && (
        <form onSubmit={handleAddSymbol} className="animate-slide-in" style={{ display: 'flex', gap: '8px', background: 'rgba(255,255,255,0.02)', padding: '10px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
          <input 
            type="text" 
            value={newSymbolInput}
            onChange={(e) => setNewSymbolInput(e.target.value)}
            placeholder="Enter Symbol (e.g. RELIANCE, TCS)" 
            autoFocus
            style={{ 
              flex: 1, 
              background: 'rgba(0, 0, 0, 0.3)', 
              border: '1px solid var(--border-glass)', 
              borderRadius: '6px', 
              padding: '6px 10px', 
              fontSize: '12px', 
              color: 'var(--text-primary)',
              outline: 'none'
            }}
          />
          <button 
            type="submit" 
            className="btn-glass" 
            style={{ 
              padding: '6px 10px', 
              fontSize: '11px', 
              borderRadius: '6px', 
              color: 'var(--accent-green)',
              border: '1px solid rgba(16, 185, 129, 0.2)',
              cursor: 'pointer' 
            }}
          >
            Add
          </button>
        </form>
      )}

      {/* Watchlist Body */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '350px', overflowY: 'auto' }}>
        {watchlist.length === 0 ? (
          <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
            No stocks in watchlist. Click the "+" button to add your favorites.
          </div>
        ) : (
          watchlist.map((item) => {
            const q = quotes[item.symbol];
            const isSelected = selectedSymbol === item.symbol;
            
            const priceStr = q ? `₹${q.price.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—';
            const isPos = q ? q.change >= 0 : true;
            const changeStr = q 
              ? `${isPos ? '+' : ''}${q.change.toFixed(2)} (${isPos ? '+' : ''}${q.pct.toFixed(2)}%)` 
              : '';

            return (
              <div 
                key={item.symbol} 
                onClick={() => onSelectSymbol(item.symbol)}
                className="glass-card watchlist-card" 
                style={{ 
                  display: 'flex', 
                  justifyContent: 'space-between', 
                  alignItems: 'center',
                  padding: '10px 14px',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  border: isSelected ? '1px solid rgba(99, 102, 241, 0.4)' : '1px solid var(--border-glass)',
                  background: isSelected ? 'rgba(99, 102, 241, 0.05)' : 'rgba(255,255,255,0.01)',
                  transition: 'all 0.2s ease-in-out'
                }}
                title="Click to view interactive chart"
              >
                {/* Left Column: Symbol details */}
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span style={{ fontSize: '13px', fontWeight: 700, color: isSelected ? '#a78bfa' : '#fff' }}>
                      {item.symbol.replace('NSE:', '')}
                    </span>
                    {isSelected && <LineChart size={12} style={{ color: '#8B5CF6' }} />}
                  </div>
                  <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                    {item.name}
                  </span>
                </div>

                {/* Right Column: Price quotes & actions */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div style={{ textAlign: 'right', display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
                    <span style={{ fontSize: '13px', fontWeight: 800, color: 'var(--text-primary)', fontFamily: 'monospace' }}>
                      {priceStr}
                    </span>
                    {q && (
                      <span style={{ 
                        fontSize: '9px', 
                        fontWeight: 700, 
                        color: isPos ? 'var(--accent-green)' : 'var(--accent-red)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '2px',
                        marginTop: '2px'
                      }}>
                        {isPos ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
                        {changeStr}
                      </span>
                    )}
                  </div>
                  
                  {/* Delete Button */}
                  <button 
                    onClick={(e) => handleRemoveSymbol(e, item.symbol)}
                    className="watchlist-delete-btn"
                    style={{
                      background: 'transparent',
                      border: 'none',
                      color: 'var(--text-muted)',
                      cursor: 'pointer',
                      padding: '4px',
                      borderRadius: '4px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      transition: 'all 0.2s'
                    }}
                    title={`Remove ${item.symbol.replace('NSE:', '')}`}
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            );
          })
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
        .watchlist-card {
          position: relative;
        }
        .watchlist-delete-btn {
          opacity: 0.15;
          transition: all 0.2s ease-in-out;
        }
        .watchlist-card:hover .watchlist-delete-btn {
          opacity: 0.7;
        }
        .watchlist-delete-btn:hover {
          opacity: 1 !important;
          color: var(--accent-red) !important;
          background: rgba(239, 68, 68, 0.12) !important;
        }
      `}</style>
    </div>
  );
}
