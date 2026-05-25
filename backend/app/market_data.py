"""
Kite Connect v3 Historical Data Provider
Docs: https://kite.trade/docs/connect/v3/historical/

Endpoint: GET /instruments/historical/{instrument_token}/{interval}
Params:
  from       - yyyy-mm-dd hh:mm:ss  (start of range)
  to         - yyyy-mm-dd hh:mm:ss  (end of range)
  continuous - 0|1  (for futures continuity)
  oi         - 0|1  (include open interest in response)

Response candle format: [timestamp, open, high, low, close, volume]
With oi=1:             [timestamp, open, high, low, close, volume, oi]
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, date
import logging
import requests

logger = logging.getLogger("Stocker.MarketData")

KITE_BASE = "https://api.kite.trade"

# ── Static instrument token map for common symbols ──────────────────────────
SYMBOL_TOKENS: Dict[str, int] = {
    "NSE:NIFTY 50":    256265,
    "NSE:NIFTY BANK":  260105,
    "NSE:SENSEX":      265,
    "NSE:RELIANCE":    738561,
    "NSE:TCS":         2953217,
    "NSE:INFY":        408065,
    "NSE:HDFC":        340481,
    "NSE:HDFCBANK":    341249,
    "NSE:ICICIBANK":   1270529,
    "NSE:SBIN":        779521,
    "NSE:WIPRO":       969473,
    "NSE:TATAMOTORS":  884737,
    "NSE:BAJFINANCE":  81153,
    "NSE:MARUTI":      2815745,
    "NSE:AXISBANK":    1510401,
    "NSE:KOTAKBANK":   492033,
    "NSE:LTIM":        3351553,
    "NSE:SUNPHARMA":   857857,
    "NSE:HINDUNILVR":  356865,
    "NSE:ITC":         424961,
}

# Valid Kite v3 intervals
VALID_INTERVALS = {
    "minute", "3minute", "5minute", "10minute",
    "15minute", "30minute", "60minute", "day",
}

# Market hours (IST)
MARKET_OPEN  = "09:15:00"
MARKET_CLOSE = "15:30:00"


class BaseMarketDataProvider(ABC):
    @abstractmethod
    def get_historical_data(
        self,
        symbol: str,
        days: int = 30,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        interval: str = "day",
        **kwargs,
    ) -> List[Dict[str, Any]]:
        pass


class KiteMarketDataProvider(BaseMarketDataProvider):
    """
    Real Kite Connect v3 historical data — no mock fallback.
    Uses direct HTTP calls so date/time formatting is fully controlled.
    """

    def __init__(self, api_key: str, access_token: str):
        self.api_key      = api_key
        self.access_token = access_token
        self._headers = {
            "X-Kite-Version": "3",
            "Authorization":  f"token {api_key}:{access_token}",
        }

    # ── Token resolution ────────────────────────────────────────────────────

    def _get_token(self, symbol: str) -> Optional[int]:
        """Resolve instrument token from static map or live instrument search."""
        if symbol in SYMBOL_TOKENS:
            return SYMBOL_TOKENS[symbol]

        # Live lookup via instruments CSV
        try:
            parts    = symbol.split(":")
            exchange = parts[0] if len(parts) == 2 else "NSE"
            ticker   = parts[-1]

            resp = requests.get(
                f"{KITE_BASE}/instruments/{exchange}",
                headers=self._headers,
                timeout=15,
            )
            resp.raise_for_status()
            # CSV: instrument_token,exchange_token,tradingsymbol,...
            for line in resp.text.splitlines()[1:]:
                cols = line.split(",")
                if len(cols) > 2 and cols[2] == ticker:
                    return int(cols[0])
        except Exception as e:
            logger.warning(f"Instrument token live lookup failed for {symbol}: {e}")

        return None

    def _get_option_token(
        self,
        underlying: str,
        strike: float,
        option_type: str,      # CE or PE
        expiry_date: Optional[str],
    ) -> Optional[int]:
        """Resolve NFO option instrument token."""
        try:
            resp = requests.get(
                f"{KITE_BASE}/instruments/NFO",
                headers=self._headers,
                timeout=20,
            )
            resp.raise_for_status()

            # underlying name pattern: NIFTY 50 → NIFTY, NIFTY BANK → BANKNIFTY
            name = underlying.split(":")[-1].upper()
            name_map = {
                "NIFTY 50":   "NIFTY",
                "NIFTY BANK": "BANKNIFTY",
                "SENSEX":     "SENSEX",
            }
            name = name_map.get(name, name.replace(" ", ""))

            target_expiry = None
            if expiry_date:
                target_expiry = datetime.strptime(expiry_date, "%Y-%m-%d").date()

            candidates = []
            for line in resp.text.splitlines()[1:]:
                cols = line.split(",")
                if len(cols) < 9:
                    continue
                token     = int(cols[0])
                inst_name = cols[3]           # name column
                inst_type = cols[9]           # instrument_type
                exp_str   = cols[5]           # expiry
                inst_strike = float(cols[6] or 0)

                if (name in inst_name and
                        inst_type.upper() == option_type.upper() and
                        abs(inst_strike - strike) < 1.0):
                    try:
                        exp = datetime.strptime(exp_str, "%Y-%m-%d").date()
                    except Exception:
                        continue
                    candidates.append((token, exp))

            if not candidates:
                return None

            today = date.today()
            if target_expiry:
                candidates.sort(key=lambda x: abs((x[1] - target_expiry).days))
            else:
                # nearest future expiry
                candidates = [(t, e) for t, e in candidates if e >= today]
                candidates.sort(key=lambda x: x[1])

            return candidates[0][0] if candidates else None

        except Exception as e:
            logger.warning(f"Option token lookup failed: {e}")
            return None

    # ── Core fetch method ────────────────────────────────────────────────────

    def get_historical_data(
        self,
        symbol: str,
        days: int = 30,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        interval: str = "day",
        instrument_type: str = "STOCK",
        strike_price: Optional[float] = None,
        expiry_date: Optional[str] = None,
        continuous: bool = False,
        include_oi: bool = False,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Fetch OHLCV candles from Kite v3 historical API.

        Date formats accepted in from_date / to_date:
          - "YYYY-MM-DD"           → auto-appends market hours for intraday
          - "YYYY-MM-DD HH:MM:SS"  → used as-is
        """
        # ── Validate interval ──────────────────────────────────────────
        if interval not in VALID_INTERVALS:
            raise RuntimeError(
                f"Invalid interval '{interval}'. "
                f"Valid options: {sorted(VALID_INTERVALS)}"
            )

        is_intraday = interval != "day"

        # ── Build date range ───────────────────────────────────────────
        def _fmt(d_str: str, is_start: bool) -> str:
            """Ensure datetime string has HH:MM:SS component."""
            if " " in d_str or "T" in d_str:
                return d_str.replace("T", " ")
            # date-only: append market open/close
            return f"{d_str} {MARKET_OPEN if is_start else MARKET_CLOSE}"

        now = datetime.now()
        if to_date:
            to_dt   = _fmt(to_date, False)
        else:
            to_dt   = now.strftime("%Y-%m-%d") + f" {MARKET_CLOSE}"

        if from_date:
            from_dt = _fmt(from_date, True)
        else:
            fd       = (now - timedelta(days=days)).strftime("%Y-%m-%d")
            from_dt  = f"{fd} {MARKET_OPEN}"

        logger.info(
            f"Kite historical fetch: {symbol} [{instrument_type}] "
            f"interval={interval} from={from_dt} to={to_dt}"
        )

        # ── Resolve instrument token ────────────────────────────────────
        if instrument_type.upper() in ("CE", "PE"):
            if strike_price is None:
                raise RuntimeError("strike_price is required for option backtests.")
            token = self._get_option_token(symbol, strike_price, instrument_type, expiry_date)
            if not token:
                raise RuntimeError(
                    f"Could not resolve NFO option token for "
                    f"{symbol} {strike_price} {instrument_type} expiry={expiry_date}"
                )
        else:
            token = self._get_token(symbol)
            if not token:
                raise RuntimeError(
                    f"Could not resolve instrument token for symbol '{symbol}'. "
                    f"Check the symbol name or add it to SYMBOL_TOKENS."
                )

        # ── Call Kite v3 /instruments/historical/{token}/{interval} ────
        url    = f"{KITE_BASE}/instruments/historical/{token}/{interval}"
        params: Dict[str, Any] = {
            "from":       from_dt,
            "to":         to_dt,
            "continuous": 1 if continuous else 0,
            "oi":         1 if include_oi else 0,
        }

        try:
            resp = requests.get(url, params=params, headers=self._headers, timeout=30)
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Network error while fetching Kite historical data: {e}")

        if resp.status_code != 200:
            raise RuntimeError(
                f"Kite API error {resp.status_code}: {resp.text[:300]}"
            )

        body = resp.json()
        if body.get("status") != "success":
            raise RuntimeError(
                f"Kite API returned status={body.get('status')}: "
                f"{body.get('message', body)}"
            )

        raw_candles: List[List] = body.get("data", {}).get("candles", [])

        if not raw_candles:
            raise RuntimeError(
                f"Kite returned 0 candles for {symbol} "
                f"({from_dt} → {to_dt}, interval={interval}). "
                f"The market may have been closed on that day, "
                f"or the date range falls outside available data."
            )

        logger.info(f"Received {len(raw_candles)} candles from Kite for {symbol}")

        # ── Parse response ─────────────────────────────────────────────
        # Format: [timestamp, open, high, low, close, volume] or [..., oi]
        result = []
        for c in raw_candles:
            ts = c[0]
            # Kite timestamps: "2017-12-15T09:15:00+0530"
            if isinstance(ts, str):
                # Normalise to readable format
                ts_clean = ts.replace("T", " ").split("+")[0].split(".")[0]
            else:
                ts_clean = str(ts)

            candle: Dict[str, Any] = {
                "date":   ts_clean,
                "open":   float(c[1]),
                "high":   float(c[2]),
                "low":    float(c[3]),
                "close":  float(c[4]),
                "volume": int(c[5]) if len(c) > 5 else 0,
            }
            if include_oi and len(c) > 6:
                candle["oi"] = int(c[6])

            result.append(candle)

        return result


# ── Simulated provider (engine tick loop only — never used in backtest) ──────

class SimulatedMarketDataProvider(BaseMarketDataProvider):
    """Used only by the live engine tick loop when no Kite session exists."""

    def get_historical_data(
        self,
        symbol: str,
        days: int = 30,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        interval: str = "day",
        **kwargs,
    ) -> List[Dict[str, Any]]:
        import random
        logger.info(f"[SIM] Generating {days} mock candles for {symbol}")
        data  = []
        base  = 22000.0 if "NIFTY" in symbol else (150.0 if "INFY" in symbol else 2500.0)
        curr  = datetime.now() - timedelta(days=days)
        random.seed(42)

        for _ in range(days):
            chg   = random.uniform(-100, 115) if "NIFTY" in symbol else random.uniform(-4, 5)
            op, cl = base, base + chg
            data.append({
                "date":   curr.strftime("%Y-%m-%d"),
                "open":   round(op, 2),
                "high":   round(max(op, cl) + random.uniform(5, 45), 2),
                "low":    round(min(op, cl) - random.uniform(5, 45), 2),
                "close":  round(cl, 2),
                "volume": random.randint(100000, 900000),
            })
            base  = cl
            curr += timedelta(days=1)

        return data
