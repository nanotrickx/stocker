import math
import logging
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
import pandas_ta_classic as ta

logger = logging.getLogger("Stocker.Analytics")

# ---------------------------------------------------------
# Black-Scholes Pricing & Greeks Engine
# ---------------------------------------------------------

def norm_cdf(x: float) -> float:
    """Cumulative distribution function for standard normal distribution."""
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0

def norm_pdf(x: float) -> float:
    """Probability density function for standard normal distribution."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)

def calculate_greeks(
    spot: float,
    strike: float,
    days_to_expiry: float,
    volatility: float,
    rate: float = 0.07,  # Default risk-free rate (7% typical in India)
    option_type: str = "CE"
) -> Dict[str, float]:
    """
    Computes Black-Scholes Option Price and Greeks (Delta, Gamma, Theta, Vega).
    - days_to_expiry: time left in days (will be converted to fraction of a year)
    - volatility: Implied Volatility as a fraction (e.g., 0.15 for 15%)
    """
    if days_to_expiry <= 0:
        # Intrinsic value at expiration
        intrinsic = max(0.0, spot - strike) if option_type.upper() == "CE" else max(0.0, strike - spot)
        return {
            "price": intrinsic,
            "delta": 1.0 if (option_type.upper() == "CE" and spot > strike) else (
                -1.0 if (option_type.upper() == "PE" and spot < strike) else 0.0
            ),
            "gamma": 0.0,
            "theta": 0.0,
            "vega": 0.0
        }

    T = days_to_expiry / 365.0
    r = rate
    sigma = max(volatility, 0.0001)  # Avoid division by zero

    d1 = (math.log(spot / strike) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    if option_type.upper() == "CE":
        price = spot * norm_cdf(d1) - strike * math.exp(-r * T) * norm_cdf(d2)
        delta = norm_cdf(d1)
        # Theta for Call
        theta = -(spot * norm_pdf(d1) * sigma) / (2 * math.sqrt(T)) - r * strike * math.exp(-r * T) * norm_cdf(d2)
    else:  # PE Option
        price = strike * math.exp(-r * T) * norm_cdf(-d2) - spot * norm_cdf(-d1)
        delta = norm_cdf(d1) - 1.0
        # Theta for Put
        theta = -(spot * norm_pdf(d1) * sigma) / (2 * math.sqrt(T)) + r * strike * math.exp(-r * T) * norm_cdf(-d2)

    # Gamma and Vega are identical for Calls and Puts
    gamma = norm_pdf(d1) / (spot * sigma * math.sqrt(T))
    vega = spot * math.sqrt(T) * norm_pdf(d1)

    # Return annualized theta scaled down to daily theta
    return {
        "price": round(price, 2),
        "delta": round(delta, 3),
        "gamma": round(gamma, 5),
        "theta": round(theta / 365.0, 3),
        "vega": round(vega / 100.0, 3)  # Normalized to 1% volatility change
    }

def calculate_implied_volatility(
    market_price: float,
    spot: float,
    strike: float,
    days_to_expiry: float,
    rate: float = 0.07,
    option_type: str = "CE"
) -> float:
    """
    Finds Implied Volatility using Newton-Raphson / Bisection method.
    """
    if days_to_expiry <= 0 or market_price <= 0:
        return 0.0

    # Numerical approximation range
    low_vol = 0.0001
    high_vol = 4.0
    iterations = 100
    precision = 1e-4

    for _ in range(iterations):
        mid_vol = (low_vol + high_vol) / 2.0
        greeks = calculate_greeks(spot, strike, days_to_expiry, mid_vol, rate, option_type)
        diff = greeks["price"] - market_price

        if abs(diff) < precision:
            return round(mid_vol * 100, 2)  # Return as percentage (e.g. 15.42)

        if diff > 0:
            high_vol = mid_vol
        else:
            low_vol = mid_vol

    return round(((low_vol + high_vol) / 2.0) * 100, 2)


# ---------------------------------------------------------
# Technical Indicators Engine
# ---------------------------------------------------------

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Injects EMA, VWAP, RSI, MACD, Bollinger Bands, and Supertrend
    into an OHLC dataset using pandas-ta.
    - Expects df to have standard columns: 'open', 'high', 'low', 'close', 'volume'
    """
    if df.empty or len(df) < 30:
        return df

    # Make copy to avoid editing original
    df = df.copy()
    
    # Simple check for required columns
    df.columns = [c.lower() for c in df.columns]

    # Calculate EMAs
    df['ema_9'] = ta.ema(df['close'], length=9)
    df['ema_20'] = ta.ema(df['close'], length=20)
    df['ema_50'] = ta.ema(df['close'], length=50)
    df['ema_200'] = ta.ema(df['close'], length=200)

    # RSI
    df['rsi'] = ta.rsi(df['close'], length=14)

    # MACD
    macd_res = ta.macd(df['close'], fast=12, slow=26, signal=9)
    if macd_res is not None:
        df['macd'] = macd_res['MACD_12_26_9']
        df['macd_signal'] = macd_res['MACDs_12_26_9']
        df['macd_hist'] = macd_res['MACDh_12_26_9']

    # Bollinger Bands
    bb_res = ta.bbands(df['close'], length=20, std=2)
    if bb_res is not None:
        df['bb_lower'] = bb_res['BBL_20_2.0']
        df['bb_mid'] = bb_res['BBM_20_2.0']
        df['bb_upper'] = bb_res['BBU_20_2.0']

    # VWAP (if volume is present)
    if 'volume' in df.columns and (df['volume'] > 0).any():
        df['vwap'] = ta.vwap(high=df['high'], low=df['low'], close=df['close'], volume=df['volume'])
    else:
        df['vwap'] = df['close']  # fallback

    # Supertrend
    try:
        st_res = ta.supertrend(high=df['high'], low=df['low'], close=df['close'], period=7, multiplier=3)
        if st_res is not None:
            df['supertrend'] = st_res['SUPERT_7_3.0']
            df['supertrend_dir'] = st_res['SUPERTd_7_3.0']  # 1 for bullish, -1 for bearish
    except Exception as e:
        logger.warning(f"Supertrend calculation failed: {e}")
        df['supertrend'] = df['close']
        df['supertrend_dir'] = 1

    return df


