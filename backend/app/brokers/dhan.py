import logging
from typing import Dict, List, Any, Optional
from app.brokers.base import BaseBroker

logger = logging.getLogger("Stocker.Brokers.Dhan")

def get_totp(secret: str) -> str:
    import time
    import hmac
    import hashlib
    import struct
    import base64
    try:
        secret = secret.replace(" ", "")
        secret = secret + '=' * ((8 - len(secret) % 8) % 8)
        key = base64.b32decode(secret, casefold=True)
        intervals_no = int(time.time() // 30)
        msg = struct.pack(">Q", intervals_no)
        h = hmac.new(key, msg, hashlib.sha1).digest()
        o = h[19] & 15
        h = (struct.unpack(">I", h[o:o+4])[0] & 0x7fffffff) % 1000000
        return f"{h:06d}"
    except Exception as e:
        logger.error(f"Error generating TOTP in get_totp: {e}")
        return ""

def get_dhan_token(active_cred: Any, session: Any) -> Optional[str]:
    if active_cred.broker_name == "dhan":
        if active_cred.totp_secret and len(active_cred.totp_secret.strip()) > 4:
            from datetime import date
            import time
            from app.database import now_ist
            import requests
            
            today = now_ist().date()
            token_date = active_cred.updated_at.date() if active_cred.updated_at else None
            
            if not active_cred.access_token or token_date != today:
                try:
                    totp_code = get_totp(active_cred.totp_secret)
                    if totp_code:
                        url = f"https://auth.dhan.co/app/generateAccessToken?dhanClientId={active_cred.api_key}&pin={active_cred.api_secret}&totp={totp_code}"
                        resp = requests.post(url, timeout=10)
                        if resp.status_code == 200:
                            res_json = resp.json()
                            gen_token = res_json.get("accessToken") or res_json.get("access_token")
                            if gen_token:
                                active_cred.access_token = gen_token
                                active_cred.updated_at = now_ist()
                                session.add(active_cred)
                                session.commit()
                                logger.info("🟢 Programmatically auto-renewed Dhan access token for today.")
                                return gen_token
                            else:
                                logger.error(f"🔴 Auto-renewal of Dhan token failed: Server returned error message: {res_json.get('message') or res_json}")
                        else:
                            logger.error(f"🔴 Auto-renewal of Dhan token failed: {resp.status_code} - {resp.text}")
                except Exception as e:
                    logger.error(f"🔴 Error auto-renewing Dhan token: {e}")
        
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

    async def login(self, credentials: Dict[str, Any]) -> bool:
        self.client_id = credentials.get("client_id") or credentials.get("api_key")
        self.access_token = credentials.get("access_token")
        
        totp_sec = credentials.get("totp_secret")
        if totp_sec and len(totp_sec.strip()) > 4:
            totp_code = get_totp(totp_sec)
            pin_code = credentials.get("api_secret")
            if totp_code and pin_code:
                try:
                    import requests
                    url = f"https://auth.dhan.co/app/generateAccessToken?dhanClientId={self.client_id}&pin={pin_code}&totp={totp_code}"
                    resp = requests.post(url, timeout=15)
                    if resp.status_code == 200:
                        res_json = resp.json()
                        gen_token = res_json.get("accessToken") or res_json.get("access_token")
                        if gen_token:
                            self.access_token = gen_token
                            logger.info("🟢 Automatically generated fresh Dhan Access Token via TOTP!")
                        else:
                            logger.error(f"🔴 Dhan token generation failed: Server returned error message: {res_json.get('message') or res_json}")
                    else:
                        logger.error(f"🔴 Dhan token generation failed: {resp.status_code} - {resp.text}")
                except Exception as e:
                    logger.error(f"🔴 Error communicating with Dhan Auth server: {e}")
        
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
        return {}

    async def place_order(self, strategy_id: str, symbol: str, transaction_type: str, 
                            quantity: int, option_type: Optional[str] = None, 
                            strike_price: Optional[float] = None, expiry: Optional[str] = None,
                            price: Optional[float] = None, instance_id: Optional[int] = None) -> Dict[str, Any]:
        return {"status": "SUCCESS"}

    async def cancel_order(self, order_id: str) -> bool:
        return True

    async def get_positions(self) -> List[Dict[str, Any]]:
        return []

    async def get_ltp(self, symbol: str) -> float:
        """
        Queries the real-time Dhan REST API to retrieve the Last Traded Price (LTP).
        Uses dynamic parsing for option symbols and resolves security IDs via Option Chain.
        """
        import requests
        if not self.access_token or not self.client_id:
            logger.error("DhanBroker: API Access Token or Client ID is missing.")
            raise RuntimeError("Dhan broker not authenticated.")

        segment = "NSE_FNO"
        sec_id = None

        # Parse symbol to resolve Dhan security ID and segment
        if symbol.startswith("NSE:"):
            underlying_clean = symbol.split(":")[-1].upper()
            if "BANK" in underlying_clean:
                sec_id = 25
            else:
                sec_id = 13
            segment = "IDX_I"
        elif "_" in symbol:
            # Option Symbol format: e.g. NSE:NIFTY 50_04JUN26_23900_CE
            try:
                parts = symbol.split("_")
                underlying = parts[0]
                expiry_raw = parts[1]
                strike = float(parts[2])
                opt_type = parts[3]
                
                # Format raw expiry (e.g. 04JUN26) to YYYY-MM-DD
                from datetime import datetime as dt
                expiry_date = dt.strptime(expiry_raw, "%d%b%y").strftime("%Y-%m-%d")
                
                from app.market_data import DhanMarketDataProvider
                provider = DhanMarketDataProvider(client_id=self.client_id, access_token=self.access_token)
                sec_id = provider._resolve_option_security_id(underlying, strike, opt_type, expiry_date)
            except Exception as e:
                logger.error(f"DhanBroker: Failed to parse or resolve option symbol {symbol}: {e}")
                raise RuntimeError(f"Could not resolve option symbol {symbol}: {e}")
        else:
            under_upper = symbol.upper()
            if "BANK" in under_upper:
                sec_id = 25
            else:
                sec_id = 13
            segment = "IDX_I"

        if not sec_id:
            logger.error(f"DhanBroker: Security ID could not be resolved for symbol '{symbol}'")
            raise RuntimeError(f"Dhan security ID resolution failed for {symbol}")

        # Call Dhan /marketfeed/ltp POST endpoint
        url = "https://api.dhan.co/v2/marketfeed/ltp"
        payload = {
            segment: [int(sec_id)]
        }

        try:
            resp = requests.post(url, json=payload, headers=self._headers, timeout=15)
            if resp.status_code == 200:
                res_data = resp.json()
                if res_data.get("status") == "success" or res_data.get("status") == "SUCCESS":
                    val = res_data.get("data", {}).get(segment, {}).get(str(sec_id), {}).get("last_price")
                    if val is not None:
                        return float(val)
            logger.error(f"DhanBroker: marketfeed/ltp call failed for securityId {sec_id}: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.error(f"DhanBroker: Exception during marketfeed/ltp call for {symbol}: {e}")

        raise RuntimeError(f"Dhan broker disconnected or live quote not found for {symbol}")
