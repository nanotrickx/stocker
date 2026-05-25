'use client';

import React from 'react';
import { Bot, Plus, X, CheckCircle, Clock, Target, Shield, Zap, TrendingUp } from 'lucide-react';
import { IndicatorCondition, StrategyType } from '../types';

interface CustomBuilderProps {
  strategyName: string;
  setStrategyName: (val: string) => void;
  strategyType: StrategyType;
  setStrategyType: (val: StrategyType) => void;
  isPaperTrade: boolean;
  setIsPaperTrade: (val: boolean) => void;
  symbolTarget: string;
  setSymbolTarget: (val: string) => void;
  optType: string;
  setOptType: (val: string) => void;
  strikeSel: string;
  setStrikeSel: (val: string) => void;
  quantity: number;
  setQuantity: (val: number) => void;
  slPct: number;
  setSlPct: (val: number) => void;
  targetPct: number;
  setTargetPct: (val: number) => void;
  // ORB-specific
  premiumMin: number;
  setPremiumMin: (val: number) => void;
  premiumMax: number;
  setPremiumMax: (val: number) => void;
  postBreakoutTf: string;
  setPostBreakoutTf: (val: string) => void;
  // Custom indicator rules
  entryConditions: IndicatorCondition[];
  setEntryConditions: React.Dispatch<React.SetStateAction<IndicatorCondition[]>>;
  exitConditions: IndicatorCondition[];
  setExitConditions: React.Dispatch<React.SetStateAction<IndicatorCondition[]>>;
  onDeploy: () => void;
  onCancel: () => void;
}

const GLASS_INPUT: React.CSSProperties = { background:'rgba(0,0,0,0.3)', border:'1px solid rgba(255,255,255,0.08)', borderRadius:'8px', color:'#fff', padding:'10px 12px', fontSize:'13px', outline:'none', width:'100%' };
const LABEL: React.CSSProperties = { fontSize:'11px', color:'var(--text-muted)', fontWeight:600, textTransform:'uppercase' as any, letterSpacing:'.04em' };

