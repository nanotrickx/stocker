'use client';

import React from 'react';
import { Activity, RefreshCw, Settings } from 'lucide-react';

interface HeaderProps {
  wsConnected: boolean;
  positionsCount: number;
  onRefresh: () => void;
  onOpenSettings: () => void;
}

export default function Header({ wsConnected, positionsCount, onRefresh, onOpenSettings }: HeaderProps) {
  return (
    <header className="glass-panel" style={{ margin: '16px 24px 0 24px', padding: '16px 24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderRadius: '16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <Activity size={28} className="glow-green" />
        <div>
          <h1 style={{ fontSize: '22px', fontWeight: 800, fontFamily: 'var(--font-display)', display: 'flex', alignItems: 'center', gap: '8px' }}>
            STOCKER <span style={{ fontSize: '11px', padding: '2px 8px', background: 'rgba(99, 102, 241, 0.2)', color: '#8B5CF6', borderRadius: '12px', border: '1px solid rgba(99, 102, 241, 0.4)' }}>ALPHA v1.5</span>
          </h1>
          <p style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Live Multi-Vendor Options Core</p>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px' }}>
          <span className={`pulsar ${wsConnected ? '' : 'red'}`}></span>
          <span style={{ color: wsConnected ? 'var(--text-primary)' : 'var(--accent-red)', fontWeight: 500 }}>
            {wsConnected ? 'LIVE FEED ACTIVE' : 'CONNECTION OFFLINE'}
          </span>
        </div>

        <div className="glass-card" style={{ padding: '6px 14px', display: 'flex', alignItems: 'center', gap: '16px', borderRadius: '10px' }}>
          <div>
            <p style={{ fontSize: '9px', color: 'var(--text-muted)' }}>MOCK MARGIN</p>
            <p style={{ fontSize: '14px', fontWeight: 700, color: 'var(--accent-green)' }}>₹1,00,000.00</p>
          </div>
          <div>
            <p style={{ fontSize: '9px', color: 'var(--text-muted)' }}>OPEN TRADES</p>
            <p style={{ fontSize: '14px', fontWeight: 700, color: '#8B5CF6', textAlign: 'center' }}>{positionsCount}</p>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn-glass" onClick={onRefresh} style={{ padding: '8px 12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <RefreshCw size={14} />
          </button>
          <button className="btn-glass" onClick={onOpenSettings} style={{ padding: '8px 12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Settings size={14} /> Settings
          </button>
        </div>
      </div>
    </header>
  );
}
