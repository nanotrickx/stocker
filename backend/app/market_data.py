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
    """Disabled and deprecated to enforce live broker data only."""

    def __init__(self, *args, **kwargs):
        raise RuntimeError("SimulatedMarketDataProvider is disabled to enforce live broker data only.")

    def get_historical_data(self, *args, **kwargs) -> List[Dict[str, Any]]:
        raise RuntimeError("SimulatedMarketDataProvider is disabled to enforce live broker data only.")



class DhanMarketDataProvider(BaseMarketDataProvider):
    """
    Real DhanHQ v2 historical F&O data provider.
    Enables true historical backtests by querying Dhan's high-fidelity charts API.
    """

    def __init__(self, client_id: str, access_token: str):
        self.client_id = client_id
        self.access_token = access_token
        self._headers = {
            "Content-Type": "application/json",
            "access-token": access_token,
            "client-id": client_id,
        }

    def _resolve_option_security_id(
        self,
        underlying: str,
        strike: float,
        option_type: str,
        expiry_date: str,
    ) -> Optional[int]:
        """Query live Dhan Option Chain to retrieve the target F&O contract Security ID."""
        try:
            # Map index name to Dhan underlying scrip ID
            underlying_clean = underlying.split(":")[-1].upper()
            if "BANK" in underlying_clean:
                under_id = 25
            else:
                under_id = 13  # Default Nifty 50

            # Ensure format is YYYY-MM-DD as strictly expected by Dhan option chain API
            try:
                dt_obj = datetime.strptime(expiry_date, "%Y-%m-%d")
                expiry_date = dt_obj.strftime("%Y-%m-%d")
            except Exception:
                # If already in DD-MMM-YYYY or another format, try parsing and converting to YYYY-MM-DD
                try:
                    dt_obj = datetime.strptime(expiry_date, "%d-%b-%Y")
                    expiry_date = dt_obj.strftime("%Y-%m-%d")
                except Exception:
                    pass

            cache_key = (under_id, expiry_date)
            if not hasattr(self, "_option_chain_cache"):
                self._option_chain_cache = {}

            if cache_key in self._option_chain_cache:
                chain_list = self._option_chain_cache[cache_key]
            else:
                import time
                time.sleep(1.0)
                url = "https://api.dhan.co/v2/optionchain"
                payload = {
                    "UnderlyingScrip": under_id,
                    "UnderlyingSeg": "IDX_I",
                    "Expiry": expiry_date
                }

                resp = requests.post(url, json=payload, headers=self._headers, timeout=15)
                if resp.status_code != 200:
                    logger.warning(f"Dhan Option Chain API failed: {resp.text}")
                    return None

                data = resp.json()
                inner_data = data.get("data", {})
                
                # Normalize to list of option details
                chain_list = []
                if isinstance(inner_data, dict):
                    oc_dict = inner_data.get("oc", {})
                    if isinstance(oc_dict, dict):
                        for strike_str, strike_data in oc_dict.items():
                            try:
                                strike_val = float(strike_str)
                                chain_list.append({
                                    "strike": strike_val,
                                    "CE": strike_data.get("ce", {}),
                                    "PE": strike_data.get("pe", {})
                                })
                            except Exception:
                                pass
                    else:
                        # Fallback to check if inner_data itself is a list
                        chain_list = inner_data if isinstance(inner_data, list) else []
                elif isinstance(inner_data, list):
                    chain_list = inner_data
                
                if chain_list:
                    self._option_chain_cache[cache_key] = chain_list

            if not chain_list:
                logger.warning(f"Dhan Option Chain API returned error or invalid format: {data if 'data' in locals() else 'None'}")
                return None

            for item in chain_list:
                # Check target strike
                strike_diff = abs(float(item.get("strike", 0)) - strike)
                if strike_diff < 1.0:
                    # Resolve CE or PE contract ID
                    opt_details = item.get(option_type.upper()) or item.get(option_type.lower())
                    if isinstance(opt_details, dict):
                        sec_id = opt_details.get("securityId") or opt_details.get("security_id")
                        if sec_id:
                            return int(sec_id)

        except Exception as e:
            logger.warning(f"Dhan F&O Security ID resolution failed: {e}")
        return None

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
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """Fetch high-fidelity OHLCV candles from Dhan charts API."""
        # 1. Resolve securityId
        if instrument_type.upper() in ("CE", "PE"):
            if not expiry_date:
                raise RuntimeError("expiry_date is strictly required for Dhan options data fetching.")
            sec_id = self._resolve_option_security_id(symbol, strike_price, instrument_type, expiry_date)
            if not sec_id:
                raise RuntimeError(
                    f"Could not resolve Dhan F&O contract securityId for {symbol} "
                    f"{strike_price} {instrument_type} expiry={expiry_date}"
                )
            segment = "NSE_FNO"
            inst_param = "OPTIDX"
        else:
            # Underlying Index or Equity (Default mapping: Nifty 50 -> 13, Bank Nifty -> 25)
            underlying_clean = symbol.split(":")[-1].upper()
            if "BANK" in underlying_clean:
                sec_id = 25
            else:
                sec_id = 13
            segment = "IDX_I"
            inst_param = "INDEX"

        # 2. Build date strings
        # Dhan takes YYYY-MM-DD
        fd = from_date.split(" ")[0] if from_date else (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        td = to_date.split(" ")[0] if to_date else datetime.now().strftime("%Y-%m-%d")

        # 3. Call Dhan Charts API
        is_intraday = interval != "day"
        endpoint = "intraday" if is_intraday else "historical"
        url = f"https://api.dhan.co/v2/charts/{endpoint}"

        payload = {
            "securityId": str(sec_id),
            "exchangeSegment": segment,
            "instrument": inst_param,
            "expiryCode": 0,
            "oi": False,
            "fromDate": fd,
            "toDate": td
        }

        try:
            resp = requests.post(url, json=payload, headers=self._headers, timeout=25)
            if resp.status_code != 200:
                raise RuntimeError(f"Dhan Charts API Error {resp.status_code}: {resp.text}")

            body = resp.json()
            # Format is columnar: {"open": [...], "high": [...], "low": [...], "close": [...], "volume": [...], "timestamp": [...]}
            if not body or "timestamp" not in body or not body["timestamp"]:
                logger.warning(f"Dhan Charts API returned empty data for {symbol} ({fd} to {td})")
                return []

            result = []
            size = len(body["timestamp"])
            for idx in range(size):
                ts = body["timestamp"][idx]
                try:
                    if ts > 1000000000:
                        dt = datetime.fromtimestamp(ts)
                    else:
                        dt = datetime(1980, 1, 1) + timedelta(seconds=ts)
                except Exception:
                    dt = datetime.now()

                result.append({
                    "date": dt.strftime("%Y-%m-%d %H:%M:%S" if is_intraday else "%Y-%m-%d"),
                    "open": float(body["open"][idx]),
                    "high": float(body["high"][idx]),
                    "low": float(body["low"][idx]),
                    "close": float(body["close"][idx]),
                    "volume": int(body.get("volume", [0] * size)[idx]),
                })

            logger.info(f"Successfully loaded {len(result)} real high-fidelity options candles from Dhan.")
            return result

        except Exception as e:
            raise RuntimeError(f"Dhan API historical data call failed: {e}")
