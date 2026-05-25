'use client';

import React from 'react';
import { Zap, ShieldAlert, XCircle } from 'lucide-react';
import { Trade } from '../types';

interface ActivePositionsProps {
  positions: Trade[];
  onForceExit: (tradeId: number) => void;
}

export default function ActivePositions({ positions, onForceExit }: ActivePositionsProps) {
  return (
    <div className="glass-panel" style={{ padding: '20px' }}>
      <h3 style={{ fontSize: '16px', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
        <Zap size={16} style={{ color: 'var(--accent-yellow)' }} /> Active Positions
      </h3>
      
      {positions.length === 0 ? (
        <div style={{ padding: '30px 10px', textAlign: 'center', color: 'var(--text-muted)' }}>
          <ShieldAlert size={36} style={{ margin: '0 auto 12px auto', display: 'block', opacity: 0.5 }} />
          <p style={{ fontSize: '13px' }}>No active options or equity positions are currently monitoring.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {positions.map((pos) => {
            return (
              <div key={pos.id} className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <span style={{ fontSize: '11px', background: pos.option_type === 'CE' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(244, 63, 94, 0.15)', color: pos.option_type === 'CE' ? 'var(--accent-green)' : 'var(--accent-red)', padding: '2px 6px', borderRadius: '4px', fontWeight: 700, marginRight: '6px' }}>
                      {pos.option_type || 'EQ'}
                    </span>
                    <strong style={{ fontSize: '14px', fontFamily: 'var(--font-display)' }}>{pos.symbol}</strong>
                  </div>
                  
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ 
                      fontSize: '10px', 
                      background: pos.mode === 'PAPER' ? 'rgba(99, 102, 241, 0.15)' : 'rgba(16, 185, 129, 0.15)', 
                      padding: '2px 6px', 
                      borderRadius: '4px', 
                      color: pos.mode === 'PAPER' ? '#8B5CF6' : 'var(--accent-green)',
                      fontWeight: 700 
                    }}>
                      {pos.mode}
                    </span>
                    
                    <button 
                      onClick={() => onForceExit(pos.id)} 
                      title="Force Exit Position" 
                      className="hover-red" 
                      style={{ 
                        background: 'transparent', 
                        border: 'none', 
                        color: 'var(--accent-red)', 
                        display: 'flex', 
                        alignItems: 'center',
                        cursor: 'pointer'
                      }}
                    >
                      <XCircle size={16} />
                    </button>
                  </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginTop: '4px', color: 'var(--text-secondary)' }}>
                  <span>Qty: <b>{pos.quantity}</b></span>
                  <span>Avg Entry: <b>₹{pos.entry_price.toFixed(2)}</b></span>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '10px', borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: '10px' }}>
                  <div>
                    <p style={{ fontSize: '9px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Strategy Engine</p>
                    <p style={{ fontSize: '11px', color: '#8B5CF6', fontWeight: 700 }}>{pos.strategy_id}</p>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <p style={{ fontSize: '9px', color: 'var(--text-muted)' }}>Unrealized P&L</p>
                    <strong style={{ fontSize: '15px' }} className={(pos.pnl || 0) >= 0 ? 'glow-green' : 'glow-red'}>
                      ₹{(pos.pnl || 0.0).toFixed(2)}
                    </strong>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
