'use client';

import React from 'react';
import { TrendingUp } from 'lucide-react';
import { OptionChainItem } from '../types';

interface OptionChainProps {
  spotPrice: number;
  optionChain: OptionChainItem[];
  onStrikeSelect: (type: 'CE' | 'PE', strikeSelection: string) => void;
}

export default function OptionChain({ spotPrice, optionChain, onStrikeSelect }: OptionChainProps) {
  return (
    <div className="glass-panel" style={{ padding: '20px', overflow: 'hidden' }}>
      <h3 style={{ fontSize: '16px', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
        <TrendingUp size={16} className="glow-green" /> Real-time Option Chain (Delta / Theta / Greeks)
      </h3>
      
      <div style={{ overflowX: 'auto' }}>
        <table className="options-table">
          <thead>
            <tr>
              <th colSpan={4} style={{ background: 'rgba(16, 185, 129, 0.05)', color: 'var(--accent-green)', borderRight: '1px solid var(--border-glass)' }}>CALL OPTIONS (CE)</th>
              <th style={{ background: 'rgba(255, 255, 255, 0.03)' }}>STRIKE</th>
              <th colSpan={4} style={{ background: 'rgba(244, 63, 94, 0.05)', color: 'var(--accent-red)', borderLeft: '1px solid var(--border-glass)' }}>PUT OPTIONS (PE)</th>
            </tr>
            <tr>
              <th style={{ background: 'rgba(16, 185, 129, 0.02)' }}>LTP</th>
              <th style={{ background: 'rgba(16, 185, 129, 0.02)' }}>Delta</th>
              <th style={{ background: 'rgba(16, 185, 129, 0.02)' }}>Theta</th>
              <th style={{ background: 'rgba(16, 185, 129, 0.02)', borderRight: '1px solid var(--border-glass)' }}>Vega</th>
              <th style={{ background: 'rgba(255, 255, 255, 0.05)', fontWeight: 700 }}>Index Strike</th>
              <th style={{ background: 'rgba(244, 63, 94, 0.02)', borderLeft: '1px solid var(--border-glass)' }}>LTP</th>
              <th style={{ background: 'rgba(244, 63, 94, 0.02)' }}>Delta</th>
              <th style={{ background: 'rgba(244, 63, 94, 0.02)' }}>Theta</th>
              <th style={{ background: 'rgba(244, 63, 94, 0.02)' }}>Vega</th>
            </tr>
          </thead>
          <tbody>
            {optionChain.map((item, idx) => {
              const isAtm = Math.abs(spotPrice - item.strike) < 50;
              const isCallItm = item.strike < spotPrice;
              const isPutItm = item.strike > spotPrice;
              const callClass = isCallItm ? 'itm-call' : '';
              const putClass = isPutItm ? 'itm-put' : '';
              
              return (
                <tr key={idx} style={{ 
                  background: isAtm ? 'rgba(99, 102, 241, 0.04)' : 'transparent',
                  borderBottom: '1px solid rgba(255, 255, 255, 0.02)'
                }}>
                  {/* CE Side */}
                  <td 
                    className={callClass}
                    onClick={() => {
                      const strikeType = isAtm ? 'ATM' : (isCallItm ? 'ITM' : 'OTM');
                      onStrikeSelect('CE', strikeType);
                    }} 
                    style={{ color: 'var(--accent-green)', fontWeight: 700, cursor: 'pointer', verticalAlign: 'middle' }}
                    title="Click to select this strike in custom builder"
                  >
                    ₹{item.ce.price.toFixed(2)}
                  </td>
                  <td className={callClass} style={{ verticalAlign: 'middle', color: isCallItm ? 'rgba(255,255,255,0.85)' : 'var(--text-secondary)' }}>
                    {item.ce.delta.toFixed(2)}
                  </td>
                  <td className={callClass} style={{ verticalAlign: 'middle', color: isCallItm ? 'rgba(255,255,255,0.85)' : 'var(--text-secondary)' }}>
                    {item.ce.theta.toFixed(2)}
                  </td>
                  <td className={callClass} style={{ borderRight: '1px solid var(--border-glass)', verticalAlign: 'middle', color: isCallItm ? 'rgba(255,255,255,0.85)' : 'var(--text-secondary)' }}>
                    {item.ce.vega.toFixed(2)}
                  </td>
                  
                  {/* Strike Price Capsule */}
                  <td style={{ verticalAlign: 'middle', background: 'rgba(255, 255, 255, 0.01)', padding: '6px' }}>
                    <span className={`strike-badge ${isAtm ? 'atm' : ''}`}>
                      {item.strike} {isAtm && '⭐'}
                    </span>
                  </td>
                  
                  {/* PE Side */}
                  <td 
                    className={putClass}
                    onClick={() => {
                      const strikeType = isAtm ? 'ATM' : (isPutItm ? 'ITM' : 'OTM');
                      onStrikeSelect('PE', strikeType);
                    }} 
                    style={{ color: 'var(--accent-red)', fontWeight: 700, cursor: 'pointer', borderLeft: '1px solid var(--border-glass)', verticalAlign: 'middle' }}
                    title="Click to select this strike in custom builder"
                  >
                    ₹{item.pe.price.toFixed(2)}
                  </td>
                  <td className={putClass} style={{ verticalAlign: 'middle', color: isPutItm ? 'rgba(255,255,255,0.85)' : 'var(--text-secondary)' }}>
                    {item.pe.delta.toFixed(2)}
                  </td>
                  <td className={putClass} style={{ verticalAlign: 'middle', color: isPutItm ? 'rgba(255,255,255,0.85)' : 'var(--text-secondary)' }}>
                    {item.pe.theta.toFixed(2)}
                  </td>
                  <td className={putClass} style={{ verticalAlign: 'middle', color: isPutItm ? 'rgba(255,255,255,0.85)' : 'var(--text-secondary)' }}>
                    {item.pe.vega.toFixed(2)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