# ---------------------------------------------------------
# Dynamic Condition Evaluator
# ---------------------------------------------------------

def check_rule_condition(condition: Dict[str, Any], last_row: pd.Series, prev_row: pd.Series, df: Optional[pd.DataFrame] = None) -> bool:
    """
    Evaluates a custom logic rule condition against the data points,
    supporting indicator lookback offsets.
    """
    # 1. Resolve row positions
    row_t = last_row
    row_prev = prev_row
    
    offset = int(condition.get("offset", 0))
    target_offset = int(condition.get("target_offset", 0))
    
    # If df is provided, retrieve historical offset rows
    if df is not None and not df.empty:
        try:
            # Series name is the index value (timestamp)
            idx_name = last_row.name
            if idx_name in df.index:
                idx_pos = df.index.get_loc(idx_name)
                
                # Check bounds
                if idx_pos - offset >= 0:
                    row_t = df.iloc[idx_pos - offset]
                else:
                    return False  # not enough history for main offset
                    
                if idx_pos - offset - 1 >= 0:
                    row_prev = df.iloc[idx_pos - offset - 1]
                else:
                    return False  # not enough history for main prev offset
        except Exception as bounds_err:
            logger.warning(f"Error resolving offset index positions in check_rule_condition: {bounds_err}")
            
    # Resolve target row values
    row_tgt = last_row
    row_tgt_prev = prev_row
    if df is not None and not df.empty:
        try:
            idx_name = last_row.name
            if idx_name in df.index:
                idx_pos = df.index.get_loc(idx_name)
                if idx_pos - target_offset >= 0:
                    row_tgt = df.iloc[idx_pos - target_offset]
                else:
                    return False
                if idx_pos - target_offset - 1 >= 0:
                    row_tgt_prev = df.iloc[idx_pos - target_offset - 1]
                else:
                    return False
        except Exception:
            pass

    # Helper to resolve field name
    def get_field_val(row: pd.Series, indicator_name: str, period: Optional[int]) -> float:
        name_lower = indicator_name.lower()
        if name_lower == "close":
            return float(row["close"])
        elif name_lower == "rsi":
            return float(row.get("rsi", 50))
        elif name_lower == "ema":
            p = period or 9
            return float(row.get(f"ema_{p}", row["close"]))
        elif name_lower == "vwap":
            return float(row.get("vwap", row["close"]))
        elif name_lower == "supertrend":
            return float(row.get("supertrend", row["close"]))
        return float(row.get(name_lower, row["close"]))

    try:
        ind = condition.get("indicator", "CLOSE")
        p1 = condition.get("period")
        comparison = condition.get("comparison", "GREATER_THAN").upper()
        
        current_val = get_field_val(row_t, ind, p1)
        prev_val = get_field_val(row_prev, ind, p1)

        # Resolve target value
        target_type = condition.get("target", "VALUE").upper()
        if target_type == "VALUE":
            target_val = float(condition.get("value", 0.0))
            prev_target_val = target_val
        else:
            target_ind = condition.get("target_indicator", "EMA")
            p2 = condition.get("target_period")
            target_val = get_field_val(row_tgt, target_ind, p2)
            prev_target_val = get_field_val(row_tgt_prev, target_ind, p2)

        # Apply comparison operator
        if comparison == "GREATER_THAN":
            return current_val > target_val
        elif comparison == "LESS_THAN":
            return current_val < target_val
        elif comparison == "EQUALS":
            return math.isclose(current_val, target_val, rel_tol=1e-5)
        elif comparison == "CROSS_ABOVE":
            # Current is above, previous was below or equal
            return prev_val <= prev_target_val and current_val > target_val
        elif comparison == "CROSS_BELOW":
            # Current is below, previous was above or equal
            return prev_val >= prev_target_val and current_val < target_val

    except Exception as e:
        logger.error(f"Error checking rule condition: {e} | Condition: {condition}")
        return False

    return False
