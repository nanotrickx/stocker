'use client';

import React from 'react';
import { Settings, X } from 'lucide-react';

interface SettingsModalProps {
  show: boolean;
  onClose: () => void;
  telegramToken: string;
  setTelegramToken: (val: string) => void;
  telegramChatId: string;
  setTelegramChatId: (val: string) => void;
  kiteApiKey: string;
  setKiteApiKey: (val: string) => void;
  kiteApiSecret: string;
  setKiteApiSecret: (val: string) => void;
  aliceClientId: string;
  setAliceClientId: (val: string) => void;
  aliceApiKey: string;
  setAliceApiKey: (val: string) => void;
  onSaveCredentials: (broker: string, key: string, secret: string) => void;
  onTestTelegram: () => void;
  activeBroker: string;
  onSelectActiveBroker: (broker: string) => void;
}

export default function SettingsModal({
  show, onClose,
  telegramToken, setTelegramToken,
  telegramChatId, setTelegramChatId,
  kiteApiKey, setKiteApiKey,
  kiteApiSecret, setKiteApiSecret,
  aliceClientId, setAliceClientId,
  aliceApiKey, setAliceApiKey,
  onSaveCredentials, onTestTelegram,
  activeBroker, onSelectActiveBroker
}: SettingsModalProps) {
  if (!show) return null;

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0, 0, 0, 0.75)', backdropFilter: 'blur(8px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
      <div className="glass-panel animate-slide-in" style={{ width: '90%', maxWidth: '600px', padding: '30px', display: 'flex', flexDirection: 'column', gap: '20px', position: 'relative' }}>
        <button onClick={onClose} style={{ position: 'absolute', top: '20px', right: '20px', background: 'transparent', color: 'var(--text-muted)', border: 'none', cursor: 'pointer' }}>
          <X size={20} />
        </button>

        <h2 style={{ fontSize: '18px', display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Settings size={20} className="glow-green" /> Stocker System Settings Panel
        </h2>

        {/* Active Live Broker Selector */}
        <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: '10px', border: '1px solid rgba(139, 92, 246, 0.25)' }}>
          <h3 style={{ fontSize: '13px', color: '#8B5CF6', display: 'flex', alignItems: 'center', gap: '6px' }}>
            ⚡ Active Live Trading Broker Selection
          </h3>
          <p style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
            Select which live API credentials the system will use for continuous evaluations and order routing.
          </p>
          <div style={{ display: 'flex', gap: '24px', marginTop: '4px' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px' }}>
              <input 
                type="radio" 
                name="activeBroker" 
                value="kite" 
                checked={activeBroker === 'kite'}
                onChange={() => onSelectActiveBroker('kite')}
                style={{ accentColor: '#8B5CF6' }}
              />
              <span style={{ fontWeight: activeBroker === 'kite' ? 700 : 400, color: activeBroker === 'kite' ? '#fff' : 'var(--text-secondary)' }}>
                Zerodha Kite Connect 🪁
              </span>
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px' }}>
              <input 
                type="radio" 
                name="activeBroker" 
                value="aliceblue" 
                checked={activeBroker === 'aliceblue'}
                onChange={() => onSelectActiveBroker('aliceblue')}
                style={{ accentColor: '#10B981' }}
              />
              <span style={{ fontWeight: activeBroker === 'aliceblue' ? 700 : 400, color: activeBroker === 'aliceblue' ? '#fff' : 'var(--text-secondary)' }}>
                Alice Blue ANT API 🌐
              </span>
            </label>
          </div>
        </div>

        {/* Telegram card */}
        <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <h3 style={{ fontSize: '13px', color: '#6366F1' }}>📢 Telegram Bot Configuration</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Telegram Bot Token</label>
              <input type="password" value={telegramToken} onChange={(e) => setTelegramToken(e.target.value)} className="input-glass" />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Telegram Chat ID</label>
              <input type="text" value={telegramChatId} onChange={(e) => setTelegramChatId(e.target.value)} className="input-glass" />
            </div>
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button className="btn-primary" onClick={() => onSaveCredentials('telegram', telegramToken, telegramChatId)} style={{ padding: '6px 14px', fontSize: '11px', borderRadius: '6px', marginTop: '6px' }}>
              Store Bot Credentials
            </button>
            <button className="btn-glass" onClick={onTestTelegram} style={{ padding: '6px 14px', fontSize: '11px', borderRadius: '6px', marginTop: '6px', color: 'var(--accent-yellow)' }}>
              Send Test Notification
            </button>
          </div>
        </div>

        {/* Zerodha Kite card */}
        <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <h3 style={{ fontSize: '13px', color: '#8B5CF6' }}>🪁 Live Vendor: Zerodha Kite Connect</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Kite API Key</label>
              <input type="text" value={kiteApiKey} onChange={(e) => setKiteApiKey(e.target.value)} className="input-glass" />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Kite API Secret</label>
              <input type="password" value={kiteApiSecret} onChange={(e) => setKiteApiSecret(e.target.value)} className="input-glass" />
            </div>
          </div>
          <button className="btn-primary" onClick={() => onSaveCredentials('kite', kiteApiKey, kiteApiSecret)} style={{ padding: '6px 14px', fontSize: '11px', borderRadius: '6px', marginTop: '6px', alignSelf: 'flex-start' }}>
            Store Kite Connect Credentials
          </button>
        </div>

        {/* Alice Blue card */}
        <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <h3 style={{ fontSize: '13px', color: 'var(--accent-green)' }}>🌐 Live Vendor: Alice Blue A3 API</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Alice Client ID</label>
              <input type="text" value={aliceClientId} onChange={(e) => setAliceClientId(e.target.value)} className="input-glass" />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>ANT API Key</label>
              <input type="password" value={aliceApiKey} onChange={(e) => setAliceApiKey(e.target.value)} className="input-glass" />
            </div>
          </div>
          <button className="btn-primary" onClick={() => onSaveCredentials('aliceblue', aliceClientId, aliceApiKey)} style={{ padding: '6px 14px', fontSize: '11px', borderRadius: '6px', marginTop: '6px', alignSelf: 'flex-start' }}>
            Store Alice Blue Credentials
          </button>
        </div>

        <button className="btn-glass" onClick={onClose} style={{ padding: '10px 20px', borderRadius: '8px', alignSelf: 'flex-end', marginTop: '10px' }}>
          Close Settings
        </button>
      </div>
    </div>
  );
}
