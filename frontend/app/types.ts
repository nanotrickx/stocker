export interface IndicatorCondition {
  indicator: string;
  period?: number;
  comparison: string;
  target: string;
  value?: number;
  target_indicator?: string;
  target_period?: number;
}

export type StrategyType = 'custom' | 'orb_breakout';

export interface TimeframeConfig {
  opening_candle_tf: string;
  pre_1030_tf: string;
  post_1030_tf: string;
}

export interface PremiumFilter {
  premium_min: number;
  premium_max: number;
  shift_to_otm_if_exceeded: boolean;
}

export interface ORBConfig {
  strategy_type: 'orb_breakout';
  symbols: string[];
  timeframes: TimeframeConfig;
  opening_range: { candle_time: string };
  option_selection: PremiumFilter & { strike_selection: string };
  risk: { target_pct: number; stop_loss_pct: number };
  action: {
    instrument_type: string;
    quantity: number;
    expiry_type: string;
    paper_trade: boolean;
  };
  timeline: {
    start_time: string;
    end_time: string;
    days_of_week: number[];
  };
}

export interface Strategy {
  id: string;
  name: string;
  description?: string;
  strategy_type?: string;
  active: boolean;
  paper_trade: boolean;
  config_json: string;
  created_at: string;
}

export interface StrategyInstance {
  id: number;
  template_id: string;
  template_name: string;
  strategy_type: string;
  name: string;
  symbol: string;
  instrument_type: string;
  config: any;
  active: boolean;
  paper_trade: boolean;
  created_at?: string;
}

export interface Trade {
  id: number;
  strategy_id: string;
  instance_id?: number;
  strategy_name?: string;
  symbol: string;
  option_type?: string;
  strike_price?: number;
  expiry?: string;
  quantity: number;
  entry_price: number;
  exit_price?: number;
  entry_time: string;
  exit_time?: string;
  status: string;
  mode: string;
  pnl?: number;
  exit_reason?: string;
}

export interface OptionContract {
  price: number;
  delta: number;
  theta: number;
  vega: number;
}

export interface OptionChainItem {
  strike: number;
  ce: OptionContract;
  pe: OptionContract;
}
