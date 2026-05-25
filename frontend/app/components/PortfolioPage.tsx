'use client';

import React, { useState, useEffect } from 'react';
import { Shield, RefreshCw, AlertTriangle, User, TrendingUp, Settings, Briefcase } from 'lucide-react';
import { API_BASE } from '../config';

interface Holding {
  tradingsymbol: string;
  exchange: string;
  quantity: number;
  average_price: number;
  last_price: number;
  pnl: number;
}

interface Position {
  tradingsymbol: string;
  exchange: string;
  quantity: number;
  average_price: number;
  last_price: number;
  pnl: number;
}

interface PortfolioData {
  status: string;
  broker_name: string;
  profile: {
    user_id: string;
    user_name: string;
    email: string;
    broker: string;
  };
  margins: {
    cash: number;
    available: number;
    used: number;
    collateral: number;
    connected?: boolean;
  };
  holdings: Holding[];
  positions?: Position[];
}

interface PortfolioPageProps {
  onGoToSettings: () => void;
}

export default function PortfolioPage({ onGoToSettings }: PortfolioPageProps) {
  const [data, setData] = useState<PortfolioData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchFullPortfolio = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/broker/full-portfolio`);
      if (!res.ok) {
        throw new Error(`HTTP error! Status: ${res.status}`);
      }
      const result = await res.json();
      if (result.status === 'ERROR') {
        setError(result.message);
        setData(null);
      } else {
        setData(result);
      }
    } catch (e: any) {
      setError(e.message || 'Failed to establish active broker authorization.');
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFullPortfolio();
  }, []);

  if (loading) {
    return (
      <div className="glass-panel animate-pulse" style={{ margin: '24px', padding: '60px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '16px' }}>
        <RefreshCw className="animate-spin" size={40} style={{ color: '#8B5CF6' }} />
        <span style={{ fontSize: '14px', color: 'var(--text-secondary)', fontWeight: 500 }}>Connecting secure broker API gateway...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="glass-panel animate-slide-in" style={{ margin: '24px', padding: '40px', border: '1px solid rgba(239, 68, 68, 0.3)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '20px', textAlign: 'center' }}>
        <div style={{ padding: '16px', borderRadius: '50%', background: 'rgba(239, 68, 68, 0.1)', color: '#EF4444' }}>
          <AlertTriangle size={36} />
        </div>
        <div>
          <h2 style={{ fontSize: '18px', fontWeight: 800, color: '#fff' }}>Broker Connection Failed</h2>
          <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '8px', maxWidth: '500px', lineHeight: 1.5 }}>
            {error}
          </p>
        </div>
        <div style={{ display: 'flex', gap: '12px' }}>
          <button 
            className="btn-primary" 
            onClick={fetchFullPortfolio}
            style={{ padding: '10px 20px', borderRadius: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}
          >
            <RefreshCw size={16} /> Retry Connection
          </button>
          <button 
            className="btn-glass" 
            onClick={onGoToSettings}
            style={{ padding: '10px 20px', borderRadius: '8px', display: 'flex', alignItems: 'center', gap: '8px', color: '#8B5CF6' }}
          >
            <Settings size={16} /> Update API Settings
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="glass-panel animate-slide-in" style={{ margin: '24px', padding: '30px', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      
      {/* Tab Title */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ fontSize: '20px', display: 'flex', alignItems: 'center', gap: '10px', fontWeight: 800 }}>
            <Briefcase size={22} className="glow-green" style={{ color: '#10B981' }} /> My Live Broker Portfolio
          </h2>
          <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
            Connected vendor: <strong style={{ color: '#fff' }}>{data?.broker_name}</strong>. Fetching live holding allocations and margin ledgers.
          </p>
        </div>
        <button 
          className="btn-glass" 
          onClick={fetchFullPortfolio}
          style={{ padding: '8px 16px', borderRadius: '6px', display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px' }}
        >
          <RefreshCw size={14} /> Refresh Portfolio
        </button>
      </div>

      {/* Profile & Info Card */}
      <div className="glass-card" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', padding: '20px', background: 'rgba(255,255,255,0.02)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ padding: '10px', borderRadius: '8px', background: 'rgba(16, 185, 129, 0.1)', color: '#10B981' }}>
            <User size={18} />
          </div>
          <div>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Account Holder ID</span>
            <p style={{ fontSize: '14px', fontWeight: 700, color: '#fff' }}>{data?.profile.user_id}</p>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ padding: '10px', borderRadius: '8px', background: 'rgba(99, 102, 241, 0.1)', color: '#6366F1' }}>
            <Briefcase size={18} />
          </div>
          <div>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Profile Name</span>
            <p style={{ fontSize: '14px', fontWeight: 700, color: '#fff' }}>{data?.profile.user_name}</p>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ padding: '10px', borderRadius: '8px', background: data?.margins.connected !== false ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)', color: data?.margins.connected !== false ? '#10B981' : '#EF4444' }}>
            <Shield size={18} />
          </div>
          <div>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Vendor Connection Status</span>
            <p style={{ fontSize: '13px', fontWeight: 700, color: data?.margins.connected !== false ? '#10B981' : '#EF4444', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: data?.margins.connected !== false ? '#10B981' : '#EF4444', display: 'inline-block' }}></span> 
              {data?.margins.connected !== false ? 'Active Session' : 'Disconnected / Outage'}
            </p>
          </div>
        </div>
      </div>

      {/* Margins Grid */}
      <div>
        <h3 style={{ fontSize: '14px', fontWeight: 700, marginBottom: '12px', color: '#fff' }}>Account Margin Balances</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px' }}>
          <div className="glass-card" style={{ padding: '16px' }}>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Total Cash Balance</span>
            <p style={{ fontSize: '20px', fontWeight: 800, marginTop: '4px', color: data?.margins.connected !== false ? '#fff' : 'var(--text-muted)' }}>
              {data?.margins.connected !== false ? `₹${data?.margins.cash.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : '—'}
            </p>
          </div>
          <div className="glass-card" style={{ padding: '16px', borderLeft: data?.margins.connected !== false ? '3px solid #10B981' : '3px solid var(--text-muted)' }}>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Available Margin</span>
            <p style={{ fontSize: '20px', fontWeight: 800, marginTop: '4px', color: data?.margins.connected !== false ? '#10B981' : 'var(--text-muted)' }}>
              {data?.margins.connected !== false ? `₹${data?.margins.available.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : '—'}
            </p>
          </div>
          <div className="glass-card" style={{ padding: '16px', borderLeft: data?.margins.connected !== false ? '3px solid #EF4444' : '3px solid var(--text-muted)' }}>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Used Margin</span>
            <p style={{ fontSize: '20px', fontWeight: 800, marginTop: '4px', color: data?.margins.connected !== false ? '#EF4444' : 'var(--text-muted)' }}>
              {data?.margins.connected !== false ? `₹${data?.margins.used.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : '—'}
            </p>
          </div>
          <div className="glass-card" style={{ padding: '16px' }}>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Collateral Value</span>
            <p style={{ fontSize: '20px', fontWeight: 800, marginTop: '4px', color: data?.margins.connected !== false ? '#3B82F6' : 'var(--text-muted)' }}>
              {data?.margins.connected !== false ? `₹${data?.margins.collateral.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : '—'}
            </p>
          </div>
        </div>
      </div>

      {/* Holdings Section */}
      <div>
        <h3 style={{ fontSize: '14px', fontWeight: 700, marginBottom: '12px', color: '#fff' }}>Broker Equity Holdings</h3>
        
        {(!data?.holdings || data.holdings.length === 0) ? (
          <div className="glass-card" style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
            No equity holdings currently active in this broker account.
          </div>
        ) : (
          <div style={{ overflowX: 'auto', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ background: 'rgba(255,255,255,0.02)', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                  <th style={{ padding: '12px', textAlign: 'left', color: 'var(--text-muted)' }}>Instrument</th>
                  <th style={{ padding: '12px', textAlign: 'center', color: 'var(--text-muted)' }}>Exchange</th>
                  <th style={{ padding: '12px', textAlign: 'center', color: 'var(--text-muted)' }}>Quantity</th>
                  <th style={{ padding: '12px', textAlign: 'right', color: 'var(--text-muted)' }}>Avg Buy Price</th>
                  <th style={{ padding: '12px', textAlign: 'right', color: 'var(--text-muted)' }}>LTP Price</th>
                  <th style={{ padding: '12px', textAlign: 'right', color: 'var(--text-muted)' }}>Net P&L</th>
                </tr>
              </thead>
              <tbody>
                {data.holdings.map((h, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                    <td style={{ padding: '12px', fontWeight: 700, color: '#fff' }}>{h.tradingsymbol}</td>
                    <td style={{ padding: '12px', textAlign: 'center' }}>
                      <span style={{ fontSize: '10px', padding: '2px 6px', borderRadius: '4px', background: 'rgba(255,255,255,0.05)', color: 'var(--text-secondary)' }}>
                        {h.exchange}
                      </span>
                    </td>
                    <td style={{ padding: '12px', textAlign: 'center', fontWeight: 600 }}>{h.quantity}</td>
                    <td style={{ padding: '12px', textAlign: 'right', color: 'var(--text-secondary)' }}>₹{h.average_price.toFixed(2)}</td>
                    <td style={{ padding: '12px', textAlign: 'right', color: '#fff', fontWeight: 600 }}>₹{h.last_price.toFixed(2)}</td>
                    <td style={{ padding: '12px', textAlign: 'right', fontWeight: 700, color: h.pnl >= 0 ? '#10B981' : '#EF4444' }}>
                      {h.pnl >= 0 ? '+' : ''}₹{h.pnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Positions Section */}
      <div style={{ marginTop: '12px' }}>
        <h3 style={{ fontSize: '14px', fontWeight: 700, marginBottom: '12px', color: '#fff' }}>Broker Active & Day Positions</h3>
        
        {(!data?.positions || data.positions.length === 0) ? (
          <div className="glass-card" style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
            No active derivatives or day positions currently open in this broker account.
          </div>
        ) : (
          <div style={{ overflowX: 'auto', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ background: 'rgba(255,255,255,0.02)', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                  <th style={{ padding: '12px', textAlign: 'left', color: 'var(--text-muted)' }}>Instrument</th>
                  <th style={{ padding: '12px', textAlign: 'center', color: 'var(--text-muted)' }}>Exchange</th>
                  <th style={{ padding: '12px', textAlign: 'center', color: 'var(--text-muted)' }}>Net Qty</th>
                  <th style={{ padding: '12px', textAlign: 'right', color: 'var(--text-muted)' }}>Avg Cost</th>
                  <th style={{ padding: '12px', textAlign: 'right', color: 'var(--text-muted)' }}>LTP Price</th>
                  <th style={{ padding: '12px', textAlign: 'right', color: 'var(--text-muted)' }}>Net P&L</th>
                </tr>
              </thead>
              <tbody>
                {data.positions.map((p, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                    <td style={{ padding: '12px', fontWeight: 700, color: '#fff' }}>{p.tradingsymbol}</td>
                    <td style={{ padding: '12px', textAlign: 'center' }}>
                      <span style={{ fontSize: '10px', padding: '2px 6px', borderRadius: '4px', background: 'rgba(255,255,255,0.05)', color: 'var(--text-secondary)' }}>
                        {p.exchange}
                      </span>
                    </td>
                    <td style={{ padding: '12px', textAlign: 'center', fontWeight: 600 }}>{p.quantity}</td>
                    <td style={{ padding: '12px', textAlign: 'right', color: 'var(--text-secondary)' }}>₹{p.average_price.toFixed(2)}</td>
                    <td style={{ padding: '12px', textAlign: 'right', color: '#fff', fontWeight: 600 }}>₹{p.last_price.toFixed(2)}</td>
                    <td style={{ padding: '12px', textAlign: 'right', fontWeight: 700, color: p.pnl >= 0 ? '#10B981' : '#EF4444' }}>
                      {p.pnl >= 0 ? '+' : ''}₹{p.pnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

    </div>
  );
}
