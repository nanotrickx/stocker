'use client';

import React from 'react';
import { Bot, Plus, Trash2, Shield, Zap, HelpCircle, Power, Sliders, ExternalLink } from 'lucide-react';
import { Strategy, StrategyInstance } from '../types';

interface ActiveAlgorithmsProps {
  templates: Strategy[];
  instances: StrategyInstance[];
  onActivateClick: (strategy: Strategy) => void;
  onToggleInstance: (id: number, active: boolean) => void;
  onDeleteInstance: (id: number) => void;
  onCreateNewClick: () => void;
  onDeleteTemplate: (id: string) => void;
}

export default function ActiveAlgorithms({
  templates,
  instances,
  onActivateClick,
  onToggleInstance,
  onDeleteInstance,
  onCreateNewClick,
  onDeleteTemplate,
}: ActiveAlgorithmsProps) {

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '28px', margin: '24px' }}>
      
      {/* ──────────────────────────────────────────────────────── */}
      {/* SECTION 1: STRATEGY BLUEPRINT LIBRARY */}
      {/* ──────────────────────────────────────────────────────── */}
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
              return (
                <div 
                  key={tmpl.id} 
                  className="glass-card" 
                  style={{ 
                    display: 'flex', 
                    flexDirection: 'column', 
                    gap: '12px', 
                    background: 'rgba(15, 10, 25, 0.4)', 
                    border: '1px solid rgba(255, 255, 255, 0.04)' 
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <h3 style={{ fontSize: '15px', fontWeight: 700 }}>{tmpl.name}</h3>
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

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '10px', borderTop: '1px solid rgba(255,255,255,0.03)' }}>
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
                        borderBottom: '1px solid rgba(255,255,255,0.03)', 
                        background: inst.active ? 'rgba(16, 185, 129, 0.02)' : 'transparent',
                        transition: 'background 0.2s' 
                      }}
                    >
                      {/* Name */}
                      <td style={{ padding: '16px', fontWeight: 600, color: '#fff' }}>
                        {inst.name}
                      </td>

                      {/* Symbol */}
                      <td style={{ padding: '16px' }}>
                        <span style={{ fontFamily: 'monospace', background: 'rgba(0,0,0,0.3)', padding: '4px 8px', borderRadius: '4px', border: '1px solid rgba(255,255,255,0.03)' }}>
                          {inst.symbol}
                        </span>
                      </td>

                      {/* SL / Target */}
                      <td style={{ padding: '16px', color: 'var(--accent-yellow)', fontWeight: 600 }}>
                        🔻{sl}% / 🟩{target}%
                      </td>

                      {/* Qty */}
                      <td style={{ padding: '16px', color: '#fff' }}>
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

    </div>
  );
}
