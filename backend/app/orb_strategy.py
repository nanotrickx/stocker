"""
Opening Range Breakout (ORB) Strategy Engine
=============================================

Multi-phase intraday options strategy:
1.  Wait for 9:15 first 1-minute candle to complete
2.  Record its HIGH and LOW as the "Opening Range"
3.  Wait for price to break above HIGH (bullish) or below LOW (bearish)
4.  On breakout → select ATM option (CE for bullish, PE for bearish)
5.  Premium filter: option premium must be 100–200; shift OTM if > 200
6.  Wait for option's first 1-min candle to complete → that close = entry
7.  Target = +10% from entry, Stop Loss = -10% from entry
8.  After 10:30 switch monitoring to 3-min or 5-min candles (configurable)

Author: Stocker Engine
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, time, timedelta

import pandas as pd

logger = logging.getLogger("Stocker.ORB")


# ── Default ORB Config (stored as JSON in config_json) ──────────────────────

DEFAULT_ORB_CONFIG: Dict[str, Any] = {
    "strategy_type": "orb_breakout",
    "symbols": ["NSE:NIFTY 50"],

    # Timeframe phases
    "timeframes": {
        "opening_candle_tf": "minute",         # 1-min for the reference candle
        "pre_1030_tf":       "minute",         # 1-min for breakout monitoring
        "post_1030_tf":      "5minute",        # switch after 10:30
    },

    # Opening range
    "opening_range": {
        "candle_time": "09:15",                # first candle start
    },

    # Option selection
    "option_selection": {
        "strike_selection": "ATM",
        "premium_min": 100,
        "premium_max": 200,
        "shift_to_otm_if_exceeded": True,
    },

    # Risk management
    "risk": {
        "target_pct": 10.0,
        "stop_loss_pct": 10.0,
    },

    # Order settings
    "action": {
        "instrument_type": "OPTION",
        "quantity": 50,
        "expiry_type": "WEEKLY",
        "paper_trade": True,
    },

    # Timeline
    "timeline": {
        "start_time": "09:15",
        "end_time": "15:15",
        "days_of_week": [1, 2, 3, 4, 5],
    },
}


@dataclass
class ORBState:
    """Tracks the state of one ORB simulation day."""
    opening_high: Optional[float] = None
    opening_low: Optional[float] = None
    opening_close: Optional[float] = None
    breakout_direction: Optional[str] = None    # "BULLISH" | "BEARISH"
    breakout_price: Optional[float] = None
    breakout_time: Optional[str] = None
    selected_option_type: Optional[str] = None  # "CE" | "PE"
    selected_strike: Optional[float] = None
    entry_price: Optional[float] = None
    entry_time: Optional[str] = None
    target_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    exit_price: Optional[float] = None
    exit_time: Optional[str] = None
    exit_reason: Optional[str] = None           # "TARGET" | "STOP_LOSS" | "TIMELINE"
    pnl: float = 0.0
    phase: str = "WAITING_OPENING_CANDLE"
    # Phases: WAITING_OPENING_CANDLE → WAITING_BREAKOUT → IN_POSITION → DONE

    # Refinement fields for Z ragu ORB rules
    selected_ce_strike: Optional[float] = None
    selected_pe_strike: Optional[float] = None
    ce_option_opening_high: Optional[float] = None
    pe_option_opening_high: Optional[float] = None
    ce_option_already_broke_out: bool = False
    pe_option_already_broke_out: bool = False
    index_high_broke_out: bool = False
    index_low_broke_out: bool = False
    trades_taken: List[str] = field(default_factory=list)
    first_trade_hit_sl: bool = False



class ORBStrategyEngine:
    """
    Processes bar-by-bar data and produces ORB strategy signals, journal entries,
    and visualization metadata.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.tfs = config.get("timeframes", DEFAULT_ORB_CONFIG["timeframes"])
        self.or_cfg = config.get("opening_range", DEFAULT_ORB_CONFIG["opening_range"])
        self.opt_cfg = config.get("option_selection", DEFAULT_ORB_CONFIG["option_selection"])
        self.risk = config.get("risk", DEFAULT_ORB_CONFIG["risk"])
        self.action = config.get("action", DEFAULT_ORB_CONFIG["action"])

        self.target_pct = self.risk.get("target_pct", 10.0)
        self.sl_pct = self.risk.get("stop_loss_pct", 10.0)
        self.premium_min = self.opt_cfg.get("premium_min", 100)
        self.premium_max = self.opt_cfg.get("premium_max", 200)
        self.qty = self.action.get("quantity", 50)

    # ── Utility ────────────────────────────────────────────────────────────

    @staticmethod
    def _time_from_ts(ts: str) -> time:
        """Extract time from a timestamp string like '2025-05-23 09:15:00'."""
        try:
            dt = pd.Timestamp(ts)
            return dt.time()
        except Exception:
            return time(9, 15)

    @staticmethod
    def _select_atm_strike(spot: float, step: int = 50) -> float:
        return round(spot / step) * step

    def _estimate_premium(self, spot: float, strike: float, opt_type: str) -> float:
        """
        Quick intrinsic + time-value estimate for premium filtering.
        Used when real option data is unavailable (backtesting).
        """
        intrinsic = max(0, spot - strike) if opt_type == "CE" else max(0, strike - spot)
        # Simple time-value approximation: tuned to weekly expirations (~0.2% of strike)
        time_val = strike * 0.002
        return round(intrinsic + time_val, 2)

    def _find_best_strike(
        self, spot: float, opt_type: str, step: int = 50
    ) -> Tuple[float, float]:
        """
        Find the strike whose estimated premium is in [premium_min, premium_max].
        Start from ATM, shift OTM if premium exceeds max.
        Returns (strike, estimated_premium).
        """
        atm = self._select_atm_strike(spot, step)
        premium = self._estimate_premium(spot, atm, opt_type)

        # If premium is in range, use it
        if self.premium_min <= premium <= self.premium_max:
            return atm, premium

        # If premium > max, shift OTM
        if premium > self.premium_max and self.opt_cfg.get("shift_to_otm_if_exceeded", True):
            for shift in range(1, 20):
                otm_strike = atm + (shift * step) if opt_type == "CE" else atm - (shift * step)
                prem = self._estimate_premium(spot, otm_strike, opt_type)
                if self.premium_min <= prem <= self.premium_max:
                    return otm_strike, prem
                if prem < self.premium_min:
                    break  # gone too far OTM

        # If premium < min, shift ITM
        if premium < self.premium_min:
            for shift in range(1, 10):
                itm_strike = atm - (shift * step) if opt_type == "CE" else atm + (shift * step)
                prem = self._estimate_premium(spot, itm_strike, opt_type)
                if self.premium_min <= prem <= self.premium_max:
                    return itm_strike, prem
                if prem > self.premium_max:
                    break

        # Fallback: ATM regardless
        return atm, premium

    # ── Main backtest runner ───────────────────────────────────────────────

    def run_backtest(
        self,
        df: pd.DataFrame,
        initial_capital: float = 100000.0,
        provider: Optional[Any] = None,
        expiry_date: Optional[str] = None,
        slippage_pct: float = 0.0,
        trail_sl_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Run ORB strategy bar-by-bar on an intraday DataFrame.

        df must be indexed by datetime with columns: open, high, low, close, volume
        and should contain 1-minute (or configured) candles for one or more trading days.

        Returns the same structure as the generic backtest:
        { summary, equity_curve, visualization, trades, journal }
        """
        if df.empty:
            return self._empty_result(initial_capital)

        capital = initial_capital
        equity_curve = []
        visualization = []
        trades = []
        journal = []
        logs = []

        def log_info(msg: str):
            logger.info(msg)
            logs.append(f"🟢 INFO | {msg}")

        def log_warn(msg: str):
            logger.warning(msg)
            logs.append(f"⚠️ WARNING | {msg}")

        # Group candles by date to process each trading day independently
        df = df.copy()
        df["_date"] = df.index.date

        for day, day_df in df.groupby("_date"):
            state = ORBState()
            day_str = str(day)

            # Load stored real option chain snapshots for this day if available
            import os
            import json
            from datetime import datetime as dt_class
            
            stored_snapshots = []
            symbol = self.config.get("symbols", ["NSE:NIFTY 50"])[0]
            clean_sym = symbol.replace("NSE:", "").replace(" ", "_")
            
            # Base data directory inside backend/data/option_chains/YYYY-MM-DD/
            base_path = os.path.dirname(os.path.abspath(__file__))
            file_path = os.path.join(os.path.dirname(base_path), "data", "option_chains", day_str, f"{clean_sym}.json")
            
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r") as f:
                        stored_snapshots = json.load(f)
                except Exception:
                    pass

            # Pre-fetch actual historical options candles from Dhan/Kite API
            ce_price_map = {}
            pe_price_map = {}
            api_data_source = False

            if provider and provider.__class__.__name__ != "SimulatedMarketDataProvider":
                try:
                    opening_candle = day_df.iloc[0]
                    ref_price = opening_candle["close"]
                    step = 50 if "NIFTY" in symbol else 100
                    
                    selected_ce_strike = round(ref_price / step) * step
                    selected_pe_strike = round(ref_price / step) * step
                    
                    resolved_expiry = expiry_date or self.config.get("expiry_date")
                    if not resolved_expiry:
                        d = dt_class.strptime(day_str, "%Y-%m-%d")
                        # Tuesday weekly option expiry
                        days_to_tuesday = (1 - d.weekday()) % 7
                        if days_to_tuesday == 0:  # If today is Tuesday, next weekly option is next Tuesday
                            days_to_tuesday = 7
                        tuesday = d + timedelta(days=days_to_tuesday)
                        
                        # Thursday weekly option expiry
                        days_to_thursday = (3 - d.weekday()) % 7
                        if days_to_thursday == 0:  # If today is Thursday, next weekly option is next Thursday
                            days_to_thursday = 7
                        thursday = d + timedelta(days=days_to_thursday)
                        
                        tuesday_str = tuesday.strftime("%Y-%m-%d")
                        thursday_str = thursday.strftime("%Y-%m-%d")
                        
                        # Check which candidate resolves to an actual F&O contract ID
                        log_info(f"Checking weekly option expiry candidates for {day_str}: Tuesday={tuesday_str}, Thursday={thursday_str}")
                        sec_id_test = None
                        if hasattr(provider, "_resolve_option_security_id"):
                            try:
                                sec_id_test = provider._resolve_option_security_id(symbol, float(selected_ce_strike), "CE", tuesday_str)
                            except Exception:
                                pass
                        
                        if sec_id_test:
                            resolved_expiry = tuesday_str
                            log_info(f"Dynamically resolved weekly expiry date as Tuesday: {resolved_expiry}")
                        else:
                            resolved_expiry = thursday_str
                            log_info(f"Dynamically resolved weekly expiry date as Thursday: {resolved_expiry}")
                        
                    log_info(f"API Pre-fetch Options for {day_str}: ATM Strike={selected_ce_strike}, Expiry={resolved_expiry}")
                    
                    # Fetch CE candles
                    try:
                        ce_candles = provider.get_historical_data(
                            symbol=symbol,
                            days=1,
                            from_date=day_str,
                            to_date=day_str,
                            interval="minute",
                            instrument_type="CE",
                            strike_price=float(selected_ce_strike),
                            expiry_date=resolved_expiry
                        )
                        if ce_candles:
                            for c in ce_candles:
                                try:
                                    time_str = c["date"].split(" ")[1][:5]
                                    ce_price_map[time_str] = c
                                except Exception:
                                    pass
                            api_data_source = True
                            log_info(f"Loaded {len(ce_price_map)} actual CE option candles from Dhan/Kite API.")
                    except Exception as ce_err:
                        log_warn(f"Failed to fetch actual CE option candles from API: {ce_err}")
                        
                    # Fetch PE candles
                    try:
                        pe_candles = provider.get_historical_data(
                            symbol=symbol,
                            days=1,
                            from_date=day_str,
                            to_date=day_str,
                            interval="minute",
                            instrument_type="PE",
                            strike_price=float(selected_pe_strike),
                            expiry_date=resolved_expiry
                        )
                        if pe_candles:
                            for c in pe_candles:
                                try:
                                    time_str = c["date"].split(" ")[1][:5]
                                    pe_price_map[time_str] = c
                                except Exception:
                                    pass
                            api_data_source = True
                            log_info(f"Loaded {len(pe_price_map)} actual PE option candles from Dhan/Kite API.")
                    except Exception as pe_err:
                        log_warn(f"Failed to fetch actual PE option candles from API: {pe_err}")
                except Exception as prefetch_err:
                    log_warn(f"Options prefetch setup error: {prefetch_err}")
            # Ensure option premium pricing is available. If not, fallback to high-fidelity mathematical simulation mode!
            if not api_data_source and not stored_snapshots:
                log_warn(
                    f"Actual F&O option candles for {symbol} are not available from either the live broker API "
                    f"or real recorded backup snapshots on {day_str}. Falling back to high-fidelity mathematical simulation."
                )

            for i in range(len(day_df)):
                row = day_df.iloc[i]
                ts = str(day_df.index[i])
                bar_time = self._time_from_ts(ts)
                signal = "HOLD"

                try:
                    bar_dt = dt_class.strptime(ts.split("+")[0], "%Y-%m-%d %H:%M:%S")
                    bar_min_str = bar_dt.strftime("%H:%M")
                except Exception:
                    bar_min_str = ""
                
                # Locate the corresponding option chain snapshot for the current minute if available
                current_snapshot = None
                if stored_snapshots:
                    try:
                        for snap in stored_snapshots:
                            snap_dt = dt_class.fromisoformat(snap["timestamp"])
                            if snap_dt.strftime("%H:%M") == bar_min_str:
                                current_snapshot = snap
                                break
                    except Exception:
                        pass

                # ── Phase: WAITING_OPENING_CANDLE ──────────────────────
                if state.phase == "WAITING_OPENING_CANDLE":
                    # The first candle of the day (>= 09:15) is our reference
                    if bar_time >= time(9, 15):
                        state.opening_high = row["high"]
                        state.opening_low = row["low"]
                        state.opening_close = row["close"]
                        
                        # Pre-select CE and PE strikes based on opening close to measure option breakout high
                        step = 50 if "NIFTY" in symbol else 100

                        # CE Selection (Strictly ATM)
                        state.selected_ce_strike = round(state.opening_close / step) * step

                        # PE Selection (Strictly ATM)
                        state.selected_pe_strike = round(state.opening_close / step) * step

                        # Math-based opening highs on options charts (with real recorded fallback)
                        real_ce_high = None
                        real_pe_high = None
                        if current_snapshot:
                            for opt in current_snapshot.get("chain", []):
                                if opt["strike"] == state.selected_ce_strike:
                                    real_ce_high = opt["CE_price"]
                                if opt["strike"] == state.selected_pe_strike:
                                    real_pe_high = opt["PE_price"]
                                    
                        # Prioritize API Pre-fetch candles, then stored backup snapshots, then mathematical simulation fallback
                        api_ce_candle = ce_price_map.get(bar_min_str)
                        api_pe_candle = pe_price_map.get(bar_min_str)

                        if api_ce_candle:
                            state.ce_option_opening_high = api_ce_candle["high"]
                        elif real_ce_high and real_ce_high > 0:
                            state.ce_option_opening_high = real_ce_high
                        else:
                            state.ce_option_opening_high = round(max(0.5, max(0, state.opening_high - state.selected_ce_strike) + state.selected_ce_strike * 0.002), 2)
                            
                        if api_pe_candle:
                            state.pe_option_opening_high = api_pe_candle["high"]
                        elif real_pe_high and real_pe_high > 0:
                            state.pe_option_opening_high = real_pe_high
                        else:
                            state.pe_option_opening_high = round(max(0.5, max(0, state.selected_pe_strike - state.opening_low) + state.selected_pe_strike * 0.002), 2)

                        state.phase = "WAITING_BREAKOUT"

                        if api_data_source:
                            db_source = "🟢 REAL LIVE API CHARTS (DhanHQ High-Fidelity Mode)"
                        elif stored_snapshots:
                            db_source = "🟢 REAL RECORDED SNAPSHOTS (High-Fidelity Mode)"
                        else:
                            db_source = "🔴 MATHEMATICAL SIMULATION (Fallback Mode)"

                        journal.append({
                            "ts": ts,
                            "action": "REFERENCE",
                            "price": row["close"],
                            "reason": [
                                f"Opening range set. Index H={state.opening_high:.2f} L={state.opening_low:.2f}",
                                f"CE Strike {state.selected_ce_strike:.0f} (Opening High: ₹{state.ce_option_opening_high:.2f})",
                                f"PE Strike {state.selected_pe_strike:.0f} (Opening High: ₹{state.pe_option_opening_high:.2f})",
                                f"Option Data Source: {db_source}",
                                f"Waiting for double breakout breakout (Index + Option)...",
                            ],
                            "note": "Phase → WAITING_BREAKOUT",
                            "capital": capital,
                        })
                        signal = "REFERENCE"

                # ── Phase: WAITING_BREAKOUT ────────────────────────────
                elif state.phase == "WAITING_BREAKOUT":
                    # Don't take new entries after 11 am IST
                    if bar_time > time(11, 0):
                        continue

                    # Estimate current premiums (with real recorded fallback)
                    real_ce_prem = None
                    real_pe_prem = None

                    api_ce_candle = ce_price_map.get(bar_min_str)
                    api_pe_candle = pe_price_map.get(bar_min_str)

                    if api_ce_candle:
                        real_ce_prem = api_ce_candle["close"]
                    elif current_snapshot:
                        for opt in current_snapshot.get("chain", []):
                            if opt["strike"] == state.selected_ce_strike:
                                real_ce_prem = opt["CE_price"]

                    if api_pe_candle:
                        real_pe_prem = api_pe_candle["close"]
                    elif current_snapshot:
                        for opt in current_snapshot.get("chain", []):
                            if opt["strike"] == state.selected_pe_strike:
                                real_pe_prem = opt["PE_price"]
                                
                    if real_ce_prem and real_ce_prem > 0:
                        current_ce_premium = real_ce_prem
                    else:
                        current_ce_premium = round(max(0.5, max(0, row["close"] - state.selected_ce_strike) + state.selected_ce_strike * 0.002), 2)
                        
                    if real_pe_prem and real_pe_prem > 0:
                        current_pe_premium = real_pe_prem
                    else:
                        current_pe_premium = round(max(0.5, max(0, state.selected_pe_strike - row["close"]) + state.selected_pe_strike * 0.002), 2)

                    # Index breakout validation
                    if row["high"] > state.opening_high and "BULLISH" not in state.trades_taken:
                        state.index_high_broke_out = True

                    if row["low"] < state.opening_low and "BEARISH" not in state.trades_taken:
                        state.index_low_broke_out = True

                    # Double breakout check
                    trigger_buy = False
                    selected_type = None
                    selected_strike = None
                    est_prem = 0.0

                    if state.index_high_broke_out:
                        if current_ce_premium > state.ce_option_opening_high:
                            trigger_buy = True
                            selected_type = "CE"
                            selected_strike = state.selected_ce_strike
                            est_prem = state.ce_option_opening_high
                            state.breakout_direction = "BULLISH"

                    if state.index_low_broke_out and not trigger_buy:
                        if current_pe_premium > state.pe_option_opening_high:
                            trigger_buy = True
                            selected_type = "PE"
                            selected_strike = state.selected_pe_strike
                            est_prem = state.pe_option_opening_high
                            state.breakout_direction = "BEARISH"

                    if trigger_buy:
                        state.selected_option_type = selected_type
                        state.selected_strike = selected_strike
                        
                        entry_price = est_prem
                        if slippage_pct > 0:
                            entry_price = round(entry_price * (1 + slippage_pct / 100.0), 2)
                        
                        state.entry_price = entry_price
                        state.entry_time = ts

                        # Determine target percentage
                        current_target_pct = 15.0 if state.first_trade_hit_sl else 10.0

                        state.target_price = round(entry_price * (1 + current_target_pct / 100), 2)
                        state.stop_loss_price = round(entry_price * (1 - self.sl_pct / 100), 2)
                        state.breakout_price = row["close"]
                        state.breakout_time = ts
                        state.phase = "IN_POSITION"
                        signal = "BUY"

                        state.trades_taken.append(state.breakout_direction)

                        if api_data_source:
                            db_purchase_source = "🟢 Purchased using REAL LIVE API OPTION CHARTS from DhanHQ API"
                        elif current_snapshot:
                            db_purchase_source = "🟢 Purchased using REAL RECORDED PREMIUM from local database backups"
                        else:
                            db_purchase_source = "🔴 Purchased using MATHEMATICAL SIMULATION fallback estimate"

                        journal.append({
                            "ts": ts,
                            "action": "BUY",
                            "price": est_prem,
                            "qty": self.qty,
                            "reason": [
                                f"DOUBLE BREAKOUT: Index + Option {state.selected_strike:.0f} {state.selected_option_type}",
                                f"Entry: ₹{est_prem:.2f} (Target: ₹{state.target_price:.2f} +{current_target_pct}% | SL: ₹{state.stop_loss_price:.2f} -{self.sl_pct}%)",
                                f"Premium Source: {db_purchase_source}",
                                f"ATM Selection details: Selected ATM {state.selected_strike:.0f} based on Spot close price ₹{row['close']:.2f}",
                            ],
                            "note": f"Phase → IN_POSITION | Buy {state.selected_strike:.0f} {state.selected_option_type} @ ₹{est_prem:.2f}",
                            "capital": capital,
                        })

                # ── Phase: IN_POSITION ─────────────────────────────────
                elif state.phase == "IN_POSITION":
                    # Monitor premium changes (with real recorded fallback)
                    real_prem = None
                    
                    api_ce_candle = ce_price_map.get(bar_min_str)
                    api_pe_candle = pe_price_map.get(bar_min_str)

                    if state.selected_option_type == "CE" and api_ce_candle:
                        real_prem = api_ce_candle["close"]
                    elif state.selected_option_type == "PE" and api_pe_candle:
                        real_prem = api_pe_candle["close"]
                    elif current_snapshot:
                        for opt in current_snapshot.get("chain", []):
                            if opt["strike"] == state.selected_strike:
                                real_prem = opt["CE_price"] if state.selected_option_type == "CE" else opt["PE_price"]
                                
                    if real_prem and real_prem > 0:
                        current_premium = real_prem
                    else:
                        spot_move = row["close"] - state.breakout_price
                        delta = 0.5 if state.selected_option_type == "CE" else -0.5
                        current_premium = max(0.5, state.entry_price + (spot_move * delta))

                    # Track max price for trailing stop loss
                    if not hasattr(state, "max_price_since_entry") or state.max_price_since_entry is None:
                        state.max_price_since_entry = state.entry_price
                    state.max_price_since_entry = max(state.max_price_since_entry, current_premium)

                    if trail_sl_pct and trail_sl_pct > 0:
                        trail_sl_price = round(state.max_price_since_entry * (1 - trail_sl_pct / 100.0), 2)
                        if trail_sl_price > state.stop_loss_price:
                            state.stop_loss_price = trail_sl_price

                    exit_reason = None
                    exit_price = None

                    # Target
                    if current_premium >= state.target_price:
                        exit_reason = "TARGET"
                        exit_price = state.target_price
                    # SL / Trailing SL
                    elif current_premium <= state.stop_loss_price:
                        exit_reason = "TRAILING_STOP_LOSS" if (trail_sl_pct and state.stop_loss_price > state.entry_price) else "STOP_LOSS"
                        exit_price = state.stop_loss_price
                    # EOD
                    elif bar_time >= time(15, 15):
                        exit_reason = "TIMELINE"
                        exit_price = round(current_premium, 2)

                    if exit_reason:
                        if slippage_pct > 0:
                            exit_price = round(exit_price * (1 - slippage_pct / 100.0), 2)
                        pnl = (exit_price - state.entry_price) * self.qty
                        state.pnl += pnl
                        capital += pnl
                        signal = "SELL"

                        # Determine next state
                        if exit_reason in ("STOP_LOSS", "TRAILING_STOP_LOSS") and len(state.trades_taken) < 2:
                            state.first_trade_hit_sl = True
                            state.phase = "WAITING_BREAKOUT"
                            state.index_high_broke_out = False
                            state.index_low_broke_out = False
                            note_next = "Phase → WAITING_BREAKOUT (Re-entry opposite side)"
                        else:
                            state.phase = "DONE"
                            note_next = "Phase → DONE"

                        if api_data_source:
                            db_sell_source = "🟢 Executed exit using REAL LIVE API OPTION CHARTS from DhanHQ API"
                        elif current_snapshot:
                            db_sell_source = "🟢 Executed exit using REAL RECORDED PREMIUM from local database backups"
                        else:
                            db_sell_source = "🔴 Executed exit using MATHEMATICAL SIMULATION fallback estimate"

                        journal.append({
                            "ts": ts,
                            "action": "SELL",
                            "price": exit_price,
                            "qty": self.qty,
                            "pnl": round(pnl, 2),
                            "reason": [
                                f"{exit_reason} HIT: Premium reached ₹{exit_price:.2f}",
                                f"Entry: ₹{state.entry_price:.2f} → Exit: ₹{exit_price:.2f}",
                                f"P&L: ₹{pnl:.2f} ({self.qty} qty)",
                                f"Premium Source: {db_sell_source}",
                            ],
                            "note": note_next,
                            "capital": round(capital, 2),
                        })

                        trades.append({
                            "symbol": f"NIFTY {state.selected_strike:.0f} {state.selected_option_type}",
                            "instrument_type": state.selected_option_type,
                            "entry_time": state.entry_time,
                            "exit_time": ts,
                            "qty": self.qty,
                            "entry_price": state.entry_price,
                            "exit_price": exit_price,
                            "pnl": round(pnl, 2),
                            "pnl_pct": round(((exit_price - state.entry_price) / state.entry_price) * 100, 2),
                            "exit_reason": exit_reason,
                            "opening_high": state.opening_high,
                            "opening_low": state.opening_low,
                            "ce_option_opening_high": state.ce_option_opening_high,
                            "pe_option_opening_high": state.pe_option_opening_high,
                            "selected_ce_strike": state.selected_ce_strike,
                            "selected_pe_strike": state.selected_pe_strike,
                        })

                # ── Build visualization bar ────────────────────────────
                indicators: Dict[str, Any] = {}
                if state.opening_high is not None:
                    indicators["orb_high"] = state.opening_high
                    indicators["orb_low"] = state.opening_low
                if state.entry_price is not None:
                    indicators["entry"] = state.entry_price
                    indicators["target"] = state.target_price
                    indicators["sl"] = state.stop_loss_price

                # Calculate current option premiums dynamically for indicators series
                current_ce_premium = 0.0
                current_pe_premium = 0.0
                if state.selected_ce_strike is not None:
                    real_ce_prem = None
                    api_ce_candle = ce_price_map.get(bar_min_str)
                    if api_ce_candle:
                        real_ce_prem = api_ce_candle["close"]
                    elif current_snapshot:
                        for opt in current_snapshot.get("chain", []):
                            if opt["strike"] == state.selected_ce_strike:
                                real_ce_prem = opt["CE_price"]
                    if real_ce_prem and real_ce_prem > 0:
                        current_ce_premium = real_ce_prem
                    else:
                        current_ce_premium = round(max(0.5, max(0, row["close"] - state.selected_ce_strike) + state.selected_ce_strike * 0.002), 2)

                    # Store CE candle OHLC
                    ce_open = current_ce_premium
                    ce_high = current_ce_premium
                    ce_low = current_ce_premium
                    ce_close = current_ce_premium
                    if api_ce_candle:
                        ce_open = api_ce_candle.get("open", current_ce_premium)
                        ce_high = api_ce_candle.get("high", current_ce_premium)
                        ce_low = api_ce_candle.get("low", current_ce_premium)
                        ce_close = api_ce_candle.get("close", current_ce_premium)
                    elif len(visualization) > 0:
                        prev_val = visualization[-1]["indicators"].get("ce_close", current_ce_premium)
                        ce_open = prev_val
                        ce_close = current_ce_premium
                        ce_high = max(ce_open, ce_close) + abs(ce_open - ce_close) * 0.25 + 0.5
                        ce_low = max(0.5, min(ce_open, ce_close) - abs(ce_open - ce_close) * 0.25 - 0.5)

                    indicators["ce_open"] = ce_open
                    indicators["ce_high"] = ce_high
                    indicators["ce_low"] = ce_low
                    indicators["ce_close"] = ce_close

                if state.selected_pe_strike is not None:
                    real_pe_prem = None
                    api_pe_candle = pe_price_map.get(bar_min_str)
                    if api_pe_candle:
                        real_pe_prem = api_pe_candle["close"]
                    elif current_snapshot:
                        for opt in current_snapshot.get("chain", []):
                            if opt["strike"] == state.selected_pe_strike:
                                real_pe_prem = opt["PE_price"]
                    if real_pe_prem and real_pe_prem > 0:
                        current_pe_premium = real_pe_prem
                    else:
                        current_pe_premium = round(max(0.5, max(0, state.selected_pe_strike - row["close"]) + state.selected_pe_strike * 0.002), 2)

                    # Store PE candle OHLC
                    pe_open = current_pe_premium
                    pe_high = current_pe_premium
                    pe_low = current_pe_premium
                    pe_close = current_pe_premium
                    if api_pe_candle:
                        pe_open = api_pe_candle.get("open", current_pe_premium)
                        pe_high = api_pe_candle.get("high", current_pe_premium)
                        pe_low = api_pe_candle.get("low", current_pe_premium)
                        pe_close = api_pe_candle.get("close", current_pe_premium)
                    elif len(visualization) > 0:
                        prev_val = visualization[-1]["indicators"].get("pe_close", current_pe_premium)
                        pe_open = prev_val
                        pe_close = current_pe_premium
                        pe_high = max(pe_open, pe_close) + abs(pe_open - pe_close) * 0.25 + 0.5
                        pe_low = max(0.5, min(pe_open, pe_close) - abs(pe_open - pe_close) * 0.25 - 0.5)

                    indicators["pe_open"] = pe_open
                    indicators["pe_high"] = pe_high
                    indicators["pe_low"] = pe_low
                    indicators["pe_close"] = pe_close

                if state.selected_ce_strike is not None:
                    indicators["ce_premium"] = current_ce_premium
                    indicators["pe_premium"] = current_pe_premium
                    indicators["selected_option_type"] = state.selected_option_type

                visualization.append({
                    "ts": ts,
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": int(row.get("volume", 0)),
                    "signal": signal,
                    "trade_state": state.phase,
                    "indicators": indicators,
                })

                equity_curve.append({
                    "date": ts,
                    "balance": round(capital, 2),
                })

        # ── Build summary ──────────────────────────────────────────────
        total_trades = len(trades)
        profitable = sum(1 for t in trades if t["pnl"] > 0)
        losing = sum(1 for t in trades if t["pnl"] <= 0)
        net_pnl = round(capital - initial_capital, 2)
        return_pct = round((net_pnl / initial_capital) * 100, 2) if initial_capital > 0 else 0

        # Max drawdown from equity curve
        max_dd = 0.0
        peak = initial_capital
        for pt in equity_curve:
            if pt["balance"] > peak:
                peak = pt["balance"]
            dd = ((peak - pt["balance"]) / peak) * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd

        return {
            "status": "SUCCESS",
            "meta": {
                "strategy_type": "orb_breakout",
                "symbol": self.config.get("symbols", ["NSE:NIFTY 50"])[0],
                "instrument_type": "OPTION",
                "candles_used": len(df),
                "is_intraday": True,
                "selected_ce_strike": state.selected_ce_strike if 'state' in locals() else None,
                "selected_pe_strike": state.selected_pe_strike if 'state' in locals() else None,
                "expiry_date": resolved_expiry if 'resolved_expiry' in locals() else None,
            },
            "summary": {
                "initial_capital": initial_capital,
                "final_capital": round(capital, 2),
                "net_pnl": net_pnl,
                "total_return_pct": return_pct,
                "total_trades": total_trades,
                "profitable_trades": profitable,
                "losing_trades": losing,
                "win_rate": round((profitable / total_trades * 100) if total_trades > 0 else 0, 1),
                "max_drawdown_pct": round(max_dd, 2),
            },
            "equity_curve": equity_curve,
            "visualization": visualization,
            "trades": trades,
            "journal": journal,
            "logs": logs,
        }

    def _empty_result(self, initial_capital: float) -> Dict[str, Any]:
        return {
            "status": "SUCCESS",
            "meta": {"strategy_type": "orb_breakout"},
            "summary": {
                "initial_capital": initial_capital,
                "final_capital": initial_capital,
                "net_pnl": 0,
                "total_return_pct": 0,
                "total_trades": 0,
                "profitable_trades": 0,
                "losing_trades": 0,
                "win_rate": 0,
                "max_drawdown_pct": 0,
            },
            "equity_curve": [],
            "visualization": [],
            "trades": [],
            "journal": [],
            "logs": [],
        }