export default function CustomBuilder({
  strategyName, setStrategyName,
  strategyType, setStrategyType,
  isPaperTrade, setIsPaperTrade,
  symbolTarget, setSymbolTarget,
  optType, setOptType,
  strikeSel, setStrikeSel,
  quantity, setQuantity,
  slPct, setSlPct,
  targetPct, setTargetPct,
  premiumMin, setPremiumMin,
  premiumMax, setPremiumMax,
  postBreakoutTf, setPostBreakoutTf,
  entryConditions, setEntryConditions,
  exitConditions, setExitConditions,
  onDeploy, onCancel
}: CustomBuilderProps) {

  const addCondition = (type: 'entry' | 'exit') => {
    const defaultNode: IndicatorCondition = { 
      indicator: 'RSI', 
      period: 14, 
      comparison: 'GREATER_THAN', 
      target: 'VALUE', 
      value: 50 
    };
    if (type === 'entry') setEntryConditions([...entryConditions, defaultNode]);
    else setExitConditions([...exitConditions, defaultNode]);
  };

  const removeCondition = (type: 'entry' | 'exit', idx: number) => {
    if (type === 'entry') setEntryConditions(entryConditions.filter((_, i) => i !== idx));
    else setExitConditions(exitConditions.filter((_, i) => i !== idx));
  };

  const updateCondition = (type: 'entry' | 'exit', idx: number, fields: Partial<IndicatorCondition>) => {
    if (type === 'entry') {
      const copy = [...entryConditions];
      copy[idx] = { ...copy[idx], ...fields };
      setEntryConditions(copy);
    } else {
      const copy = [...exitConditions];
      copy[idx] = { ...copy[idx], ...fields };
      setExitConditions(copy);
    }
  };

  return (
    <div className="glass-panel animate-slide-in" style={{ margin: '24px', padding: '30px', maxWidth: '1100px' }}>
      <h2 style={{ fontSize: '20px', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '10px' }}>
        <Bot size={22} className="glow-green" /> Strategy Builder
      </h2>
      <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '24px' }}>
        Design your trading strategy. Choose a built-in template or build custom indicator rules.
      </p>

      {/* ── Strategy Type Selector ── */}
      <div style={{ marginBottom:'24px' }}>
        <label style={LABEL}>Strategy Type</label>
        <div style={{ display:'flex', gap:'10px', marginTop:'8px' }}>
          <button onClick={()=>setStrategyType('orb_breakout')}
            style={{
              flex:1, padding:'14px 16px', borderRadius:'12px', cursor:'pointer',
              background: strategyType==='orb_breakout' ? 'linear-gradient(135deg, #F59E0B22, #F59E0B08)' : 'rgba(255,255,255,0.03)',
              border: strategyType==='orb_breakout' ? '1.5px solid #F59E0B' : '1px solid rgba(255,255,255,0.08)',
              transition:'all .2s ease',
            }}>
            <div style={{ display:'flex', alignItems:'center', gap:'8px', marginBottom:'6px' }}>
              <TrendingUp size={16} style={{ color:'#F59E0B' }} />
              <span style={{ fontSize:'13px', fontWeight:700, color: strategyType==='orb_breakout' ? '#F59E0B' : '#fff' }}>
                🎯 ORB Breakout
              </span>
            </div>
            <p style={{ fontSize:'11px', color:'var(--text-muted)', margin:0, lineHeight:'1.5' }}>
              Opening Range Breakout — 9:15 candle high/low breakout → ATM option → ±10% target/SL. Premium filter 100-200.
            </p>
          </button>

          <button onClick={()=>setStrategyType('custom')}
            style={{
              flex:1, padding:'14px 16px', borderRadius:'12px', cursor:'pointer',
              background: strategyType==='custom' ? 'linear-gradient(135deg, #6366F122, #6366F108)' : 'rgba(255,255,255,0.03)',
              border: strategyType==='custom' ? '1.5px solid #6366F1' : '1px solid rgba(255,255,255,0.08)',
              transition:'all .2s ease',
            }}>
            <div style={{ display:'flex', alignItems:'center', gap:'8px', marginBottom:'6px' }}>
              <Zap size={16} style={{ color:'#6366F1' }} />
              <span style={{ fontSize:'13px', fontWeight:700, color: strategyType==='custom' ? '#6366F1' : '#fff' }}>
                🔧 Custom Rules
              </span>
            </div>
            <p style={{ fontSize:'11px', color:'var(--text-muted)', margin:0, lineHeight:'1.5' }}>
              Build indicator-based entry/exit rules (EMA, RSI, VWAP crossovers) with custom SL/target.
            </p>
          </button>
        </div>
      </div>

      {/* ── Common Fields ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '24px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <label style={LABEL}>Strategy Name</label>
          <input 
            type="text" 
            value={strategyName} 
            onChange={(e) => setStrategyName(e.target.value)} 
            style={GLASS_INPUT} 
          />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <label style={LABEL}>Trading Mode</label>
          <div style={{ display: 'flex', gap: '10px', height: '100%' }}>
            <button 
              type="button"
              onClick={() => setIsPaperTrade(true)} 
              className={isPaperTrade ? 'btn-primary' : 'btn-glass'}
              style={{ flex: 1, borderRadius: '8px', fontSize: '13px' }}
            >
              🛡️ Paper Trade
            </button>
            <button 
              type="button"
              onClick={() => setIsPaperTrade(false)} 
              className={!isPaperTrade ? 'btn-primary' : 'btn-glass'}
              style={{ flex: 1, borderRadius: '8px', fontSize: '13px' }}
            >
              🚀 Live Trading
            </button>
          </div>
        </div>
      </div>

      {/* ── Common: Symbol, Quantity ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '16px', marginBottom: '24px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <label style={LABEL}>Target Symbol</label>
          <select value={symbolTarget} onChange={(e) => setSymbolTarget(e.target.value)} style={GLASS_INPUT}>
            <option value="NSE:NIFTY 50">NIFTY 50 (Index)</option>
            <option value="NSE:NIFTY BANK">BANKNIFTY (Index)</option>
            <option value="NSE:RELIANCE">RELIANCE (Equity)</option>
            <option value="NSE:INFY">INFY (Equity)</option>
            <option value="NSE:TCS">TCS (Equity)</option>
            <option value="NSE:HDFCBANK">HDFCBANK (Equity)</option>
            <option value="NSE:SBIN">SBIN (Equity)</option>
          </select>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <label style={LABEL}>Option Type</label>
          <select value={optType} onChange={(e) => setOptType(e.target.value)} style={GLASS_INPUT}>
            {strategyType === 'orb_breakout' ? (
              <option value="AUTO">Auto (CE/PE by breakout)</option>
            ) : (<>
              <option value="CE">Call Option (CE)</option>
              <option value="PE">Put Option (PE)</option>
            </>)}
          </select>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <label style={LABEL}>Strike Selection</label>
          <select value={strikeSel} onChange={(e) => setStrikeSel(e.target.value)} style={GLASS_INPUT}>
            <option value="ATM">At-The-Money (ATM)</option>
            <option value="ITM">In-The-Money (ITM)</option>
            <option value="OTM">Out-of-The-Money (OTM)</option>
          </select>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <label style={LABEL}>Order Quantity</label>
          <input 
            type="number" 
            value={quantity} 
            onChange={(e) => setQuantity(Number(e.target.value))} 
            style={GLASS_INPUT} 
          />
        </div>
      </div>

      {/* ══════════════════════════════════════════════════════════════
          ORB BREAKOUT CONFIG
          ══════════════════════════════════════════════════════════════ */}
      {strategyType === 'orb_breakout' && (
        <div style={{ background:'rgba(245,158,11,0.04)', border:'1px solid rgba(245,158,11,0.15)', borderRadius:'12px', padding:'20px', marginBottom:'24px' }}>
          <h3 style={{ fontSize:'14px', fontWeight:700, color:'#F59E0B', marginBottom:'16px', display:'flex', alignItems:'center', gap:'8px' }}>
            <Target size={16} /> ORB Breakout Configuration
          </h3>

          {/* Strategy Explanation */}
          <div style={{ background:'rgba(0,0,0,0.2)', borderRadius:'8px', padding:'14px', marginBottom:'16px', fontSize:'12px', color:'var(--text-secondary)', lineHeight:'1.8' }}>
            <strong style={{ color:'#F59E0B' }}>How it works:</strong><br/>
            1. Market opens at <strong style={{ color:'#fff' }}>9:15 AM</strong> — record first 1-min candle HIGH and LOW<br/>
            2. Wait for price to <strong style={{ color:'#10B981' }}>break above HIGH</strong> → buy ATM <strong style={{ color:'#10B981' }}>CE</strong> | 
               break <strong style={{ color:'#EF4444' }}>below LOW</strong> → buy ATM <strong style={{ color:'#EF4444' }}>PE</strong><br/>
            3. Option premium must be ₹{premiumMin}–₹{premiumMax}. If ATM exceeds, shift to OTM<br/>
            4. <strong style={{ color:'#10B981' }}>Target: +{targetPct}%</strong> | <strong style={{ color:'#EF4444' }}>SL: -{slPct}%</strong> from entry premium<br/>
            5. After <strong style={{ color:'#fff' }}>10:30</strong> → switch to <strong style={{ color:'#fff' }}>{postBreakoutTf}</strong> candles for monitoring
          </div>

          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr 1fr', gap:'14px' }}>
            {/* Premium Range */}
            <div style={{ display:'flex', flexDirection:'column', gap:'6px' }}>
              <label style={LABEL}>Min Premium (₹)</label>
              <input type="number" value={premiumMin} onChange={e=>setPremiumMin(Number(e.target.value))} 
                style={{ ...GLASS_INPUT, borderLeft:'3px solid #F59E0B' }} />
            </div>
            <div style={{ display:'flex', flexDirection:'column', gap:'6px' }}>
              <label style={LABEL}>Max Premium (₹)</label>
              <input type="number" value={premiumMax} onChange={e=>setPremiumMax(Number(e.target.value))}
                style={{ ...GLASS_INPUT, borderLeft:'3px solid #F59E0B' }} />
            </div>
            {/* Target / SL */}
            <div style={{ display:'flex', flexDirection:'column', gap:'6px' }}>
              <label style={{ ...LABEL, color:'#10B981' }}>🎯 Target %</label>
              <input type="number" step="0.5" value={targetPct} onChange={e=>setTargetPct(Number(e.target.value))}
                style={{ ...GLASS_INPUT, borderLeft:'3px solid #10B981' }} />
            </div>
            <div style={{ display:'flex', flexDirection:'column', gap:'6px' }}>
              <label style={{ ...LABEL, color:'#EF4444' }}>🔻 Stop Loss %</label>
              <input type="number" step="0.5" value={slPct} onChange={e=>setSlPct(Number(e.target.value))}
                style={{ ...GLASS_INPUT, borderLeft:'3px solid #EF4444' }} />
            </div>
          </div>

          {/* Timeframe */}
          <div style={{ marginTop:'14px' }}>
            <label style={LABEL}>Post 10:30 Candle Interval</label>
            <div style={{ display:'flex', gap:'6px', marginTop:'6px' }}>
              {[
                { v:'3minute', l:'3 min' },
                { v:'5minute', l:'5 min' },
                { v:'15minute', l:'15 min' },
              ].map(tf => (
                <button key={tf.v} onClick={()=>setPostBreakoutTf(tf.v)}
                  style={{
                    padding:'6px 14px', borderRadius:'16px', fontSize:'12px', fontWeight:600, border:'none', cursor:'pointer',
                    background: postBreakoutTf === tf.v ? '#F59E0B' : 'rgba(255,255,255,0.06)',
                    color: postBreakoutTf === tf.v ? '#000' : 'var(--text-secondary)',
                    transition:'all .15s ease',
                  }}>
                  {tf.l}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════
          CUSTOM INDICATOR RULES
          ══════════════════════════════════════════════════════════════ */}
      {strategyType === 'custom' && (<>
        {/* Entry Conditions logic */}
        <div style={{ marginBottom: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <h3 style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>📈 ENTRY LOGIC RULES (All Must Match)</h3>
            <button type="button" onClick={() => addCondition('entry')} className="btn-glass" style={{ padding: '6px 12px', fontSize: '11px', borderRadius: '6px', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Plus size={12} /> Add Condition
            </button>
          </div>
          
          {entryConditions.map((cond, idx) => (
            <div key={idx} className="strategy-node-row">
              <select value={cond.indicator} onChange={(e) => updateCondition('entry', idx, { indicator: e.target.value })} className="input-glass" style={{ background: '#0D121D', padding: '6px 10px', height: '32px', fontSize: '12px' }}>
                <option value="EMA">EMA</option>
                <option value="RSI">RSI</option>
                <option value="VWAP">VWAP</option>
                <option value="LTP">LTP Spot</option>
              </select>
              
              {cond.indicator !== 'VWAP' && cond.indicator !== 'LTP' && (
                <input 
                  type="number" 
                  placeholder="Period"
                  value={cond.period || ''}
                  onChange={(e) => updateCondition('entry', idx, { period: Number(e.target.value) })}
                  className="input-glass" 
                  style={{ width: '80px', padding: '6px 10px', height: '32px', fontSize: '12px' }}
                />
              )}

              <select value={cond.comparison} onChange={(e) => updateCondition('entry', idx, { comparison: e.target.value })} className="input-glass" style={{ background: '#0D121D', padding: '6px 10px', height: '32px', fontSize: '12px' }}>
                <option value="CROSS_ABOVE">Crosses Above</option>
                <option value="CROSS_BELOW">Crosses Below</option>
                <option value="GREATER_THAN">Greater Than</option>
                <option value="LESS_THAN">Less Than</option>
              </select>

              <select value={cond.target} onChange={(e) => updateCondition('entry', idx, { target: e.target.value })} className="input-glass" style={{ background: '#0D121D', padding: '6px 10px', height: '32px', fontSize: '12px' }}>
                <option value="INDICATOR">Indicator</option>
                <option value="VALUE">Static Value</option>
              </select>

              {cond.target === 'VALUE' ? (
                <input 
                  type="number" 
                  placeholder="Value"
                  value={cond.value || ''}
                  onChange={(e) => updateCondition('entry', idx, { value: Number(e.target.value) })}
                  className="input-glass" 
                  style={{ width: '80px', padding: '6px 10px', height: '32px', fontSize: '12px' }}
                />
              ) : (
                <>
                  <select value={cond.target_indicator || 'EMA'} onChange={(e) => updateCondition('entry', idx, { target_indicator: e.target.value })} className="input-glass" style={{ background: '#0D121D', padding: '6px 10px', height: '32px', fontSize: '12px' }}>
                    <option value="EMA">EMA</option>
                    <option value="RSI">RSI</option>
                    <option value="VWAP">VWAP</option>
                    <option value="LTP">LTP Spot</option>
                  </select>
                  {cond.target_indicator !== 'VWAP' && cond.target_indicator !== 'LTP' && (
                    <input 
                      type="number" 
                      placeholder="Period"
                      value={cond.target_period || ''}
                      onChange={(e) => updateCondition('entry', idx, { target_period: Number(e.target.value) })}
                      className="input-glass" 
                      style={{ width: '80px', padding: '6px 10px', height: '32px', fontSize: '12px' }}
                    />
                  )}
                </>
              )}

              <button type="button" onClick={() => removeCondition('entry', idx)} style={{ background: 'transparent', color: 'var(--text-muted)', marginLeft: 'auto', cursor: 'pointer' }} className="hover-red">
                <X size={14} />
              </button>
            </div>
          ))}
        </div>

        {/* Exit logic builder */}
        <div style={{ marginBottom: '30px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <h3 style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>📉 EXIT LOGIC RULES (Any One Matches)</h3>
            <button type="button" onClick={() => addCondition('exit')} className="btn-glass" style={{ padding: '6px 12px', fontSize: '11px', borderRadius: '6px', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Plus size={12} /> Add Condition
            </button>
          </div>

          {exitConditions.map((cond, idx) => (
            <div key={idx} className="strategy-node-row">
              <select value={cond.indicator} onChange={(e) => updateCondition('exit', idx, { indicator: e.target.value })} className="input-glass" style={{ background: '#0D121D', padding: '6px 10px', height: '32px', fontSize: '12px' }}>
                <option value="EMA">EMA</option>
                <option value="RSI">RSI</option>
                <option value="VWAP">VWAP</option>
                <option value="LTP">LTP Spot</option>
              </select>

              {cond.indicator !== 'VWAP' && cond.indicator !== 'LTP' && (
                <input 
                  type="number" 
                  placeholder="Period"
                  value={cond.period || ''}
                  onChange={(e) => updateCondition('exit', idx, { period: Number(e.target.value) })}
                  className="input-glass" 
                  style={{ width: '80px', padding: '6px 10px', height: '32px', fontSize: '12px' }}
                />
              )}

              <select value={cond.comparison} onChange={(e) => updateCondition('exit', idx, { comparison: e.target.value })} className="input-glass" style={{ background: '#0D121D', padding: '6px 10px', height: '32px', fontSize: '12px' }}>
                <option value="CROSS_ABOVE">Crosses Above</option>
                <option value="CROSS_BELOW">Crosses Below</option>
                <option value="GREATER_THAN">Greater Than</option>
                <option value="LESS_THAN">Less Than</option>
              </select>

              <select value={cond.target} onChange={(e) => updateCondition('exit', idx, { target: e.target.value })} className="input-glass" style={{ background: '#0D121D', padding: '6px 10px', height: '32px', fontSize: '12px' }}>
                <option value="INDICATOR">Indicator</option>
                <option value="VALUE">Static Value</option>
              </select>

              {cond.target === 'VALUE' ? (
                <input 
                  type="number" 
                  placeholder="Value"
                  value={cond.value || ''}
                  onChange={(e) => updateCondition('exit', idx, { value: Number(e.target.value) })}
                  className="input-glass" 
                  style={{ width: '80px', padding: '6px 10px', height: '32px', fontSize: '12px' }}
                />
              ) : (
                <>
                  <select value={cond.target_indicator || 'EMA'} onChange={(e) => updateCondition('exit', idx, { target_indicator: e.target.value })} className="input-glass" style={{ background: '#0D121D', padding: '6px 10px', height: '32px', fontSize: '12px' }}>
                    <option value="EMA">EMA</option>
                    <option value="RSI">RSI</option>
                    <option value="VWAP">VWAP</option>
                    <option value="LTP">LTP Spot</option>
                  </select>
                  {cond.target_indicator !== 'VWAP' && cond.target_indicator !== 'LTP' && (
                    <input 
                      type="number" 
                      placeholder="Period"
                      value={cond.target_period || ''}
                      onChange={(e) => updateCondition('exit', idx, { target_period: Number(e.target.value) })}
                      className="input-glass" 
                      style={{ width: '80px', padding: '6px 10px', height: '32px', fontSize: '12px' }}
                    />
                  )}
                </>
              )}

              <button type="button" onClick={() => removeCondition('exit', idx)} style={{ background: 'transparent', color: 'var(--text-muted)', marginLeft: 'auto', cursor: 'pointer' }} className="hover-red">
                <X size={14} />
              </button>
            </div>
          ))}

          {/* Stop Loss & Target Parameters */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginTop: '16px', background: 'rgba(255,255,255,0.01)', border: '1px dashed var(--border-glass)', borderRadius: '10px', padding: '16px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '12px', color: 'var(--accent-red)', fontWeight: 600 }}>🔻 Hard Stop Loss Percentage (%)</label>
              <input 
                type="number" 
                step="0.1"
                value={slPct}
                onChange={(e) => setSlPct(Number(e.target.value))}
                className="input-glass" 
                style={{ borderLeft: '3px solid var(--accent-red)' }}
              />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '12px', color: 'var(--accent-green)', fontWeight: 600 }}>🟩 Hard Target Percentage (%)</label>
              <input 
                type="number" 
                step="0.1"
                value={targetPct}
                onChange={(e) => setTargetPct(Number(e.target.value))}
                className="input-glass" 
                style={{ borderLeft: '3px solid var(--accent-green)' }}
              />
            </div>
          </div>
        </div>
      </>)}

      {/* Action Buttons */}
      <div style={{ display: 'flex', gap: '12px', borderTop: '1px solid var(--border-glass)', paddingTop: '20px' }}>
        <button type="button" onClick={onDeploy} className="btn-primary" style={{ padding: '12px 24px', borderRadius: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <CheckCircle size={16} /> Deploy & Activate Strategy
        </button>
        <button type="button" onClick={onCancel} className="btn-glass" style={{ padding: '12px 20px', borderRadius: '8px' }}>
          Cancel
        </button>
      </div>
    </div>
  );
}
