'use client';

import React, { useState, useEffect } from 'react';
import { X, Play, Shield, Zap, Info } from 'lucide-react';
import { Strategy } from '../types';

interface ActivationModalProps {
  strategy: Strategy;
  onClose: () => void;
  onDeploy: (data: {
    template_id: string;
    symbol: string;
    instrument_type: string;
    quantity: number;
    stop_loss_pct: number;
    target_pct: number;
    premium_min: number;
    premium_max: number;
    paper_trade: boolean;
  }) => void;
}

const GLASS_INPUT: React.CSSProperties = {
  background: 'rgba(0, 0, 0, 0.4)',
  border: '1px solid rgba(255, 255, 255, 0.08)',
  borderRadius: '8px',
  color: '#fff',
  padding: '10px 12px',
  fontSize: '13px',
  outline: 'none',
  width: '100%',
  marginTop: '4px',
  transition: 'border 0.2s',
};

const LABEL: React.CSSProperties = {
  fontSize: '11px',
  color: 'var(--text-muted)',
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: '.04em',
  display: 'block',
};

export default function ActivationModal({ strategy, onClose, onDeploy }: ActivationModalProps) {
  // Parse defaults from template config
  const config = React.useMemo(() => {
    try {
      return JSON.parse(strategy.config_json);
    } catch {
      return {};
    }
  }, [strategy.config_json]);

  const defaultSymbol = config.symbols?.[0] || 'NSE:NIFTY 50';
  const defaultQty = config.action?.quantity || 50;
  const defaultSL = config.risk?.stop_loss_pct || 10.0;
  const defaultTarget = config.risk?.target_pct || 10.0;
  const defaultMin = config.option_selection?.premium_min || 100;
  const defaultMax = config.option_selection?.premium_max || 200;

  const [symbol, setSymbol] = useState(defaultSymbol);
  const [instrumentType, setInstrumentType] = useState(config.action?.instrument_type || 'OPTION');
  const [quantity, setQuantity] = useState(defaultQty);
  const [slPct, setSlPct] = useState(defaultSL);
  const [targetPct, setTargetPct] = useState(defaultTarget);
  const [premiumMin, setPremiumMin] = useState(defaultMin);
  const [premiumMax, setPremiumMax] = useState(defaultMax);
  const [paperTrade, setPaperTrade] = useState(true);

  // Auto-update quantity default based on symbol choice
  useEffect(() => {
    if (symbol.includes('BANKNIFTY')) {
      setQuantity(15);
    } else if (symbol.includes('NIFTY')) {
      setQuantity(50);
    }
  }, [symbol]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onDeploy({
      template_id: strategy.id,
      symbol,
      instrument_type: instrumentType,
      quantity,
      stop_loss_pct: slPct,
      target_pct: targetPct,
      premium_min: premiumMin,
      premium_max: premiumMax,
      paper_trade: paperTrade,
    });
  };

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(8px)',
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px',
      }}
      className="animate-fade-in"
    >
      <div
        className="glass-panel"
        style={{
          width: '100%',
          maxWidth: '540px',
          background: 'rgba(17, 12, 28, 0.85)',
          border: '1px solid rgba(139, 92, 246, 0.25)',
          borderRadius: '16px',
          overflow: 'hidden',
          boxShadow: '0 20px 40px rgba(0, 0, 0, 0.5), 0 0 50px rgba(139, 92, 246, 0.1)',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '20px 24px',
            borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <div>
            <h3 style={{ fontSize: '18px', fontWeight: 700, color: '#fff', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Play size={18} style={{ color: '#8B5CF6' }} /> Deploy Strategy Instance
            </h3>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
              Blueprint: {strategy.name}
            </p>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              padding: '4px',
              borderRadius: '50%',
              transition: '0.2s',
            }}
            className="hover-red"
          >
            <X size={20} />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} style={{ padding: '24px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
            
            {/* Symbol Target */}
            <div>
              <label style={LABEL}>Target Asset Symbol</label>
              <select
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                style={GLASS_INPUT}
              >
                <option value="NSE:NIFTY 50">NSE: NIFTY 50</option>
                <option value="NSE:NIFTY BANK">NSE: BANKNIFTY</option>
                <option value="NSE:RELIANCE">NSE: RELIANCE</option>
                <option value="NSE:TCS">NSE: TCS</option>
                <option value="NSE:HDFCBANK">NSE: HDFCBANK</option>
              </select>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              {/* Instrument Type */}
              <div>
                <label style={LABEL}>Instrument Segment</label>
                <select
                  value={instrumentType}
                  onChange={(e) => setInstrumentType(e.target.value)}
                  style={GLASS_INPUT}
                >
                  <option value="OPTION">Options (NFO)</option>
                  <option value="STOCK">Equities Spot (NSE)</option>
                </select>
              </div>

              {/* Quantity */}
              <div>
                <label style={LABEL}>Position Quantity / Lot Size</label>
                <input
                  type="number"
                  value={quantity}
                  onChange={(e) => setQuantity(parseInt(e.target.value) || 0)}
                  style={GLASS_INPUT}
                  min={1}
                />
              </div>
            </div>

            {/* Stop Loss and Target */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              <div>
                <label style={LABEL}>Stop Loss % (SL)</label>
                <input
                  type="number"
                  step="0.1"
                  value={slPct}
                  onChange={(e) => setSlPct(parseFloat(e.target.value) || 0.0)}
                  style={GLASS_INPUT}
                  min={0.1}
                />
              </div>

              <div>
                <label style={LABEL}>Profit Target %</label>
                <input
                  type="number"
                  step="0.1"
                  value={targetPct}
                  onChange={(e) => setTargetPct(parseFloat(e.target.value) || 0.0)}
                  style={GLASS_INPUT}
                  min={0.1}
                />
              </div>
            </div>

            {/* ORB specific premium configuration */}
            {strategy.strategy_type === 'orb_breakout' && (
              <div
                style={{
                  background: 'rgba(139, 92, 246, 0.06)',
                  border: '1px solid rgba(139, 92, 246, 0.15)',
                  borderRadius: '10px',
                  padding: '16px',
                  marginTop: '4px',
                }}
              >
                <span
                  style={{
                    fontSize: '11px',
                    color: '#8B5CF6',
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                    marginBottom: '10px',
                  }}
                >
                  <Info size={12} /> ORB Premium Range Filters
                </span>
                
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                  <div>
                    <label style={{ ...LABEL, fontSize: '10px' }}>Min Premium Price (₹)</label>
                    <input
                      type="number"
                      value={premiumMin}
                      onChange={(e) => setPremiumMin(parseInt(e.target.value) || 0)}
                      style={{ ...GLASS_INPUT, background: 'rgba(0,0,0,0.5)' }}
                    />
                  </div>

                  <div>
                    <label style={{ ...LABEL, fontSize: '10px' }}>Max Premium Price (₹)</label>
                    <input
                      type="number"
                      value={premiumMax}
                      onChange={(e) => setPremiumMax(parseInt(e.target.value) || 0)}
                      style={{ ...GLASS_INPUT, background: 'rgba(0,0,0,0.5)' }}
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Trading Sandbox Mode selector */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '12px 16px',
                background: 'rgba(255,255,255,0.02)',
                border: '1px solid rgba(255,255,255,0.05)',
                borderRadius: '8px',
                marginTop: '4px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                {paperTrade ? (
                  <Shield size={18} style={{ color: '#8B5CF6' }} />
                ) : (
                  <Zap size={18} style={{ color: 'var(--accent-green)' }} />
                )}
                <div>
                  <span style={{ fontSize: '13px', fontWeight: 600, color: '#fff', display: 'block' }}>
                    {paperTrade ? 'Paper Sandbox Mode' : 'Live Order Routing'}
                  </span>
                  <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                    {paperTrade
                      ? 'Simulates trades locally with virtual capital'
                      : 'Executes real transactions via Zerodha Kite'}
                  </span>
                </div>
              </div>

              <label className="switch" style={{ position: 'relative', display: 'inline-block', width: '38px', height: '20px' }}>
                <input
                  type="checkbox"
                  checked={!paperTrade}
                  onChange={(e) => setPaperTrade(!e.target.checked)}
                  style={{ opacity: 0, width: 0, height: 0 }}
                />
                <span
                  style={{
                    position: 'absolute',
                    cursor: 'pointer',
                    top: 0,
                    left: 0,
                    right: 0,
                    bottom: 0,
                    background: !paperTrade ? 'var(--accent-green)' : 'rgba(255,255,255,0.1)',
                    borderRadius: '34px',
                    transition: '0.3s',
                  }}
                >
                  <span
                    style={{
                      position: 'absolute',
                      content: '""',
                      height: '14px',
                      width: '14px',
                      left: !paperTrade ? '20px' : '3px',
                      bottom: '3px',
                      background: '#fff',
                      borderRadius: '50%',
                      transition: '0.3s',
                    }}
                  />
                </span>
              </label>
            </div>

          </div>

          {/* Action Row */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'flex-end',
              gap: '12px',
              marginTop: '28px',
              borderTop: '1px solid rgba(255, 255, 255, 0.05)',
              paddingTop: '20px',
            }}
          >
            <button
              type="button"
              onClick={onClose}
              className="btn-glass"
              style={{ padding: '10px 20px', borderRadius: '8px', fontSize: '13px' }}
            >
              Cancel
            </button>
            
            <button
              type="submit"
              className="btn-primary"
              style={{
                padding: '10px 24px',
                borderRadius: '8px',
                fontSize: '13px',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                boxShadow: '0 4px 12px rgba(139, 92, 246, 0.3)',
              }}
            >
              <Play size={14} /> Activate Strategy
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
