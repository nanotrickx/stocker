'use client';

import React, { useState, useMemo } from 'react';
import { Trash2, ShieldAlert, Filter, ListFilter, Send } from 'lucide-react';
import { Trade } from '../types';

interface TradeLedgerProps {
  tradeHistory: Trade[];
  onClear: () => void;
  onSendTelegramLedger?: (filteredTrades: Trade[]) => void;
}

const SELECT_STYLE: React.CSSProperties = {
  background: 'rgba(0, 0, 0, 0.3)',
  border: '1px solid rgba(255, 255, 255, 0.08)',
  borderRadius: '6px',
  color: '#fff',
  padding: '6px 12px',
  fontSize: '12px',
  outline: 'none',
  minWidth: '120px',
};

export default function TradeLedger({ tradeHistory, onClear, onSendTelegramLedger }: TradeLedgerProps) {
  const [strategyFilter, setStrategyFilter] = useState('ALL');
  const [symbolFilter, setSymbolFilter] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [modeFilter, setModeFilter] = useState('ALL');

  // Resolve unique filter options dynamically from data
  const uniqueStrategies = useMemo(() => {
    const names = new Set<string>();
    tradeHistory.forEach((t) => {
      if (t.strategy_name) names.add(t.strategy_name);
      else if (t.strategy_id) names.add(t.strategy_id);
    });
    return Array.from(names);
  }, [tradeHistory]);

  const uniqueSymbols = useMemo(() => {
    const symbols = new Set<string>();
    tradeHistory.forEach((t) => symbols.add(t.symbol));
    return Array.from(symbols);
  }, [tradeHistory]);

  // Filter logic
  const filteredTrades = useMemo(() => {
    return tradeHistory.filter((t) => {
      const name = t.strategy_name || t.strategy_id;
      if (strategyFilter !== 'ALL' && name !== strategyFilter) return false;
      if (symbolFilter !== 'ALL' && t.symbol !== symbolFilter) return false;
      if (statusFilter !== 'ALL' && t.status !== statusFilter) return false;
      if (modeFilter !== 'ALL' && t.mode !== modeFilter) return false;
      return true;
    });
  }, [tradeHistory, strategyFilter, symbolFilter, statusFilter, modeFilter]);

  const fmtTime = (t?: string) => {
    if (!t) return '--';
    try {
      const d = new Date(t);
      return d.toLocaleString('en-IN', {
        day: '2-digit',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: true,
      });
    } catch {
      return t;
    }
  };

  return (
    <div className="glass-panel animate-slide-in" style={{ margin: '24px', padding: '24px' }}>
      
      {/* Header Row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h2 style={{ fontSize: '18px', fontWeight: 700 }}>Stocker Trade History Ledger</h2>
          <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Lists closed and active options/equity positions</p>
        </div>

        <div style={{ display: 'flex', gap: '12px' }}>
          {onSendTelegramLedger && tradeHistory.length > 0 && (
            <button
              onClick={() => onSendTelegramLedger(filteredTrades)}
              className="btn-glass"
              style={{
                padding: '8px 16px',
                color: '#10B981',
                border: '1px solid rgba(16, 185, 129, 0.2)',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                fontSize: '13px',
              }}
            >
              <Send size={14} /> Send to Telegram
            </button>
          )}

          <button
            onClick={onClear}
            className="btn-glass"
            style={{
              padding: '8px 16px',
              color: 'var(--accent-red)',
              border: '1px solid rgba(244, 63, 94, 0.2)',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              fontSize: '13px',
            }}
          >
            <Trash2 size={14} /> Clear Ledger Records
          </button>
        </div>
      </div>

      {/* Sleek Filter Bar */}
      {tradeHistory.length > 0 && (
        <div
          style={{
            display: 'flex',
            gap: '12px',
            alignItems: 'center',
            marginBottom: '20px',
            padding: '12px 16px',
            background: 'rgba(255, 255, 255, 0.02)',
            border: '1px solid rgba(255, 255, 255, 0.05)',
            borderRadius: '8px',
            flexWrap: 'wrap',
          }}
        >
          <span style={{ fontSize: '12px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600 }}>
            <ListFilter size={14} style={{ color: '#8B5CF6' }} /> Filter Ledger:
          </span>

          {/* Strategy filter */}
          <select value={strategyFilter} onChange={(e) => setStrategyFilter(e.target.value)} style={SELECT_STYLE}>
            <option value="ALL">All Strategies</option>
            {uniqueStrategies.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>

          {/* Symbol filter */}
          <select value={symbolFilter} onChange={(e) => setSymbolFilter(e.target.value)} style={SELECT_STYLE}>
            <option value="ALL">All Symbols</option>
            {uniqueSymbols.map((sym) => (
              <option key={sym} value={sym}>
                {sym}
              </option>
            ))}
          </select>

          {/* Status filter */}
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={SELECT_STYLE}>
            <option value="ALL">All Statuses</option>
            <option value="OPEN">OPEN</option>
            <option value="CLOSED">CLOSED</option>
          </select>

          {/* Mode filter */}
          <select value={modeFilter} onChange={(e) => setModeFilter(e.target.value)} style={SELECT_STYLE}>
            <option value="ALL">All Modes</option>
            <option value="PAPER">PAPER (Sandbox)</option>
            <option value="LIVE">LIVE (Kite)</option>
          </select>
        </div>
      )}

      {tradeHistory.length === 0 ? (
        <div style={{ padding: '60px 0', textAlign: 'center', color: 'var(--text-muted)' }}>
          <ShieldAlert size={48} style={{ margin: '0 auto 16px auto', display: 'block', opacity: 0.3 }} />
          <p style={{ fontSize: '14px' }}>No completed trade records found in the database ledger.</p>
        </div>
      ) : filteredTrades.length === 0 ? (
        <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--text-muted)', border: '1px dashed rgba(255,255,255,0.05)', borderRadius: '8px' }}>
          <Filter size={32} style={{ margin: '0 auto 12px auto', display: 'block', opacity: 0.3 }} />
          <p style={{ fontSize: '13px' }}>No trade ledger rows match the selected filters.</p>
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className="options-table" style={{ fontSize: '12px' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-glass)' }}>
                <th>ID</th>
                <th>Strategy / Instance</th>
                <th>Symbol</th>
                <th>Option Type</th>
                <th>Qty</th>
                <th>Entry Price</th>
                <th>Entry Time</th>
                <th>Exit Price</th>
                <th>Exit Time</th>
                <th>Lot Value (₹)</th>
                <th>Gain (%)</th>
                <th>P&L (₹)</th>
                <th>Status</th>
                <th>Execution</th>
                <th>Exit Reason</th>
                <th>Report</th>
              </tr>
            </thead>
            <tbody>
              {filteredTrades.map((trade) => {
                const isGain = (trade.pnl || 0) >= 0;
                return (
                  <tr key={trade.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.02)' }}>
                    <td>#{trade.id}</td>
                    <td style={{ fontWeight: 600 }}>{trade.strategy_name || trade.strategy_id}</td>
                    <td style={{ fontWeight: 700, fontFamily: 'monospace' }}>{trade.symbol}</td>
                    <td>{trade.option_type || 'EQUITY'}</td>
                    <td>{trade.quantity}</td>
                    <td>₹{trade.entry_price.toFixed(2)}</td>
                    <td style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>{fmtTime(trade.entry_time)}</td>
                    <td>{trade.exit_price ? `₹${trade.exit_price.toFixed(2)}` : '--'}</td>
                    <td style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>{fmtTime(trade.exit_time)}</td>
                    <td style={{ fontWeight: 600 }}>₹{(trade.quantity * trade.entry_price).toFixed(2)}</td>
                    <td style={{ fontWeight: 700 }} className={isGain ? 'glow-green' : 'glow-red'}>
                      {trade.pnl ? `${((trade.pnl / (trade.quantity * trade.entry_price)) * 100).toFixed(2)}%` : '--'}
                    </td>
                    <td style={{ fontWeight: 700 }} className={isGain ? 'glow-green' : 'glow-red'}>
                      {trade.pnl ? `₹${trade.pnl.toFixed(2)}` : '--'}
                    </td>
                    <td>
                      <span
                        style={{
                          padding: '2px 6px',
                          borderRadius: '4px',
                          fontSize: '10px',
                          fontWeight: 600,
                          background: trade.status === 'OPEN' ? 'rgba(245, 158, 11, 0.15)' : 'rgba(255,255,255,0.05)',
                          color: trade.status === 'OPEN' ? 'var(--accent-yellow)' : 'var(--text-secondary)',
                        }}
                      >
                        {trade.status}
                      </span>
                    </td>
                    <td>
                      <span
                        style={{
                          fontSize: '10px',
                          color: trade.mode === 'LIVE' ? 'var(--accent-green)' : '#8B5CF6',
                          fontWeight: 600,
                        }}
                      >
                        {trade.mode}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                        {trade.exit_reason || '--'}
                      </span>
                    </td>
                    <td>
                      {onSendTelegramLedger && (
                        <button
                          onClick={() => onSendTelegramLedger([trade])}
                          className="btn-glass"
                          title="Send individual trade report to Telegram"
                          style={{
                            padding: '4px 8px',
                            color: '#10B981',
                            border: '1px solid rgba(16, 185, 129, 0.2)',
                            borderRadius: '4px',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                          }}
                        >
                          <Send size={12} />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
