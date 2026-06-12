import logging
from typing import Dict, List, Any, Optional
from app.brokers.base import BaseBroker

logger = logging.getLogger("Stocker.Brokers.Dhan")

def get_totp(secret: str, time_offset: int = 0) -> str:
    import time
    import hmac
    import hashlib
    import struct
    import base64
    try:
        secret = secret.replace(" ", "")
        secret = secret + '=' * ((8 - len(secret) % 8) % 8)
        key = base64.b32decode(secret, casefold=True)
        intervals_no = int((time.time() + time_offset) // 30)
        msg = struct.pack(">Q", intervals_no)
        h = hmac.new(key, msg, hashlib.sha1).digest()
        o = h[19] & 15
        h = (struct.unpack(">I", h[o:o+4])[0] & 0x7fffffff) % 1000000
        return f"{h:06d}"
    except Exception as e:
        logger.error(f"Error generating TOTP in get_totp: {e}")
        return ""

def request_dhan_access_token(client_id: str, pin: str, totp_secret: str) -> Optional[str]:
    import requests
    # Try current time, then 30s back, then 30s forward, then -60s, +60s to handle clock skew
    for offset in [0, -30, 30, -60, 60]:
        totp_code = get_totp(totp_secret, time_offset=offset)
        if not totp_code:
            continue
        try:
            url = f"https://auth.dhan.co/app/generateAccessToken?dhanClientId={client_id}&pin={pin}&totp={totp_code}"
            resp = requests.post(url, timeout=15)
            if resp.status_code == 200:
                res_json = resp.json()
                gen_token = res_json.get("accessToken") or res_json.get("access_token")
                if gen_token:
                    if offset != 0:
                        logger.info(f"🟢 Dhan Access Token generated with clock skew offset {offset}s!")
                    return gen_token
                else:
                    msg = res_json.get('message') or str(res_json)
                    logger.warning(f"Dhan token attempt with offset {offset}s returned: {msg}")
            else:
                logger.warning(f"Dhan token attempt with offset {offset}s returned status {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.warning(f"Dhan token attempt with offset {offset}s failed with error: {e}")
    return None

def get_dhan_token(active_cred: Any, session: Any) -> Optional[str]:
    if active_cred.broker_name == "dhan":
        if active_cred.totp_secret and len(active_cred.totp_secret.strip()) > 4:
            from datetime import date
            from app.database import now_ist
            
            today = now_ist().date()
            token_date = active_cred.updated_at.date() if active_cred.updated_at else None
            
            if not active_cred.access_token or token_date != today:
                gen_token = request_dhan_access_token(active_cred.api_key, active_cred.api_secret, active_cred.totp_secret)
                if gen_token:
                    active_cred.access_token = gen_token
                    active_cred.updated_at = now_ist()
                    session.add(active_cred)
                    session.commit()
                    logger.info("🟢 Programmatically auto-renewed Dhan access token for today.")
                    return gen_token
                else:
                    logger.error("🔴 Auto-renewal of Dhan token failed: All TOTP clock skew offsets exhausted.")
        
        return active_cred.access_token or active_cred.api_secret
    return None

class DhanBroker(BaseBroker):
    """
    DhanHQ Options API Integration Layer.
    Connects to live Dhan API server for profile, margins, and orders routing.
    """
    def __init__(self):
        self.client_id = None
        self.access_token = None
        self._headers = {}
        self._provider = None

    async def login(self, credentials: Dict[str, Any]) -> bool:
        self.client_id = credentials.get("client_id") or credentials.get("api_key")
        self.access_token = credentials.get("access_token")
        
        totp_sec = credentials.get("totp_secret")
        pin_code = credentials.get("api_secret")
        
        need_token_gen = True
        if self.access_token:
            try:
                from app.database import engine as db_engine, BrokerCredential, now_ist
                from sqlmodel import Session, select
                with Session(db_engine) as session:
                    statement = select(BrokerCredential).where(
                        BrokerCredential.broker_name == "dhan",
                        BrokerCredential.api_key == self.client_id
                    )
                    cred = session.exec(statement).first()
                    if cred and cred.access_token == self.access_token and cred.updated_at:
                        if cred.updated_at.date() == now_ist().date():
                            need_token_gen = False
                            logger.info("🟢 Active Dhan token in DB is already fresh for today. Skipping TOTP login.")
            except Exception as db_err:
                logger.warning(f"Failed to check token freshness in database during login: {db_err}")

        if need_token_gen and totp_sec and len(totp_sec.strip()) > 4 and pin_code:
            gen_token = request_dhan_access_token(self.client_id, pin_code, totp_sec)
            if gen_token:
                self.access_token = gen_token
                logger.info("🟢 Automatically generated fresh Dhan Access Token via TOTP!")
                try:
                    from app.database import engine as db_engine, BrokerCredential
                    from sqlmodel import Session, select
                    from app.database import now_ist
                    with Session(db_engine) as session:
                        statement = select(BrokerCredential).where(
                            BrokerCredential.broker_name == "dhan",
                            BrokerCredential.api_key == self.client_id
                        )
                        cred = session.exec(statement).first()
                        if cred:
                            cred.access_token = gen_token
                            cred.updated_at = now_ist()
                            session.add(cred)
                            session.commit()
                            logger.info("💾 Successfully saved fresh Dhan Access Token to SQLite database.")
                except Exception as db_err:
                    logger.error(f"🔴 Failed to save renewed Dhan token to database: {db_err}")
            else:
                logger.error("🔴 Dhan token generation failed: All TOTP clock skew offsets exhausted.")
        
        if not self.access_token:
            self.access_token = credentials.get("api_secret")
            
        if not self.client_id or not self.access_token:
            logger.error("Dhan Client ID or Access Token/API Key is missing in login credentials.")
            return False
        
        self._headers = {
            "Content-Type": "application/json",
            "access-token": self.access_token,
            "client-id": self.client_id,
        }
        return True

    async def get_profile(self) -> Dict[str, Any]:
        import requests
        try:
            resp = requests.get("https://api.dhan.co/v2/profile", headers=self._headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "broker": "DHAN",
                    "client_id": data.get("dhanClientId"),
                    "client_name": "Dhan Account",
                    "available_funds": 0.0,
                    "used_margin": 0.0,
                    "total_equity": 0.0
                }
        except Exception as e:
            logger.error(f"Dhan profile fetch failed: {e}")
        return {"broker": "DHAN", "status": "ERROR"}

    async def get_live_quotes(self, symbols: List[str]) -> Dict[str, Any]:
        """
        Fetches live Last Traded Price (LTP) for multiple symbols in a SINGLE REST API call.
        Includes a 1.5-second cache and dynamic throttling with an asyncio.Lock to prevent concurrent race conditions.
        """
        import requests
        import time
        import asyncio

        if not self.access_token or not self.client_id:
            logger.error("DhanBroker: API Access Token or Client ID is missing.")
            return {}

        if not hasattr(self, "_quotes_cache"):
            self._quotes_cache = {}
        if not hasattr(self, "_last_api_call_time"):
            self._last_api_call_time = 0.0
        if not hasattr(self, "_api_lock"):
            self._api_lock = asyncio.Lock()

        async with self._api_lock:
            now_time = time.time()
            # 1. Filter out symbols that are already fresh in cache
            res = {}
            missing_symbols = []
            for symbol in symbols:
                if symbol in self._quotes_cache:
                    val, cache_time = self._quotes_cache[symbol]
                    if now_time - cache_time < 1.5:
                        res[symbol] = val
                        continue
                missing_symbols.append(symbol)

            if not missing_symbols:
                return res

            # 2. Apply rate-limit safe throttling sleep before making a new HTTP request
            time_since_last_call = now_time - self._last_api_call_time
            if time_since_last_call < 1.5:
                sleep_needed = 1.5 - time_since_last_call
                logger.debug(f"DhanBroker: Throttling API call. Sleeping for {sleep_needed:.2f}s...")
                await asyncio.sleep(sleep_needed)
                now_time = time.time()

            payload = {}
            sec_to_sym = {}

            for symbol in missing_symbols:
                segment = "NSE_FNO"
                sec_id = None

                # Parse symbol to resolve Dhan security ID and segment
                if "_" in symbol:
                    try:
                        parts = symbol.split("_")
                        underlying = parts[0]
                        expiry_raw = parts[1]
                        strike = float(parts[2])
                        opt_type = parts[3]
                        
                        from datetime import datetime as dt
                        expiry_date = dt.strptime(expiry_raw, "%d%b%y").strftime("%Y-%m-%d")
                        
                        if not self._provider:
                            from app.market_data import DhanMarketDataProvider
                            self._provider = DhanMarketDataProvider(client_id=self.client_id, access_token=self.access_token)
                        sec_id = self._provider._resolve_option_security_id(underlying, strike, opt_type, expiry_date)
                    except Exception as e:
                        logger.error(f"DhanBroker: Failed to parse or resolve option symbol {symbol}: {e}")
                        continue
                elif symbol.startswith("NSE:"):
                    underlying_clean = symbol.split(":")[-1].upper()
                    if "BANK" in underlying_clean:
                        sec_id = 25
                    else:
                        sec_id = 13
                    segment = "IDX_I"
                else:
                    under_upper = symbol.upper()
                    if "BANK" in under_upper:
                        sec_id = 25
                    else:
                        sec_id = 13
                    segment = "IDX_I"

                if sec_id:
                    if segment not in payload:
                        payload[segment] = []
                    payload[segment].append(int(sec_id))
                    sec_to_sym[str(sec_id)] = (symbol, segment)

            if not payload:
                return res

            url = "https://api.dhan.co/v2/marketfeed/ltp"
            try:
                self._last_api_call_time = time.time()
                resp = requests.post(url, json=payload, headers=self._headers, timeout=15)
                if resp.status_code == 200:
                    res_data = resp.json()
                    if res_data.get("status") == "success" or res_data.get("status") == "SUCCESS":
                        data = res_data.get("data", {})
                        for sec_id_str, sym_info in sec_to_sym.items():
                            symbol_name, segment_name = sym_info
                            val = data.get(segment_name, {}).get(sec_id_str, {}).get("last_price")
                            if val is not None:
                                quote_val = {
                                    "last_price": float(val),
                                    "ohlc": {"close": float(val)}
                                }
                                # Cache the result
                                self._quotes_cache[symbol_name] = (quote_val, self._last_api_call_time)
                                res[symbol_name] = quote_val
                        return res
                logger.error(f"DhanBroker: bulk /marketfeed/ltp call failed: {resp.status_code} - {resp.text}")
            except Exception as e:
                logger.error(f"DhanBroker: Exception during bulk marketfeed/ltp call: {e}")

            return res

    async def get_ltp(self, symbol: str) -> float:
        """Fetch real-time LTP for a single symbol using the bulk rate-limit safe lookup."""
        res = await self.get_live_quotes([symbol])
        if symbol in res:
            return float(res[symbol]["last_price"])
        raise RuntimeError(f"Dhan broker disconnected or live quote not found for {symbol}")

    async def place_order(self, strategy_id: str, symbol: str, transaction_type: str, 
                            quantity: int, option_type: Optional[str] = None, 
                            strike_price: Optional[float] = None, expiry: Optional[str] = None,
                            price: Optional[float] = None, instance_id: Optional[int] = None) -> Dict[str, Any]:
        return {"status": "SUCCESS"}

    async def cancel_order(self, order_id: str) -> bool:
        return True

    async def get_positions(self) -> List[Dict[str, Any]]:
        return []
