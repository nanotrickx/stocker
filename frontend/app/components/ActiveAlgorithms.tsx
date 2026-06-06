'use client';

import React from 'react';
import { Bot, Plus, Trash2, Shield, Zap, HelpCircle, Power, Sliders, ExternalLink, Send, Terminal, X, TrendingUp } from 'lucide-react';
import { Strategy, StrategyInstance } from '../types';

interface ActiveAlgorithmsProps {
  templates: Strategy[];
  instances: StrategyInstance[];
  onActivateClick: (strategy: Strategy) => void;
  onToggleInstance: (id: number, active: boolean) => void;
  onDeleteInstance: (id: number) => void;
  onCreateNewClick: () => void;
  onDeleteTemplate: (id: string) => void;
  onSendTelegramStatus?: (id: number) => void;
  strategyLogs?: any[];
  hideBlueprints?: boolean;
}

export default function ActiveAlgorithms({
  templates,
  instances,
  onActivateClick,
  onToggleInstance,
  onDeleteInstance,
  onCreateNewClick,
  onDeleteTemplate,
  onSendTelegramStatus,
  strategyLogs = [],
  hideBlueprints = false,
}: ActiveAlgorithmsProps) {

  const [selectedInstance, setSelectedInstance] = React.useState<StrategyInstance | null>(null);
  const [optionChain, setOptionChain] = React.useState<any>(null);
  const [loadingChain, setLoadingChain] = React.useState(false);
  const [errorChain, setErrorChain] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!selectedInstance) {
      setOptionChain(null);
      return;
    }

    const fetchOptionChain = async () => {
      try {
        const res = await fetch(`http://127.0.0.1:8000/api/strategy-instances/${selectedInstance.id}/option-chain`);
        if (!res.ok) throw new Error('Failed to fetch option chain');
        const data = await res.json();
        setOptionChain(data);
        setErrorChain(null);
      } catch (err: any) {
        setErrorChain(err.message || 'Error fetching option chain');
      }
    };

    setLoadingChain(true);
    fetchOptionChain().finally(() => setLoadingChain(false));

    const interval = setInterval(fetchOptionChain, 3000);
    return () => clearInterval(interval);
  }, [selectedInstance]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '28px', margin: hideBlueprints ? '0' : '24px' }}>
      
      {/* ──────────────────────────────────────────────────────── */}
      {/* SECTION 1: STRATEGY BLUEPRINT LIBRARY */}
      {/* ──────────────────────────────────────────────────────── */}
      {!hideBlueprints && (
        <div className="glass-panel animate-slide-in" style={{ padding: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <div>
            <h2 style={{ fontSize: '18px', display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700 }}>
              <Bot size={22} style={{ color: '#8B5CF6' }} className="glow-indigo" /> Algorithmic Blueprints
            </h2>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Core mathematical strategy models. Click "Activate" to deploy an instance on any asset.
            </p>
          </div>

          <button 
            onClick={onCreateNewClick} 
            className="btn-primary" 
            style={{ padding: '8px 16px', borderRadius: '8px', display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px' }}
          >
            <Plus size={15} /> Create Custom Blueprint
          </button>
        </div>

        {templates.length === 0 ? (
          <div style={{ padding: '40px 0', textAlign: 'center', border: '1px dashed var(--border-glass)', borderRadius: '12px' }}>
            <HelpCircle size={40} style={{ margin: '0 auto 12px auto', display: 'block', opacity: 0.3 }} />
            <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>No blueprints saved. Click "Create" to build one!</p>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '20px' }}>
            {templates.map((tmpl) => {
              const sType = tmpl.strategy_type || 'custom';
              const isOrb = sType === 'orb_breakout';
              return (
                <div 
                  key={tmpl.id} 
                  className="glass-card" 
                  style={{ 
                    display: 'flex', 
                    flexDirection: 'column', 
                    gap: '12px', 
                    background: 'var(--sub-panel-bg)', 
                    border: '1px solid var(--border-glass)',
                    borderLeft: isOrb ? '3px solid #F59E0B' : '3px solid #6366F1',
                    paddingLeft: '18px'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <h3 style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-primary)' }}>{tmpl.name}</h3>
                      <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>ID: {tmpl.id}</span>
                    </div>

                    <span style={{ 
                      fontSize: '10px', 
                      background: sType === 'orb_breakout' ? 'rgba(245,158,11,0.15)' : 'rgba(99,102,241,0.15)', 
                      color: sType === 'orb_breakout' ? '#F59E0B' : '#6366F1',
                      padding: '2px 8px',
                      borderRadius: '12px',
                      fontWeight: 700,
                    }}>
                      {sType === 'orb_breakout' ? '🎯 ORB Breakout' : '🔧 Custom'}
                    </span>
                  </div>

                  <p style={{ fontSize: '12px', color: 'var(--text-muted)', lineHeight: '1.4', flexGrow: 1 }}>
                    {tmpl.description || 'Custom mathematical logic rule set.'}
                  </p>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '10px', borderTop: '1px solid var(--border-glass-subtle)' }}>
                    {tmpl.id !== 'orb_breakout' ? (
                      <button 
                        onClick={() => onDeleteTemplate(tmpl.id)} 
                        style={{ background: 'none', border: 'none', color: 'rgba(239, 68, 68, 0.6)', cursor: 'pointer', display: 'flex', alignItems: 'center' }}
                        className="hover-red"
                      >
                        <Trash2 size={14} />
                      </button>
                    ) : <div />}

                    <button 
                      onClick={() => onActivateClick(tmpl)} 
                      className="btn-glass hover-blue"
                      style={{ padding: '6px 14px', borderRadius: '6px', fontSize: '12px', color: '#8B5CF6', border: '1px solid rgba(139,92,246,0.3)', display: 'flex', alignItems: 'center', gap: '4px' }}
                    >
                      <Power size={12} /> Activate
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
      )}

      {/* ──────────────────────────────────────────────────────── */}
      {/* SECTION 2: RUNNING DEPLOYMENTS / INSTANCES */}
      {/* ──────────────────────────────────────────────────────── */}
      <div className="glass-panel animate-slide-in" style={{ padding: '24px' }}>
        <div>
          <h2 style={{ fontSize: '18px', display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700 }}>
            <Sliders size={20} style={{ color: 'var(--accent-green)' }} /> Running Strategy Deployments
          </h2>
          <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '20px' }}>
            Active strategy engine instances running on live/simulated market data streams.
          </p>
        </div>

        {instances.length === 0 ? (
          <div style={{ padding: '50px 0', textAlign: 'center', border: '1px dashed var(--border-glass)', borderRadius: '12px' }}>
            <HelpCircle size={44} style={{ margin: '0 auto 12px auto', display: 'block', opacity: 0.2 }} />
            <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>No strategies are currently running.</p>
            <p style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '4px' }}>Click "Activate" on a blueprint card above to deploy your first trading loop.</p>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'left' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--text-muted)' }}>
                  <th style={{ padding: '12px 16px' }}>Instance Name</th>
                  <th style={{ padding: '12px 16px' }}>Asset Symbol</th>
                  <th style={{ padding: '12px 16px' }}>Risk Parameters</th>
                  <th style={{ padding: '12px 16px' }}>Qty / Lot</th>
                  <th style={{ padding: '12px 16px' }}>Execution Mode</th>
                  <th style={{ padding: '12px 16px' }}>Engine Status</th>
                  <th style={{ padding: '12px 16px', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {instances.map((inst) => {
                  const sl = inst.config?.risk?.stop_loss_pct || 10.0;
                  const target = inst.config?.risk?.target_pct || 10.0;
                  const qty = inst.config?.action?.quantity || 50;

                  return (
                    <tr 
                      key={inst.id} 
                      style={{ 
                        borderBottom: '1px solid var(--border-glass-subtle)', 
                        background: inst.active ? 'rgba(16, 185, 129, 0.02)' : 'transparent',
                        transition: 'background 0.2s' 
                      }}
                    >
                      {/* Name */}
                      <td style={{ padding: '16px', fontWeight: 600, color: 'var(--text-primary)' }}>
                        {inst.name}
                      </td>

                      {/* Symbol */}
                      <td style={{ padding: '16px' }}>
                        <span style={{ fontFamily: 'monospace', background: 'var(--glass-bg-accent)', padding: '4px 8px', borderRadius: '4px', border: '1px solid var(--border-glass-subtle)' }}>
                          {inst.symbol}
                        </span>
                      </td>

                      {/* SL / Target */}
                      <td style={{ padding: '16px', color: 'var(--accent-yellow)', fontWeight: 600 }}>
                        🔻{sl}% / 🟩{target}%
                      </td>

                      {/* Qty */}
                      <td style={{ padding: '16px', color: 'var(--text-primary)' }}>
                        {qty}
                      </td>

                      {/* Mode */}
                      <td style={{ padding: '16px' }}>
                        <span style={{ 
                          fontSize: '11px', 
                          background: inst.paper_trade ? 'rgba(99, 102, 241, 0.12)' : 'rgba(16, 185, 129, 0.12)', 
                          color: inst.paper_trade ? '#8B5CF6' : 'var(--accent-green)',
                          padding: '3px 8px',
                          borderRadius: '12px',
                          fontWeight: 700,
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px'
                        }}>
                          {inst.paper_trade ? <Shield size={10} /> : <Zap size={10} />}
                          {inst.paper_trade ? 'SANDBOX' : 'LIVE'}
                        </span>
                      </td>

                      {/* Status switch */}
                      <td style={{ padding: '16px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <label className="switch" style={{ position: 'relative', display: 'inline-block', width: '38px', height: '20px' }}>
                            <input 
                              type="checkbox" 
                              checked={inst.active} 
                              onChange={(e) => onToggleInstance(inst.id, e.target.checked)}
                              style={{ opacity: 0, width: 0, height: 0 }}
                            />
                            <span style={{
                              position: 'absolute', cursor: 'pointer', top: 0, left: 0, right: 0, bottom: 0,
                              background: inst.active ? 'var(--accent-green)' : 'rgba(255, 255, 255, 0.1)',
                              borderRadius: '34px', transition: '0.3s'
                            }}>
                              <span style={{
                                position: 'absolute', content: '""', height: '14px', width: '14px', left: inst.active ? '20px' : '3px', bottom: '3px',
                                background: '#fff', borderRadius: '50%', transition: '0.3s'
                              }} />
                            </span>
                          </label>
                          <span style={{ fontSize: '11px', fontWeight: 600, color: inst.active ? 'var(--accent-green)' : 'var(--text-muted)' }}>
                            {inst.active ? 'RUNNING' : 'PAUSED'}
                          </span>
                        </div>
                      </td>

                      {/* Delete */}
                      <td style={{ padding: '16px', textAlign: 'right' }}>
                        <button 
                          onClick={() => setSelectedInstance(inst)} 
                          style={{ 
                            background: 'rgba(139, 92, 246, 0.08)', 
                            border: '1px solid rgba(139, 92, 246, 0.15)', 
                            color: '#a78bfa', 
                            padding: '6px 10px', 
                            borderRadius: '6px',
                            cursor: 'pointer',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                            marginRight: '8px',
                            fontSize: '11px',
                            fontWeight: 600
                          }}
                          className="hover-purple"
                          title="Show Real-time Strategy Logs and Live Option Chain"
                        >
                          <Terminal size={11} /> Show Logs
                        </button>
                        {onSendTelegramStatus && (
                          <button 
                            onClick={() => onSendTelegramStatus(inst.id)} 
                            style={{ 
                              background: 'rgba(59, 130, 246, 0.08)', 
                              border: '1px solid rgba(59, 130, 246, 0.15)', 
                              color: '#3B82F6', 
                              padding: '6px 10px', 
                              borderRadius: '6px',
                              cursor: 'pointer',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '4px',
                              marginRight: '8px',
                              fontSize: '11px',
                              fontWeight: 600
                            }}
                            className="hover-blue"
                            title="Send current strategy status report to Telegram Bot"
                          >
                            <Send size={11} /> Status
                          </button>
                        )}
                        <button 
                          onClick={() => onDeleteInstance(inst.id)} 
                          style={{ 
                            background: 'rgba(239, 68, 68, 0.08)', 
                            border: '1px solid rgba(239, 68, 68, 0.15)', 
                            color: 'rgba(239, 68, 68, 0.8)', 
                            padding: '6px', 
                            borderRadius: '6px',
                            cursor: 'pointer',
                            display: 'inline-flex',
                            alignItems: 'center'
                          }}
                          className="hover-red"
                        >
                          <Trash2 size={13} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ──────────────────────────────────────────────────────── */}
      {/* STRATEGY LOGS & OPTION CHAIN MODAL */}
      {/* ──────────────────────────────────────────────────────── */}
      {selectedInstance && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0, 0, 0, 0.75)', backdropFilter: 'blur(8px)',
          display: 'flex', justifyContent: 'center', alignItems: 'center',
          zIndex: 9999, padding: '20px'
        }}>
          <div className="glass-panel animate-slide-in" style={{
            width: '100%', maxWidth: '1050px', background: 'var(--panel-glass)',
            border: '1px solid var(--border-glass)', borderRadius: '16px',
            padding: '24px', boxShadow: 'var(--shadow-premium)',
            maxHeight: '90vh', display: 'flex', flexDirection: 'column', gap: '20px'
          }}>
            {/* Modal Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid var(--border-glass)', paddingBottom: '16px' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <h3 style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-primary)' }}>
                    {selectedInstance.name}
                  </h3>
                  <span style={{
                    fontSize: '11px',
                    background: selectedInstance.paper_trade ? 'rgba(99, 102, 241, 0.15)' : 'rgba(16, 185, 129, 0.15)',
                    color: selectedInstance.paper_trade ? '#a78bfa' : 'var(--accent-green)',
                    padding: '2px 8px', borderRadius: '12px', fontWeight: 700
                  }}>
                    {selectedInstance.paper_trade ? 'SANDBOX EXECUTION' : 'LIVE TRADING'}
                  </span>
                </div>
                <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
                  Live engine details, indicators, and real-time exchange options pricing.
                </p>
              </div>

              <button 
                onClick={() => setSelectedInstance(null)}
                style={{ background: 'var(--glass-bg-subtle)', border: '1px solid var(--border-glass)', color: 'var(--text-primary)', borderRadius: '50%', padding: '6px', cursor: 'pointer', display: 'flex', alignItems: 'center' }}
                className="hover-red"
              >
                <X size={18} />
              </button>
            </div>

            {/* Modal Body */}
            <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', minHeight: 0, overflowY: 'auto' }}>
              {/* Left Column: Live Strategy Logs */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', minHeight: 0 }}>
                <h4 style={{ fontSize: '13px', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600 }}>
                  <Terminal size={14} style={{ color: '#8B5CF6' }} /> Strategy Evaluation Console Logs
                </h4>
                
                <div style={{
                  flex: 1, background: 'rgba(0, 0, 0, 0.4)', borderRadius: '8px', padding: '16px',
                  fontFamily: 'monospace', fontSize: '11px', color: '#10B981', overflowY: 'auto',
                  border: '1px solid rgba(255,255,255,0.03)', display: 'flex', flexDirection: 'column', gap: '4px',
                  minHeight: '250px'
                }}>
                  {(() => {
                    const filteredLogs = (strategyLogs || []).filter(log => log.strategy_id === selectedInstance.id);
                    if (filteredLogs.length === 0) {
                      return (
                        <div style={{ display: 'flex', flex: 1, justifyContent: 'center', alignItems: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
                          No active logs streamed for this instance yet. Waiting for engine tick...
                        </div>
                      );
                    }
                    return filteredLogs.slice().reverse().map((log, index) => {
                      let color = '#F3F4F6';
                      if (log.message.includes('[TRIGGER]')) color = '#10B981';
                      else if (log.message.includes('[EVAL]')) color = '#F59E0B';
                      else if (log.message.includes('[SYSTEM]')) color = '#a78bfa';
                      else if (log.message.includes('[TICK]')) color = '#6B7280';
                      
                      return (
                        <p key={index} style={{ color, margin: 0, lineHeight: '1.5' }}>
                          <span style={{ color: '#8B5CF6', marginRight: '6px' }}>[{log.timestamp}]</span>
                          {log.message}
                        </p>
                      );
                    });
                  })()}
                </div>
              </div>

              {/* Right Column: Live Option Chain */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', minHeight: 0 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h4 style={{ fontSize: '13px', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600 }}>
                    <TrendingUp size={14} style={{ color: 'var(--accent-green)' }} /> Live Option Chain Board
                  </h4>
                  {optionChain && (
                    <span style={{
                      fontSize: '10px',
                      background: optionChain.broker === 'KITE' ? 'rgba(16, 185, 129, 0.15)' : optionChain.broker === 'OFFLINE' ? 'rgba(239, 68, 68, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                      color: optionChain.broker === 'KITE' ? 'var(--accent-green)' : optionChain.broker === 'OFFLINE' ? 'var(--accent-red)' : '#F59E0B',
                      padding: '2px 8px', borderRadius: '10px', fontWeight: 700
                    }}>
                      🔌 {optionChain.broker === 'KITE' ? 'LIVE BROKER FEED' : optionChain.broker === 'OFFLINE' ? 'BROKER FEED OFFLINE' : 'SANDBOX SIMULATOR'}
                    </span>
                  )}
                </div>

                <div style={{
                  flex: 1, background: 'rgba(0, 0, 0, 0.3)', borderRadius: '8px', padding: '16px',
                  border: '1px solid rgba(255,255,255,0.03)', display: 'flex', flexDirection: 'column', gap: '16px',
                  minHeight: '250px'
                }}>
                  {loadingChain && !optionChain ? (
                    <div style={{ display: 'flex', flex: 1, justifyContent: 'center', alignItems: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
                      Querying live options contract premiums...
                    </div>
                  ) : errorChain ? (
                    <div style={{ display: 'flex', flex: 1, justifyContent: 'center', alignItems: 'center', color: 'var(--accent-red)', fontSize: '12px', flexDirection: 'column', gap: '8px' }}>
                      <span>⚠️ {errorChain}</span>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Verify backend API connection and status.</span>
                    </div>
                  ) : optionChain ? (
                    optionChain.broker === 'OFFLINE' ? (
                      <div style={{ display: 'flex', flex: 1, justifyContent: 'center', alignItems: 'center', color: 'var(--accent-red)', fontSize: '12px', flexDirection: 'column', gap: '12px', textAlign: 'center', padding: '16px' }}>
                        <span style={{ fontSize: '24px' }}>⚠️</span>
                        <span style={{ fontWeight: 700, fontSize: '13px', color: 'var(--text-primary)' }}>Broker Data Feed is Offline</span>
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)', maxWidth: '280px', lineHeight: '1.5' }}>
                          Real-time option premiums are currently unavailable because the broker feed has disconnected. Simulator sandbox fallbacks have been strictly disabled for strategy safety.
                        </span>
                      </div>
                    ) : (
                      <>
                        {/* Metric Summary Bar */}
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', background: 'var(--card-bg)', padding: '12px', borderRadius: '8px', border: '1px solid var(--border-glass)' }}>
                          <div>
                            <span style={{ fontSize: '10px', color: 'var(--text-muted)', display: 'block' }}>UNDERLYING SPOT</span>
                            <span style={{ fontSize: '14px', fontWeight: 800, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                              {optionChain.underlying.replace('NSE:', '')} @ {optionChain.spot_price > 0 ? `₹${optionChain.spot_price.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : 'N/A'}
                            </span>
                          </div>
                          <div style={{ textAlign: 'right' }}>
                            <span style={{ fontSize: '10px', color: 'var(--text-muted)', display: 'block' }}>NEAREST WEEKLY EXPIRY</span>
                            <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--accent-yellow)', display: 'block', marginTop: '3px' }}>
                              📅 {optionChain.expiry_date}
                            </span>
                          </div>
                        </div>

                        {/* Option Chain Table */}
                        <div style={{ flex: 1, overflowY: 'auto', marginTop: '12px' }}>
                          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px', textAlign: 'center' }}>
                            <thead>
                              <tr style={{ borderBottom: '1px solid var(--border-glass-subtle)', color: 'var(--text-muted)', fontSize: '10px' }}>
                                <th style={{ padding: '6px', textAlign: 'left' }}>CALL PREMIUM (CE)</th>
                                <th style={{ padding: '6px' }}>STRIKE PRICE</th>
                                <th style={{ padding: '6px', textAlign: 'right' }}>PUT PREMIUM (PE)</th>
                              </tr>
                            </thead>
                            <tbody>
                            {optionChain.chain.map((row: any) => {
                              const isAtm = row.CE.is_atm || row.PE.is_atm;
                              return (
                                <tr key={row.strike} style={{
                                  borderBottom: '1px solid rgba(255,255,255,0.02)',
                                  background: isAtm ? 'rgba(245, 158, 11, 0.05)' : 'transparent',
                                  transition: 'background 0.2s'
                                }} className="option-row">
                                  {/* Call Option Premium */}
                                  <td style={{ padding: '8px 6px', textAlign: 'left', display: 'flex', flexDirection: 'column' }}>
                                    <span style={{ color: 'var(--accent-green)', fontWeight: 700, fontSize: '12px' }}>
                                      ₹{row.CE.last_price.toFixed(2)}
                                    </span>
                                    <span style={{ color: 'var(--text-muted)', fontSize: '8px', fontFamily: 'monospace' }}>
                                      {row.CE.tradingsymbol}
                                    </span>
                                  </td>

                                  {/* Strike Price */}
                                  <td style={{ padding: '8px 6px' }}>
                                    <span style={{
                                      background: isAtm ? 'rgba(245, 158, 11, 0.2)' : 'rgba(255,255,255,0.03)',
                                      color: isAtm ? 'var(--accent-yellow)' : '#fff',
                                      padding: '3px 10px',
                                      borderRadius: '4px',
                                      fontSize: '12px',
                                      fontWeight: isAtm ? 800 : 600,
                                      border: isAtm ? '1px solid rgba(245, 158, 11, 0.4)' : '1px solid transparent',
                                      display: 'inline-flex',
                                      alignItems: 'center',
                                      gap: '4px'
                                    }}>
                                      {row.strike} {isAtm && <span style={{ fontSize: '8px', fontWeight: 900 }}>[ATM]</span>}
                                    </span>
                                  </td>

                                  {/* Put Option Premium */}
                                  <td style={{ padding: '8px 6px', textAlign: 'right' }}>
                                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
                                      <span style={{ color: 'rgba(239, 68, 68, 0.9)', fontWeight: 700, fontSize: '12px' }}>
                                        ₹{row.PE.last_price.toFixed(2)}
                                      </span>
                                      <span style={{ color: 'var(--text-muted)', fontSize: '8px', fontFamily: 'monospace' }}>
                                        {row.PE.tradingsymbol}
                                      </span>
                                    </div>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </>
                  )
                  ) : (
                    <div style={{ display: 'flex', flex: 1, justifyContent: 'center', alignItems: 'center', color: 'var(--text-muted)' }}>
                      No option chain loaded.
                    </div>
                  )}
                </div>
              </div>
            </div>
            
            {/* Modal Footer */}
            <div style={{ display: 'flex', justifyContent: 'flex-end', borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '16px' }}>
              <button onClick={() => setSelectedInstance(null)} className="btn-glass hover-red" style={{ padding: '8px 16px', borderRadius: '8px', fontSize: '13px' }}>
                Close Details
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
