'use client';

import React from 'react';
import { 
  Settings, 
  Shield, 
  Zap, 
  Send, 
  Save, 
  Bot, 
  Link, 
  Check, 
  X, 
  AlertTriangle, 
  RefreshCw, 
  Info, 
  Sliders, 
  ShieldCheck,
  Volume2
} from 'lucide-react';
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
  dhanTotpSecret: string;
  setDhanTotpSecret: (val: string) => void;
  onSaveCredentials: (broker: string, key: string, secret: string, totpSecret?: string) => void;
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
  dhanTotpSecret, setDhanTotpSecret,
  onSaveCredentials, onTestTelegram,
  activeBroker, onSelectActiveBroker
}: SettingsPageProps) {
  const [activeTab, setActiveTab] = React.useState<'broker' | 'risk' | 'notifications' | 'diagnostics'>('broker');
  const [requestToken, setRequestToken] = React.useState('');
  const [loginStatus, setLoginStatus] = React.useState<{ type: 'SUCCESS' | 'ERROR' | 'INFO', message: string } | null>(null);

  // Global Risk Settings States
  const [riskMaxDailyLoss, setRiskMaxDailyLoss] = React.useState('0');
  const [riskMaxActivePositions, setRiskMaxActivePositions] = React.useState('0');
  const [riskAutoSquareOffTime, setRiskAutoSquareOffTime] = React.useState('');
  const [riskDefaultSlippage, setRiskDefaultSlippage] = React.useState('0.0');

  // Telegram Notifications Toggles
  const [notifyOrderPlacement, setNotifyOrderPlacement] = React.useState(true);
  const [notifyOrderExecution, setNotifyOrderExecution] = React.useState(true);
  const [notifySlTargetHit, setNotifySlTargetHit] = React.useState(true);
  const [notifyDailySummary, setNotifyDailySummary] = React.useState(true);

  const [isSavingSettings, setIsSavingSettings] = React.useState(false);
  const [settingsSaveStatus, setSettingsSaveStatus] = React.useState<{ type: 'SUCCESS' | 'ERROR', message: string } | null>(null);

  // Broker Health Check State
  const [isTestingBroker, setIsTestingBroker] = React.useState(false);
  const [brokerTestStatus, setBrokerTestStatus] = React.useState<{ healthy: boolean, message: string, testedAt: string } | null>(null);

  // Load global safety settings on mount
  React.useEffect(() => {
    const fetchGlobalSettings = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/settings/global`);
        if (res.ok) {
          const data = await res.json();
          setRiskMaxDailyLoss(data.risk_max_daily_loss.toString());
          setRiskMaxActivePositions(data.risk_max_active_positions.toString());
          setRiskAutoSquareOffTime(data.risk_auto_square_off_time);
          setRiskDefaultSlippage(data.risk_default_slippage.toString());
          setNotifyOrderPlacement(data.notify_order_placement);
          setNotifyOrderExecution(data.notify_order_execution);
          setNotifySlTargetHit(data.notify_sl_target_hit);
          setNotifyDailySummary(data.notify_daily_summary);
        }
      } catch (e) {
        console.error("Failed to load global safety settings:", e);
      }
    };
    fetchGlobalSettings();
  }, []);

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

  const handleSaveGlobalSettings = async () => {
    setIsSavingSettings(true);
    setSettingsSaveStatus(null);
    try {
      const res = await fetch(`${API_BASE}/api/settings/global`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          risk_max_daily_loss: parseFloat(riskMaxDailyLoss) || 0,
          risk_max_active_positions: parseInt(riskMaxActivePositions) || 0,
          risk_auto_square_off_time: riskAutoSquareOffTime,
          risk_default_slippage: parseFloat(riskDefaultSlippage) || 0.0,
          notify_order_placement: notifyOrderPlacement,
          notify_order_execution: notifyOrderExecution,
          notify_sl_target_hit: notifySlTargetHit,
          notify_daily_summary: notifyDailySummary
        })
      });
      const result = await res.json();
      if (res.ok && result.status === 'SUCCESS') {
        setSettingsSaveStatus({ type: 'SUCCESS', message: 'Global risk controls and notification preferences updated successfully!' });
        setTimeout(() => setSettingsSaveStatus(null), 4000);
      } else {
        setSettingsSaveStatus({ type: 'ERROR', message: result.message || 'Failed to save settings.' });
      }
    } catch (e: any) {
      setSettingsSaveStatus({ type: 'ERROR', message: e.message || 'Error connecting to backend API.' });
    } finally {
      setIsSavingSettings(false);
    }
  };

  const handleTestBrokerConnection = async () => {
    setIsTestingBroker(true);
    setBrokerTestStatus(null);
    const start = Date.now();
    try {
      const res = await fetch(`${API_BASE}/api/broker/test-connection`, {
        method: 'POST'
      });
      const result = await res.json();
      const latency = Date.now() - start;
      if (res.ok && result.status === 'SUCCESS') {
        setBrokerTestStatus({
          healthy: result.healthy,
          message: result.healthy 
            ? `${result.message} (Latency: ${latency}ms)`
            : `Connection verification failed: ${result.message}`,
          testedAt: new Date().toLocaleTimeString()
        });
      } else {
        setBrokerTestStatus({
          healthy: false,
          message: result.message || 'Unable to verify broker connection.',
          testedAt: new Date().toLocaleTimeString()
        });
      }
    } catch (e: any) {
      setBrokerTestStatus({
        healthy: false,
        message: e.message || 'Error communicating with local gateway.',
        testedAt: new Date().toLocaleTimeString()
      });
    } finally {
      setIsTestingBroker(false);
    }
  };

  return (
    <div className="glass-panel responsive-container animate-slide-in" style={{ padding: '30px', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      
      {/* Page Header */}
      <div>
        <h2 style={{ fontSize: '20px', display: 'flex', alignItems: 'center', gap: '10px', fontWeight: 800 }}>
          <Settings size={22} className="glow-indigo" style={{ color: '#8B5CF6' }} /> Stocker Core System Settings
        </h2>
        <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
          Configure API endpoints, credentials, global risk controls, Telegram alerts, and manage active session authorizations.
        </p>
      </div>

      {/* Tabbed Navigation */}
      <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid var(--border-glass-subtle)', paddingBottom: '12px', overflowX: 'auto' }}>
        <button 
          onClick={() => setActiveTab('broker')}
          className="btn-glass"
          style={{ 
            padding: '10px 16px', fontSize: '13px', borderRadius: '8px', display: 'flex', alignItems: 'center', gap: '8px',
            background: activeTab === 'broker' ? 'rgba(99, 102, 241, 0.15)' : 'transparent',
            borderColor: activeTab === 'broker' ? '#6366F1' : 'var(--border-glass)',
            color: activeTab === 'broker' ? '#ffffff' : 'var(--text-secondary)',
            fontWeight: activeTab === 'broker' ? 600 : 400
          }}
        >
          <Link size={15} /> Broker Connections
        </button>

        <button 
          onClick={() => setActiveTab('risk')}
          className="btn-glass"
          style={{ 
            padding: '10px 16px', fontSize: '13px', borderRadius: '8px', display: 'flex', alignItems: 'center', gap: '8px',
            background: activeTab === 'risk' ? 'rgba(16, 185, 129, 0.1)' : 'transparent',
            borderColor: activeTab === 'risk' ? '#10B981' : 'var(--border-glass)',
            color: activeTab === 'risk' ? '#ffffff' : 'var(--text-secondary)',
            fontWeight: activeTab === 'risk' ? 600 : 400
          }}
        >
          <Shield size={15} /> Risk & Safety Controls
        </button>

        <button 
          onClick={() => setActiveTab('notifications')}
          className="btn-glass"
          style={{ 
            padding: '10px 16px', fontSize: '13px', borderRadius: '8px', display: 'flex', alignItems: 'center', gap: '8px',
            background: activeTab === 'notifications' ? 'rgba(245, 158, 11, 0.1)' : 'transparent',
            borderColor: activeTab === 'notifications' ? '#F59E0B' : 'var(--border-glass)',
            color: activeTab === 'notifications' ? '#ffffff' : 'var(--text-secondary)',
            fontWeight: activeTab === 'notifications' ? 600 : 400
          }}
        >
          <Bot size={15} /> Telegram Notifications
        </button>

        <button 
          onClick={() => setActiveTab('diagnostics')}
          className="btn-glass"
          style={{ 
            padding: '10px 16px', fontSize: '13px', borderRadius: '8px', display: 'flex', alignItems: 'center', gap: '8px',
            background: activeTab === 'diagnostics' ? 'rgba(239, 68, 68, 0.1)' : 'transparent',
            borderColor: activeTab === 'diagnostics' ? '#F43F5E' : 'var(--border-glass)',
            color: activeTab === 'diagnostics' ? '#ffffff' : 'var(--text-secondary)',
            fontWeight: activeTab === 'diagnostics' ? 600 : 400
          }}
        >
          <Sliders size={15} /> System Diagnostics
        </button>
      </div>

      {/* Tab Content Panels */}
      <div className="animate-slide-in">
        
        {/* TAB 1: BROKER CONNECTIONS */}
        {activeTab === 'broker' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '24px' }}>
            {/* Left: Selection */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
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
                      <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-primary)' }}>Zerodha Kite Connect 🪁</span>
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
                      <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-primary)' }}>Alice Blue ANT API 🌐</span>
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
                      <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-primary)' }}>DhanHQ Rolling Options API ⚡</span>
                      <p style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '2px' }}>Run backtests and route options orders directly via Dhan API</p>
                    </div>
                  </label>

                </div>
              </div>

              {/* Verify Connection Health block */}
              <div className="glass-card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
                <h3 style={{ fontSize: '14px', color: '#10B981', display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700 }}>
                  <ShieldCheck size={16} /> Connection Health Verifier
                </h3>
                <p style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                  Ping check the active broker's API session connection state to verify authentication is currently active.
                </p>
                
                {brokerTestStatus && (
                  <div style={{
                    fontSize: '12px', padding: '12px', borderRadius: '8px',
                    background: brokerTestStatus.healthy ? 'rgba(16, 185, 129, 0.08)' : 'rgba(239, 68, 68, 0.08)',
                    color: brokerTestStatus.healthy ? '#10B981' : '#EF4444',
                    border: `1px solid ${brokerTestStatus.healthy ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)'}`
                  }}>
                    <div style={{ fontWeight: 700, marginBottom: '2px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      {brokerTestStatus.healthy ? '🟢 Session Connected' : '🔴 Session Expired/Error'}
                    </div>
                    <div>{brokerTestStatus.message}</div>
                    <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '6px' }}>Tested at: {brokerTestStatus.testedAt}</div>
                  </div>
                )}

                <button
                  className="btn-glass"
                  onClick={handleTestBrokerConnection}
                  disabled={isTestingBroker}
                  style={{ 
                    padding: '10px', fontSize: '12px', borderRadius: '6px', cursor: 'pointer',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
                    color: 'var(--text-primary)'
                  }}
                >
                  <RefreshCw size={14} className={isTestingBroker ? 'spin' : ''} />
                  {isTestingBroker ? 'Testing API Gateway Connection...' : 'Test Connection Status'}
                </button>
              </div>
            </div>

            {/* Right: API Forms */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
              
              {/* Zerodha Form */}
              {activeBroker === 'kite' && (
                <>
                  <div className="glass-card animate-slide-in" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
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
                </>
              )}

              {/* Alice Blue Form */}
              {activeBroker === 'aliceblue' && (
                <div className="glass-card animate-slide-in" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
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
              )}

              {/* DhanHQ Form */}
              {activeBroker === 'dhan' && (
                <div className="glass-card animate-slide-in" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <h3 style={{ fontSize: '14px', color: '#3B82F6', display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700 }}>
                    ⚡ Live Broker: DhanHQ Options API
                  </h3>
                  
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Dhan Client ID / API Key</label>
                      <input 
                        type="text" 
                        value={dhanClientId} 
                        onChange={(e) => setDhanClientId(e.target.value)} 
                        className="input-glass" 
                        placeholder="Enter Dhan Client ID or API Key (e.g. 9203be84)"
                        style={{ padding: '10px', fontSize: '12px' }}
                      />
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Dhan Trading PIN / API Secret</label>
                      <input 
                        type="password" 
                        value={dhanAccessToken} 
                        onChange={(e) => setDhanAccessToken(e.target.value)} 
                        className="input-glass" 
                        placeholder="Enter 6-digit Dhan Trading PIN or API Secret"
                        style={{ padding: '10px', fontSize: '12px' }}
                      />
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Dhan TOTP Secret Key (For 24h Auto-Login)</label>
                      <input 
                        type="password" 
                        value={dhanTotpSecret} 
                        onChange={(e) => setDhanTotpSecret(e.target.value)} 
                        className="input-glass" 
                        placeholder="Enter TOTP Secret Key for automatic daily token generation"
                        style={{ padding: '10px', fontSize: '12px' }}
                      />
                    </div>
                  </div>

                  <button 
                    className="btn-primary" 
                    onClick={() => onSaveCredentials('dhan', dhanClientId, dhanAccessToken, dhanTotpSecret)} 
                    style={{ padding: '8px 16px', fontSize: '12px', borderRadius: '6px', alignSelf: 'flex-start', display: 'flex', alignItems: 'center', gap: '6px' }}
                  >
                    <Save size={14} /> Store Dhan API
                  </button>
                </div>
              )}

            </div>
          </div>
        )}

        {/* TAB 2: RISK & SAFETY CONTROLS */}
        {activeTab === 'risk' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            
            {/* Risk Disclaimer Alert */}
            <div className="glass-card" style={{ background: 'rgba(245, 158, 11, 0.05)', border: '1px solid rgba(245, 158, 11, 0.25)', display: 'flex', gap: '16px', padding: '20px' }}>
              <div style={{ color: '#F59E0B' }}><Info size={24} /></div>
              <div>
                <h4 style={{ fontSize: '14px', color: '#F59E0B', fontWeight: 700, marginBottom: '4px' }}>Global Algo Safeguards & Risk Controls</h4>
                <p style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                  These rules apply globally across all executing strategy instances (both custom indicator and ORB breakouts).
                  Once any limit is breached, the execution engine will strictly block any subsequent buy triggers until manual reset.
                </p>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '24px' }}>
              
              {/* Card Panel: Drawdown limits */}
              <div className="glass-card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <h3 style={{ fontSize: '14px', color: '#10B981', display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700 }}>
                  <Shield size={16} /> Daily Risk & Capital Limits
                </h3>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                      <label style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Max Daily Realized Loss Limit (INR)</label>
                      <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>0 = Disabled / No Limit</span>
                    </div>
                    <input 
                      type="number" 
                      value={riskMaxDailyLoss} 
                      onChange={(e) => setRiskMaxDailyLoss(e.target.value)} 
                      className="input-glass" 
                      placeholder="e.g. 5000"
                      style={{ padding: '10px', fontSize: '12px' }}
                    />
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                      <label style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Max Active Option Positions Limit</label>
                      <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>0 = Disabled / No Limit</span>
                    </div>
                    <input 
                      type="number" 
                      value={riskMaxActivePositions} 
                      onChange={(e) => setRiskMaxActivePositions(e.target.value)} 
                      className="input-glass" 
                      placeholder="e.g. 2"
                      style={{ padding: '10px', fontSize: '12px' }}
                    />
                  </div>
                </div>
              </div>

              {/* Card Panel: Execution parameters */}
              <div className="glass-card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <h3 style={{ fontSize: '14px', color: '#8B5CF6', display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700 }}>
                  <Sliders size={16} /> Global Order Execution Parameters
                </h3>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                      <label style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Auto-Square Off Time (IST, 24-hr)</label>
                      <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>HH:MM (e.g. 15:15)</span>
                    </div>
                    <input 
                      type="text" 
                      value={riskAutoSquareOffTime} 
                      onChange={(e) => setRiskAutoSquareOffTime(e.target.value)} 
                      className="input-glass" 
                      placeholder="15:15"
                      style={{ padding: '10px', fontSize: '12px' }}
                    />
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                      <label style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Global Slippage Allowance Estimate (%)</label>
                      <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>e.g. 0.05 = 5% slip</span>
                    </div>
                    <input 
                      type="number" 
                      step="0.01"
                      value={riskDefaultSlippage} 
                      onChange={(e) => setRiskDefaultSlippage(e.target.value)} 
                      className="input-glass" 
                      placeholder="0.02"
                      style={{ padding: '10px', fontSize: '12px' }}
                    />
                  </div>

                </div>
              </div>
            </div>

            {/* Save Status banner */}
            {settingsSaveStatus && (
              <div style={{ 
                fontSize: '12px', padding: '12px', borderRadius: '8px', width: '100%',
                background: settingsSaveStatus.type === 'SUCCESS' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                color: settingsSaveStatus.type === 'SUCCESS' ? '#10B981' : '#EF4444',
                border: `1px solid ${settingsSaveStatus.type === 'SUCCESS' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)'}`
              }}>
                {settingsSaveStatus.message}
              </div>
            )}

            <button 
              className="btn-primary"
              disabled={isSavingSettings}
              onClick={handleSaveGlobalSettings}
              style={{ 
                padding: '12px 24px', fontSize: '13px', borderRadius: '8px', alignSelf: 'flex-start',
                display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer'
              }}
            >
              <Save size={16} />
              {isSavingSettings ? 'Saving Safety Configuration...' : 'Apply Risk Safeguards'}
            </button>

          </div>
        )}

        {/* TAB 3: TELEGRAM & NOTIFICATIONS */}
        {activeTab === 'notifications' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '24px' }}>
            
            {/* Left Column: Bot Credentials */}
            <div className="glass-card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <h3 style={{ fontSize: '14px', color: '#6366F1', display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700 }}>
                <Bot size={16} /> Telegram Notifications Bot Credentials
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

            {/* Right Column: Alert Toggles (Verbosity Preferences) */}
            <div className="glass-card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <h3 style={{ fontSize: '14px', color: '#F59E0B', display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700 }}>
                <Volume2 size={16} /> Broadcast Filter Preferences
              </h3>
              <p style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                Customize which algorithm events trigger automated Telegram channel reports and bulletins in real-time.
              </p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '4px' }}>
                
                <label style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', padding: '10px', borderRadius: '6px', background: 'rgba(0,0,0,0.15)', cursor: 'pointer' }}>
                  <input 
                    type="checkbox" 
                    checked={notifyOrderPlacement} 
                    onChange={(e) => setNotifyOrderPlacement(e.target.checked)} 
                    style={{ accentColor: '#6366F1', marginTop: '3px' }}
                  />
                  <div>
                    <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>Buy Orders / Placements</span>
                    <p style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '2px' }}>Send messages immediately when dynamic strategy entry rules are met.</p>
                  </div>
                </label>

                <label style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', padding: '10px', borderRadius: '6px', background: 'rgba(0,0,0,0.15)', cursor: 'pointer' }}>
                  <input 
                    type="checkbox" 
                    checked={notifyOrderExecution} 
                    onChange={(e) => setNotifyOrderExecution(e.target.checked)} 
                    style={{ accentColor: '#6366F1', marginTop: '3px' }}
                  />
                  <div>
                    <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>Sell Exits / Executions</span>
                    <p style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '2px' }}>Send messages when order executions close active scalp positions.</p>
                  </div>
                </label>

                <label style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', padding: '10px', borderRadius: '6px', background: 'rgba(0,0,0,0.15)', cursor: 'pointer' }}>
                  <input 
                    type="checkbox" 
                    checked={notifySlTargetHit} 
                    onChange={(e) => setNotifySlTargetHit(e.target.checked)} 
                    style={{ accentColor: '#6366F1', marginTop: '3px' }}
                  />
                  <div>
                    <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>SL, Target & Trailing Stop loss Hits</span>
                    <p style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '2px' }}>Send immediate alerts when target profit or SL thresholds are breached.</p>
                  </div>
                </label>

                <label style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', padding: '10px', borderRadius: '6px', background: 'rgba(0,0,0,0.15)', cursor: 'pointer' }}>
                  <input 
                    type="checkbox" 
                    checked={notifyDailySummary} 
                    onChange={(e) => setNotifyDailySummary(e.target.checked)} 
                    style={{ accentColor: '#6366F1', marginTop: '3px' }}
                  />
                  <div>
                    <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>End of Day (EOD) Daily Summary bulletins</span>
                    <p style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '2px' }}>Send final trading account ledger reports automatically at 3:30 PM.</p>
                  </div>
                </label>

              </div>

              {settingsSaveStatus && settingsSaveStatus.type !== 'SUCCESS' && (
                <div style={{ color: '#EF4444', fontSize: '11px', marginTop: '4px' }}>
                  {settingsSaveStatus.message}
                </div>
              )}

              <button 
                className="btn-primary" 
                onClick={handleSaveGlobalSettings}
                style={{ padding: '10px 18px', fontSize: '12px', borderRadius: '6px', alignSelf: 'flex-start', display: 'flex', alignItems: 'center', gap: '6px', marginTop: '8px' }}
              >
                <Save size={14} /> Save Filter Preferences
              </button>
            </div>

          </div>
        )}

        {/* TAB 4: DIAGNOSTICS & LOGS */}
        {activeTab === 'diagnostics' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '24px' }}>
            
            {/* Sandbox Database reset card */}
            <div className="glass-card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '14px', border: '1px solid rgba(244, 63, 94, 0.3)' }}>
              <h3 style={{ fontSize: '14px', color: '#F43F5E', display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700 }}>
                <AlertTriangle size={16} /> Danger Zone / Sandbox Control
              </h3>
              <p style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                Reset paper trade execution records to completely restart sandbox metrics. This wipes all logs and ledger histories permanently.
              </p>
              
              {/* In page.tsx reset is triggered by REST endpoint call */}
              <button
                className="btn-glass"
                onClick={async () => {
                  if (confirm('This will wipe all paper positions, logs, and summaries to restart fresh. Proceed?')) {
                    try {
                      const res = await fetch(`${API_BASE}/api/paper-reset`, { method: 'POST' });
                      if (res.ok) {
                        alert('Paper trading database wiped successfully!');
                      }
                    } catch (e) {
                      alert('Error clearing database records.');
                    }
                  }
                }}
                style={{ 
                  padding: '10px', fontSize: '12px', borderRadius: '6px', alignSelf: 'flex-start', cursor: 'pointer',
                  border: '1px solid rgba(244, 63, 94, 0.2)', color: 'var(--accent-red)'
                }}
              >
                Reset Sandbox DB Records
              </button>
            </div>

            {/* System Info card */}
            <div className="glass-card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <h3 style={{ fontSize: '14px', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700 }}>
                <Info size={16} /> Core Engine Architecture Details
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '6px' }}>
                  <span style={{ color: 'var(--text-muted)' }}>FastAPI Gateway Status</span>
                  <span style={{ color: '#10B981', fontWeight: 600 }}>CONNECTED (Port 8000)</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '6px' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Database Engine</span>
                  <span>SQLite & SQLModel ORM</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '6px' }}>
                  <span style={{ color: 'var(--text-muted)' }}>System Version</span>
                  <span>Stocker Core Build v1.5.2</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Indian Standard Time (IST)</span>
                  <span>GMT +5:30 (Market Hours Active)</span>
                </div>
              </div>
            </div>

          </div>
        )}

      </div>

    </div>
  );
}
