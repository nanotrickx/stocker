'use client';
 
import React from 'react';
import { 
  Activity, 
  RefreshCw, 
  Settings, 
  TrendingUp, 
  Bot, 
  BookOpen, 
  BarChart2, 
  Briefcase, 
  LayoutDashboard,
  Shield,
  Zap,
  Menu,
  Sun,
  Moon
} from 'lucide-react';
 
interface HeaderProps {
  wsConnected: boolean;
  positionsCount: number;
  onRefresh: () => void;
  onOpenSettings: () => void;
  spotPrice: number;
  activeTab: string;
  portfolio: {
    is_live: boolean;
    cash_balance: number;
    available_margin: number;
    broker_name: string;
  };
  onToggleMobileSidebar?: () => void;
  theme: 'dark' | 'light';
  onToggleTheme: () => void;
}

export default function Header({ 
  wsConnected, 
  positionsCount, 
  onRefresh, 
  onOpenSettings,
  spotPrice,
  activeTab,
  portfolio,
  onToggleMobileSidebar,
  theme,
  onToggleTheme
}: HeaderProps) {

  // Breadcrumb resolver
  const getBreadcrumb = () => {
    switch (activeTab) {
      case 'dashboard':
        return {
          group: 'Trading Desk',
          page: 'Market Dashboard',
          icon: <LayoutDashboard size={16} style={{ color: '#6366F1' }} />
        };
      case 'builder':
        return {
          group: 'Strategy Corner',
          page: 'Blueprint Builder',
          icon: <Bot size={16} style={{ color: '#8B5CF6' }} />
        };
      case 'ledger':
        return {
          group: 'Trading Desk',
          page: 'Trade Logs & Ledger',
          icon: <BookOpen size={16} style={{ color: '#10B981' }} />
        };
      case 'backtest':
        return {
          group: 'Strategy Corner',
          page: 'Backtest Simulator',
          icon: <BarChart2 size={16} style={{ color: '#F59E0B' }} />
        };
      case 'portfolio':
        return {
          group: 'Trading Desk',
          page: 'Broker Portfolio',
          icon: <Briefcase size={16} style={{ color: '#EC4899' }} />
        };
      case 'settings':
        return {
          group: 'System Control',
          page: 'System Settings',
          icon: <Settings size={16} style={{ color: '#9CA3AF' }} />
        };
      default:
        return {
          group: 'Console',
          page: 'Stocker Terminal',
          icon: <Activity size={16} style={{ color: '#6366F1' }} />
        };
    }
  };

  const breadcrumb = getBreadcrumb();

  return (
    <header className="glass-panel dashboard-header">
      {/* Left: Hamburger Navigation Menu Toggle & Breadcrumbs */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <button 
          className="mobile-nav-toggle"
          onClick={onToggleMobileSidebar}
          title="Open Menu"
        >
          <Menu size={16} />
        </button>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '32px',
            height: '32px',
            borderRadius: '8px',
            background: 'rgba(255, 255, 255, 0.03)',
            border: '1px solid rgba(255, 255, 255, 0.05)'
          }}>
            {breadcrumb.icon}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <span style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600, letterSpacing: '0.05em' }}>
              {breadcrumb.group}
            </span>
            <h2 style={{ fontSize: '14px', fontWeight: 700, color: 'var(--text-primary)', margin: 0, lineHeight: '1.2' }}>
              {breadcrumb.page}
            </h2>
          </div>
        </div>
      </div>

      {/* Right: Metrics, Ticker & Actions */}
      <div className="header-metrics-group">
        
        {/* NIFTY 50 Live Ticker */}
        <div className="header-metric-block" style={{ 
          background: 'rgba(0, 0, 0, 0.3)', 
          border: '1px solid rgba(255, 255, 255, 0.04)', 
          padding: '6px 14px', 
          borderRadius: '8px',
          display: 'flex',
          alignItems: 'center',
          gap: '12px'
        }}>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <span style={{ fontSize: '8px', color: 'var(--text-muted)', fontWeight: 700 }}>NIFTY 50 INDEX</span>
            <span className="glow-green" style={{ fontSize: '13px', fontWeight: 800, fontFamily: 'monospace' }}>
              ₹{spotPrice.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>
          <span className={`pulsar ${wsConnected ? '' : 'red'}`} style={{ width: '6px', height: '6px' }} />
        </div>

        {/* Live Broker Margin / Account Ticker */}
        <div className="header-metric-block" style={{ 
          background: 'rgba(0, 0, 0, 0.3)', 
          border: '1px solid rgba(255, 255, 255, 0.04)', 
          padding: '6px 14px', 
          borderRadius: '8px',
          display: 'flex',
          alignItems: 'center',
          gap: '12px'
        }}>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <span style={{ fontSize: '8px', color: 'var(--text-muted)', fontWeight: 700 }}>
              {portfolio.is_live ? `${portfolio.broker_name.toUpperCase()} MARGIN` : 'VIRTUAL MARGIN'}
            </span>
            <span style={{ fontSize: '13px', fontWeight: 800, color: portfolio.is_live ? '#10B981' : '#8B5CF6', fontFamily: 'monospace' }}>
              ₹{portfolio.is_live 
                ? portfolio.available_margin.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                : '1,00,000.00'
              }
            </span>
          </div>
          {portfolio.is_live ? (
            <Zap size={12} style={{ color: '#10B981' }} />
          ) : (
            <Shield size={12} style={{ color: '#8B5CF6' }} />
          )}
        </div>

        {/* Active Trades Badge */}
        <div className="header-metric-block" style={{ 
          background: 'rgba(139, 92, 246, 0.06)', 
          border: '1px solid rgba(139, 92, 246, 0.15)', 
          padding: '6px 14px', 
          borderRadius: '8px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center'
        }}>
          <span style={{ fontSize: '8px', color: 'var(--text-muted)', fontWeight: 700 }}>POSITIONS</span>
          <span style={{ fontSize: '13px', fontWeight: 800, color: '#a78bfa' }}>
            {positionsCount}
          </span>
        </div>

        {/* Action Buttons */}
        <div className="header-actions-block" style={{ display: 'flex', gap: '6px' }}>
          <button 
            className="btn-glass" 
            onClick={onToggleTheme} 
            title={`Switch to ${theme === 'dark' ? 'Light' : 'Dark'} Mode`}
            style={{ 
              width: '32px', 
              height: '32px', 
              borderRadius: '8px', 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center',
              padding: 0
            }}
          >
            {theme === 'dark' ? <Sun size={14} style={{ color: '#F59E0B' }} /> : <Moon size={14} style={{ color: '#6366F1' }} />}
          </button>
          <button 
            className="btn-glass" 
            onClick={onRefresh} 
            title="Reload API State Ticks"
            style={{ 
              width: '32px', 
              height: '32px', 
              borderRadius: '8px', 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center',
              padding: 0
            }}
          >
            <RefreshCw size={14} />
          </button>
          <button 
            className="btn-glass" 
            onClick={onOpenSettings} 
            title="Configure System Credentials"
            style={{ 
              width: '32px', 
              height: '32px', 
              borderRadius: '8px', 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center',
              padding: 0
            }}
          >
            <Settings size={14} />
          </button>
        </div>

      </div>
    </header>
  );
}
