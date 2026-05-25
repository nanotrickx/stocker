/**
 * Central API configuration.
 *
 * When running locally:        API_BASE = "http://localhost:8000"
 * When running through ngrok:  set NEXT_PUBLIC_API_URL in .env.local
 *
 * Usage:
 *   import { API_BASE, WS_BASE } from '../config';
 *   fetch(`${API_BASE}/api/strategies`)
 *   new WebSocket(`${WS_BASE}/api/ws`)
 */

const resolveBase = (): string => {
  if (typeof window !== 'undefined') {
    // Allow runtime override from env var (set in .env.local)
    const envUrl = process.env.NEXT_PUBLIC_API_URL;
    if (envUrl) return envUrl.replace(/\/$/, '');
  }
  return 'http://localhost:8000';
};

export const API_BASE = resolveBase();

export const WS_BASE = API_BASE
  .replace(/^https:/, 'wss:')
  .replace(/^http:/, 'ws:');
