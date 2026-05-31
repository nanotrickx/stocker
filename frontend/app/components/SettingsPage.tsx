'use client';

import React from 'react';
import { Settings, Shield, Zap, Send, Save, Bot } from 'lucide-react';
import { API_BASE } from '../config';

interface SettingsPageProps {
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
  dhanClientId: string;
  setDhanClientId: (val: string) => void;
  dhanAccessToken: string;
  setDhanAccessToken: (val: string) => void;
  onSaveCredentials: (broker: string, key: string, secret: string) => void;
  onTestTelegram: () => void;
  activeBroker: string;
  onSelectActiveBroker: (broker: string) => void;
}

export default function SettingsPage({
  telegramToken, setTelegramToken,
  telegramChatId, setTelegramChatId,
  kiteApiKey, setKiteApiKey,
  kiteApiSecret, setKiteApiSecret,
  aliceClientId, setAliceClientId,
  aliceApiKey, setAliceApiKey,
  dhanClientId, setDhanClientId,
  dhanAccessToken, setDhanAccessToken,
  onSaveCredentials, onTestTelegram,
  activeBroker, onSelectActiveBroker
}: SettingsPageProps) {
  const [requestToken, setRequestToken] = React.useState('');
  const [loginStatus, setLoginStatus] = React.useState<{ type: 'SUCCESS' | 'ERROR' | 'INFO', message: string } | null>(null);

  const handleZerodhaLogin = async () => {
    setLoginStatus({ type: 'INFO', message: 'Generating secure Kite daily session...' });
    try {
      const res = await fetch(`${API_BASE}/api/broker/zerodha-login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_token: requestToken })
      });
      const result = await res.json();
      if (result.status === 'SUCCESS') {
        setLoginStatus({ type: 'SUCCESS', message: result.message });
        setRequestToken('');
      } else {
        setLoginStatus({ type: 'ERROR', message: result.message });
      }
    } catch (e: any) {
      setLoginStatus({ type: 'ERROR', message: e.message || 'Failed to exchange credentials.' });
    }
  };
  
  return (
    <div className="glass-panel animate-slide-in" style={{ margin: '24px', padding: '30px', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      
      {/* Page Header */}
      <div>
        <h2 style={{ fontSize: '20px', display: 'flex', alignItems: 'center', gap: '10px', fontWeight: 800 }}>
          <Settings size={22} className="glow-indigo" style={{ color: '#8B5CF6' }} /> Stocker Core System Settings
        </h2>
        <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
          Configure API endpoints, credentials, Telegram alerts, and choose which active broker routes live option scalping orders.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '24px' }}>
        
        {/* Left Column: Broker Selection & Telegram */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          
          {/* Card: Active Live Broker Selector */}
          <div className="glass-card" style={{ padding: '24px', border: '1px solid rgba(139, 92, 246, 0.25)', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <h3 style={{ fontSize: '14px', color: '#8B5CF6', display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700 }}>
              <Zap size={16} /> Active Live Trading Broker Selection
            </h3>
            <p style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              Select which live API credentials the system will use for continuous mathematical evaluations and scalp order routing.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '8px' }}>
              
              <label 
                style={{ 
                  display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer', padding: '12px', 
                  borderRadius: '8px', background: activeBroker === 'kite' ? 'rgba(139, 92, 246, 0.1)' : 'rgba(0,0,0,0.15)',
                  border: activeBroker === 'kite' ? '1px solid rgba(139, 92, 246, 0.3)' : '1px solid rgba(255,255,255,0.02)',
                  transition: '0.2s'
                }}
              >
                <input 
                  type="radio" 
                  name="activeBrokerPage" 
                  value="kite" 
                  checked={activeBroker === 'kite'}
                  onChange={() => onSelectActiveBroker('kite')}
                  style={{ accentColor: '#8B5CF6', width: '16px', height: '16px' }}
                />
                <div>
                  <span style={{ fontSize: '13px', fontWeight: 700, color: '#fff' }}>Zerodha Kite Connect 🪁</span>
                  <p style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '2px' }}>Route trades directly via Kite Connect API keys</p>
                </div>
              </label>

              <label 
                style={{ 
                  display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer', padding: '12px', 
                  borderRadius: '8px', background: activeBroker === 'aliceblue' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(0,0,0,0.15)',
                  border: activeBroker === 'aliceblue' ? '1px solid rgba(16, 185, 129, 0.3)' : '1px solid rgba(255,255,255,0.02)',
                  transition: '0.2s'
                }}
              >
                <input 
                  type="radio" 
                  name="activeBrokerPage" 
                  value="aliceblue" 
                  checked={activeBroker === 'aliceblue'}
                  onChange={() => onSelectActiveBroker('aliceblue')}
                  style={{ accentColor: '#10B981', width: '16px', height: '16px' }}
                />
                <div>
                  <span style={{ fontSize: '13px', fontWeight: 700, color: '#fff' }}>Alice Blue ANT API 🌐</span>
                  <p style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '2px' }}>Route trades directly via A3 ANT REST client credentials</p>
                </div>
              </label>

              <label 
                style={{ 
                  display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer', padding: '12px', 
                  borderRadius: '8px', background: activeBroker === 'dhan' ? 'rgba(59, 130, 246, 0.1)' : 'rgba(0,0,0,0.15)',
                  border: activeBroker === 'dhan' ? '1px solid rgba(59, 130, 246, 0.3)' : '1px solid rgba(255,255,255,0.02)',
                  transition: '0.2s'
                }}
              >
                <input 
                  type="radio" 
                  name="activeBrokerPage" 
                  value="dhan" 
                  checked={activeBroker === 'dhan'}
                  onChange={() => onSelectActiveBroker('dhan')}
                  style={{ accentColor: '#3B82F6', width: '16px', height: '16px' }}
                />
                <div>
                  <span style={{ fontSize: '13px', fontWeight: 700, color: '#fff' }}>DhanHQ Rolling Options API ⚡</span>
                  <p style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '2px' }}>Run backtests and route options orders directly via Dhan API</p>
                </div>
              </label>

            </div>
          </div>

          {/* Card: Telegram Bot Configuration */}
          <div className="glass-card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <h3 style={{ fontSize: '14px', color: '#6366F1', display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700 }}>
              <Bot size={16} /> Telegram Notifications Bot Settings
            </h3>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Telegram Bot Token</label>
                <input 
                  type="password" 
                  value={telegramToken} 
                  onChange={(e) => setTelegramToken(e.target.value)} 
                  className="input-glass" 
                  placeholder="123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"
                  style={{ padding: '10px', fontSize: '12px' }}
                />
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Telegram Chat ID / Channel ID</label>
                <input 
                  type="text" 
                  value={telegramChatId} 
                  onChange={(e) => setTelegramChatId(e.target.value)} 
                  className="input-glass" 
                  placeholder="-1001234567890"
                  style={{ padding: '10px', fontSize: '12px' }}
                />
              </div>
            </div>

            <div style={{ display: 'flex', gap: '10px', marginTop: '4px' }}>
              <button 
                className="btn-primary" 
                onClick={() => onSaveCredentials('telegram', telegramToken, telegramChatId)} 
                style={{ padding: '8px 16px', fontSize: '12px', borderRadius: '6px', display: 'flex', alignItems: 'center', gap: '6px' }}
              >
                <Save size={14} /> Store Bot Tokens
              </button>
              <button 
                className="btn-glass" 
                onClick={onTestTelegram} 
                style={{ padding: '8px 16px', fontSize: '12px', borderRadius: '6px', color: 'var(--accent-yellow)', display: 'flex', alignItems: 'center', gap: '6px' }}
              >
                <Send size={14} /> Test Broadcast
              </button>
            </div>
          </div>

        </div>

        {/* Right Column: API Keys Configurations */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          
          {/* Card: Zerodha Kite Connect */}
          <div className="glass-card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <h3 style={{ fontSize: '14px', color: '#8B5CF6', display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700 }}>
              🪁 Live Broker: Zerodha Kite Connect API
            </h3>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Kite API Key</label>
                <input 
                  type="text" 
                  value={kiteApiKey} 
                  onChange={(e) => setKiteApiKey(e.target.value)} 
                  className="input-glass" 
                  placeholder="Enter Kite API Key"
                  style={{ padding: '10px', fontSize: '12px' }}
                />
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Kite API Secret (or Access Token)</label>
                <input 
                  type="password" 
                  value={kiteApiSecret} 
                  onChange={(e) => setKiteApiSecret(e.target.value)} 
                  className="input-glass" 
                  placeholder="Enter API Secret Token"
                  style={{ padding: '10px', fontSize: '12px' }}
                />
              </div>
            </div>

            <button 
              className="btn-primary" 
              onClick={() => onSaveCredentials('kite', kiteApiKey, kiteApiSecret)} 
              style={{ padding: '8px 16px', fontSize: '12px', borderRadius: '6px', alignSelf: 'flex-start', display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <Save size={14} /> Store Kite Connect API
            </button>
          </div>

          {/* Card: Zerodha Connect Active Session Manager */}
          {activeBroker === 'kite' && (
            <div className="glass-card animate-slide-in" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px', border: '1px solid rgba(139, 92, 246, 0.4)' }}>
              <h3 style={{ fontSize: '14px', color: '#8B5CF6', display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700 }}>
                🔑 Zerodha Connect Session Authorizer
              </h3>
              <p style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                Zerodha requires daily login authentication. Complete these steps to validate your active session.
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <button 
                  onClick={async () => {
                    try {
                      const res = await fetch(`${API_BASE}/api/broker/zerodha-auth-url`);
                      const result = await res.json();
                      if (result.status === 'SUCCESS' && result.url) {
                        window.open(result.url, '_blank', 'noopener,noreferrer');
                      } else {
                        alert(result.message || 'Failed to generate secure auth session.');
                      }
                    } catch (e) {
                      alert('Unable to contact secure trading engine authentication gateway.');
                    }
                  }}
                  className="btn-glass"
                  style={{ width: '100%', padding: '10px', textAlign: 'center', display: 'block', borderRadius: '6px', fontSize: '12px', color: 'var(--accent-yellow)', border: '1px solid rgba(245, 158, 11, 0.3)', cursor: 'pointer', background: 'transparent' }}
                >
                  🔗 Step 1: Click here to log in & authenticate Zerodha Kite
                </button>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Step 2: Paste the returned 'request_token' parameter here:</label>
                  <input 
                    type="text" 
                    value={requestToken} 
                    onChange={(e) => setRequestToken(e.target.value)} 
                    placeholder="e.g. 32-character token from address bar"
                    className="input-glass"
                    style={{ padding: '10px', fontSize: '12px' }}
                  />
                </div>
                {loginStatus && (
                  <div style={{ 
                    fontSize: '12px', padding: '10px', borderRadius: '6px', 
                    background: loginStatus.type === 'SUCCESS' ? 'rgba(16, 185, 129, 0.1)' : loginStatus.type === 'ERROR' ? 'rgba(239, 68, 68, 0.1)' : 'rgba(139, 92, 246, 0.1)',
                    color: loginStatus.type === 'SUCCESS' ? '#10B981' : loginStatus.type === 'ERROR' ? '#EF4444' : '#8B5CF6',
                    border: `1px solid ${loginStatus.type === 'SUCCESS' ? 'rgba(16, 185, 129, 0.2)' : loginStatus.type === 'ERROR' ? 'rgba(239, 68, 68, 0.2)' : 'rgba(139, 92, 246, 0.2)'}`
                  }}>
                    {loginStatus.message}
                  </div>
                )}
                <button 
                  className="btn-primary" 
                  onClick={handleZerodhaLogin}
                  disabled={!requestToken}
                  style={{ padding: '10px', fontSize: '12px', borderRadius: '6px', width: '100%', opacity: requestToken ? 1 : 0.6 }}
                >
                  Verify & Activate Daily Session
                </button>
              </div>
            </div>
          )}

          {/* Card: Alice Blue ANT API */}
          <div className="glass-card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <h3 style={{ fontSize: '14px', color: 'var(--accent-green)', display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700 }}>
              🌐 Live Broker: Alice Blue A3 ANT API
            </h3>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Alice Client ID (Username)</label>
                <input 
                  type="text" 
                  value={aliceClientId} 
                  onChange={(e) => setAliceClientId(e.target.value)} 
                  className="input-glass" 
                  placeholder="e.g. AB123456"
                  style={{ padding: '10px', fontSize: '12px' }}
                />
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>ANT API Key</label>
                <input 
                  type="password" 
                  value={aliceApiKey} 
                  onChange={(e) => setAliceApiKey(e.target.value)} 
                  className="input-glass" 
                  placeholder="Enter Alice Blue API Key"
                  style={{ padding: '10px', fontSize: '12px' }}
                />
              </div>
            </div>

            <button 
              className="btn-primary" 
              onClick={() => onSaveCredentials('aliceblue', aliceClientId, aliceApiKey)} 
              style={{ padding: '8px 16px', fontSize: '12px', borderRadius: '6px', alignSelf: 'flex-start', display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <Save size={14} /> Store Alice Blue API
            </button>
          </div>

          {/* Card: DhanHQ API */}
          <div className="glass-card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <h3 style={{ fontSize: '14px', color: '#3B82F6', display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700 }}>
              ⚡ Live Broker: DhanHQ Options API
            </h3>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Dhan Client ID</label>
                <input 
                  type="text" 
                  value={dhanClientId} 
                  onChange={(e) => setDhanClientId(e.target.value)} 
                  className="input-glass" 
                  placeholder="Enter Dhan Client ID"
                  style={{ padding: '10px', fontSize: '12px' }}
                />
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Dhan JWT Access Token</label>
                <input 
                  type="password" 
                  value={dhanAccessToken} 
                  onChange={(e) => setDhanAccessToken(e.target.value)} 
                  className="input-glass" 
                  placeholder="Enter Dhan Access Token"
                  style={{ padding: '10px', fontSize: '12px' }}
                />
              </div>
            </div>

            <button 
              className="btn-primary" 
              onClick={() => onSaveCredentials('dhan', dhanClientId, dhanAccessToken)} 
              style={{ padding: '8px 16px', fontSize: '12px', borderRadius: '6px', alignSelf: 'flex-start', display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <Save size={14} /> Store Dhan API
            </button>
          </div>

        </div>

      </div>

    </div>
  );
}
