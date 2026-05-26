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

        # Group candles by date to process each trading day independently
        df = df.copy()
        df["_date"] = df.index.date

        for day, day_df in df.groupby("_date"):
            state = ORBState()
            day_str = str(day)

            for i in range(len(day_df)):
                row = day_df.iloc[i]
                ts = str(day_df.index[i])
                bar_time = self._time_from_ts(ts)
                signal = "HOLD"

                # ── Phase: WAITING_OPENING_CANDLE ──────────────────────
                if state.phase == "WAITING_OPENING_CANDLE":
                    # The first candle of the day (>= 09:15) is our reference
                    if bar_time >= time(9, 15):
                        state.opening_high = row["high"]
                        state.opening_low = row["low"]
                        state.opening_close = row["close"]
                        
                        # Pre-select CE and PE strikes based on opening close to measure option breakout high
                        step = 50 if "NIFTY" in self.config.get("symbols", ["NSE:NIFTY 50"])[0] else 100

                        # CE Selection
                        ce_atm, ce_est = self._find_best_strike(state.opening_close, "CE", step)
                        state.selected_ce_strike = ce_atm

                        # PE Selection
                        pe_atm, pe_est = self._find_best_strike(state.opening_close, "PE", step)
                        state.selected_pe_strike = pe_atm

                        # Math-based opening highs on options charts
                        state.ce_option_opening_high = round(max(0.5, max(0, state.opening_high - state.selected_ce_strike) + state.selected_ce_strike * 0.002), 2)
                        state.pe_option_opening_high = round(max(0.5, max(0, state.selected_pe_strike - state.opening_low) + state.selected_pe_strike * 0.002), 2)

                        state.phase = "WAITING_BREAKOUT"

                        journal.append({
                            "ts": ts,
                            "action": "REFERENCE",
                            "price": row["close"],
                            "reason": [
                                f"Opening range set. Index H={state.opening_high:.2f} L={state.opening_low:.2f}",
                                f"CE Strike {state.selected_ce_strike:.0f} (Opening High: ₹{state.ce_option_opening_high:.2f})",
                                f"PE Strike {state.selected_pe_strike:.0f} (Opening High: ₹{state.pe_option_opening_high:.2f})",
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

                    # Estimate current premiums
                    current_ce_premium = round(max(0.5, max(0, row["close"] - state.selected_ce_strike) + state.selected_ce_strike * 0.002), 2)
                    current_pe_premium = round(max(0.5, max(0, state.selected_pe_strike - row["close"]) + state.selected_pe_strike * 0.002), 2)

                    # Option breakout before index did check
                    if row["high"] <= state.opening_high and current_ce_premium > state.ce_option_opening_high:
                        if not state.ce_option_already_broke_out:
                            state.ce_option_already_broke_out = True
                            journal.append({
                                "ts": ts,
                                "action": "ALERT",
                                "price": current_ce_premium,
                                "reason": [f"CE Option broke out above ₹{state.ce_option_opening_high:.2f} before Index. CE entry invalidated."],
                                "note": "CE Invalidated",
                                "capital": capital
                            })

                    if row["low"] >= state.opening_low and current_pe_premium > state.pe_option_opening_high:
                        if not state.pe_option_already_broke_out:
                            state.pe_option_already_broke_out = True
                            journal.append({
                                "ts": ts,
                                "action": "ALERT",
                                "price": current_pe_premium,
                                "reason": [f"PE Option broke out above ₹{state.pe_option_opening_high:.2f} before Index. PE entry invalidated."],
                                "note": "PE Invalidated",
                                "capital": capital
                            })

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

                    if state.index_high_broke_out and not state.ce_option_already_broke_out:
                        if current_ce_premium > state.ce_option_opening_high:
                            trigger_buy = True
                            selected_type = "CE"
                            selected_strike = state.selected_ce_strike
                            est_prem = current_ce_premium
                            state.breakout_direction = "BULLISH"

                    if state.index_low_broke_out and not state.pe_option_already_broke_out and not trigger_buy:
                        if current_pe_premium > state.pe_option_opening_high:
                            trigger_buy = True
                            selected_type = "PE"
                            selected_strike = state.selected_pe_strike
                            est_prem = current_pe_premium
                            state.breakout_direction = "BEARISH"

                    if trigger_buy:
                        state.selected_option_type = selected_type
                        state.selected_strike = selected_strike
                        state.entry_price = est_prem
                        state.entry_time = ts

                        # Determine target percentage
                        current_target_pct = 15.0 if state.first_trade_hit_sl else 10.0

                        state.target_price = round(est_prem * (1 + current_target_pct / 100), 2)
                        state.stop_loss_price = round(est_prem * (1 - self.sl_pct / 100), 2)
                        state.breakout_price = row["close"]
                        state.breakout_time = ts
                        state.phase = "IN_POSITION"
                        signal = "BUY"

                        state.trades_taken.append(state.breakout_direction)

                        journal.append({
                            "ts": ts,
                            "action": "BUY",
                            "price": est_prem,
                            "qty": self.qty,
                            "reason": [
                                f"DOUBLE BREAKOUT: Index + Option {state.selected_strike:.0f} {state.selected_option_type}",
                                f"Entry: ₹{est_prem:.2f} (Target: ₹{state.target_price:.2f} +{current_target_pct}% | SL: ₹{state.stop_loss_price:.2f} -{self.sl_pct}%)",
                            ],
                            "note": f"Phase → IN_POSITION | Buy {state.selected_strike:.0f} {state.selected_option_type} @ ₹{est_prem:.2f}",
                            "capital": capital,
                        })

                # ── Phase: IN_POSITION ─────────────────────────────────
                elif state.phase == "IN_POSITION":
                    spot_move = row["close"] - state.breakout_price
                    delta = 0.5 if state.selected_option_type == "CE" else -0.5
                    current_premium = max(0.5, state.entry_price + (spot_move * delta))

                    exit_reason = None
                    exit_price = None

                    # Target
                    if current_premium >= state.target_price:
                        exit_reason = "TARGET"
                        exit_price = state.target_price
                    # SL
                    elif current_premium <= state.stop_loss_price:
                        exit_reason = "STOP_LOSS"
                        exit_price = state.stop_loss_price
                    # EOD
                    elif bar_time >= time(15, 15):
                        exit_reason = "TIMELINE"
                        exit_price = round(current_premium, 2)

                    if exit_reason:
                        pnl = (exit_price - state.entry_price) * self.qty
                        state.pnl += pnl
                        capital += pnl
                        signal = "SELL"

                        # Determine next state
                        if exit_reason == "STOP_LOSS" and len(state.trades_taken) < 2:
                            state.first_trade_hit_sl = True
                            state.phase = "WAITING_BREAKOUT"
                            state.index_high_broke_out = False
                            state.index_low_broke_out = False
                            note_next = "Phase → WAITING_BREAKOUT (Re-entry opposite side)"
                        else:
                            state.phase = "DONE"
                            note_next = "Phase → DONE"

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
        }
