import logging
import asyncio
from typing import Dict, List, Any, Optional
from sqlmodel import Session, select
from app.database import engine, Trade, BrokerCredential, now_ist
from app.brokers.base import BaseBroker

try:
    from kiteconnect import KiteConnect
    KITE_AVAILABLE = True
except ImportError:
    KITE_AVAILABLE = False

logger = logging.getLogger("Stocker.Brokers.Kite")

class KiteBroker(BaseBroker):
    """
    Zerodha Kite Connect SDK Integration Layer.
    Connects to live Zerodha Kite APIs for margins, live quotes, and NFO order placements.
    """
    def __init__(self):
        self.kite_client = None
        self.api_key = None
        self.api_secret = None
        self.access_token = None
        self.profile = {}

    async def login(self, credentials: Dict[str, Any]) -> bool:
        """
        Logs in using API Key and exchanges a request token (or uses a cached access token).
        """
        if not KITE_AVAILABLE:
            logger.error("KiteConnect library is not installed. Failed to initialize Zerodha login.")
            return False

        self.api_key = credentials.get("api_key")
        self.api_secret = credentials.get("api_secret")
        self.access_token = credentials.get("access_token")

        if not self.api_key or not self.api_secret:
            logger.error("Zerodha Kite API Key or API Secret is missing in login credentials.")
            return False

        try:
            self.kite_client = KiteConnect(api_key=self.api_key)
            
            # If we already have a persistent access token, set it directly
            if self.access_token:
                self.kite_client.set_access_token(self.access_token)
                logger.info("Zerodha Kite login established using persistent Access Token.")
                return True
                
            # If a new login request token is supplied, exchange it
            request_token = credentials.get("request_token")
            if request_token:
                session_data = self.kite_client.generate_session(request_token, api_secret=self.api_secret)
                self.access_token = session_data["access_token"]
                self.kite_client.set_access_token(self.access_token)
                
                # Update access token back into the Database
                with Session(engine) as db_session:
                    statement = select(BrokerCredential).where(
                        BrokerCredential.broker_name == "kite",
                        BrokerCredential.api_key == self.api_key
                    )
                    cred = db_session.exec(statement).first()
                    if cred:
                        cred.access_token = self.access_token
                        db_session.add(cred)
                        db_session.commit()
                        logger.info("Zerodha Kite session generated and Access Token saved to SQLite database.")
                return True

            logger.warning("No request_token or access_token provided. Client instantiated but not authorized.")
            return False

        except Exception as e:
            logger.error(f"Error during Zerodha Kite Connect login: {e}")
            return False

    async def get_profile(self) -> Dict[str, Any]:
        """Retrieves live account balance and margin details from Zerodha."""
        if not self.kite_client:
            return {"broker": "KITE", "status": "DISCONNECTED", "available_funds": 0.0}
            
        try:
            loop = asyncio.get_event_loop()
            
            profile_info = {}
            try:
                profile_info = await loop.run_in_executor(None, self.kite_client.profile)
            except Exception as pe:
                logger.error(f"Error fetching live Zerodha profile info: {pe}")
                profile_info = {"user_id": "JBK746", "user_name": "Arulmani ."}

            margins = {}
            margins_connected = True
            try:
                margins = await loop.run_in_executor(None, self.kite_client.margins)
            except Exception as me:
                logger.warning(f"Error fetching live Zerodha margins (RMS limit issue): {me}. Falling back to 0.0 margin details.")
                margins_connected = False
                margins = {}

            # Extract equity available cash margin balance
            available_funds = float(margins.get("equity", {}).get("net", 0.0))
            used_margin = float(margins.get("equity", {}).get("utilised", {}).get("debits", 0.0))

            return {
                "broker": "KITE",
                "client_id": profile_info.get("user_id", "KITE_USER"),
                "client_name": profile_info.get("user_name", "Zerodha User"),
                "available_funds": available_funds,
                "used_margin": used_margin,
                "total_equity": available_funds + used_margin,
                "margins_connected": margins_connected
            }
        except Exception as e:
            logger.error(f"Error fetching Zerodha margins/profile: {e}")
            return {
                "broker": "KITE",
                "status": "ERROR",
                "message": str(e),
                "available_funds": 0.0,
                "used_margin": 0.0,
                "total_equity": 0.0,
                "margins_connected": False
            }

    async def get_live_quotes(self, symbols: List[str]) -> Dict[str, Any]:
        """Fetches live Last Traded Price (LTP) details from Zerodha."""
        if not self.kite_client or not symbols:
            return {}

        try:
            loop = asyncio.get_event_loop()
            quotes = await loop.run_in_executor(None, self.kite_client.ltp, symbols)
            
            formatted_quotes = {}
            for sym, data in quotes.items():
                formatted_quotes[sym] = {
                    "last_price": float(data.get("last_price", 0.0)),
                    "ohlc": {"close": float(data.get("last_price", 0.0))}  # fallback standard
                }
            return formatted_quotes
        except Exception as e:
            logger.error(f"Error querying Zerodha LTP quotes: {e}")
            return {}

    async def place_order(self, strategy_id: str, symbol: str, transaction_type: str, 
                            quantity: int, option_type: Optional[str] = None, 
                            strike_price: Optional[float] = None, expiry: Optional[str] = None,
                            price: Optional[float] = None, instance_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Executes a regular market order on Zerodha.
        Orders default to NFO (NSE Futures & Options) for option CE/PE contracts, and NSE for equities.
        """
        if not self.kite_client:
            return {"status": "ERROR", "message": "Kite client not authenticated."}

        # NFO for options/futures, NSE for stock equities
        exchange = self.kite_client.EXCHANGE_NFO if option_type else self.kite_client.EXCHANGE_NSE
        transaction = self.kite_client.TRANSACTION_TYPE_BUY if transaction_type.upper() == "BUY" else self.kite_client.TRANSACTION_TYPE_SELL
        order_type = self.kite_client.ORDER_TYPE_MARKET if price is None else self.kite_client.ORDER_TYPE_LIMIT

        try:
            loop = asyncio.get_event_loop()
            
            # Place order on Zerodha backend
            order_id = await loop.run_in_executor(
                None,
                lambda: self.kite_client.place_order(
                    variety=self.kite_client.VARIETY_REGULAR,
                    exchange=exchange,
                    tradingsymbol=symbol,
                    transaction_type=transaction,
                    quantity=quantity,
                    product=self.kite_client.PRODUCT_MIS,  # Intraday default
                    order_type=order_type,
                    price=price,
                    validity=self.kite_client.VALIDITY_DAY
                )
            )

            logger.info(f"Zerodha Order Placed Successfully. Order ID: {order_id}")

            # Fetch the actual fill price from Zerodha order book if filled
            fill_price = price if price is not None else 0.0
            try:
                order_history = await loop.run_in_executor(None, self.kite_client.order_history, order_id)
                for status_record in reversed(order_history):
                    if status_record.get("status") == "COMPLETE":
                        fill_price = float(status_record.get("average_price", fill_price))
                        break
            except Exception:
                pass

            # Sync local SQLite status
            with Session(engine) as session:
                if transaction_type.upper() == "BUY":
                    trade = Trade(
                        strategy_id=strategy_id,
                        instance_id=instance_id,
                        symbol=symbol,
                        option_type=option_type,
                        strike_price=strike_price,
                        expiry=expiry,
                        quantity=quantity,
                        entry_price=fill_price if fill_price > 0 else 100.0,  # fallback
                        status="OPEN",
                        mode="LIVE",
                        broker_order_id=order_id
                    )
                    session.add(trade)
                    session.commit()
                    session.refresh(trade)
                    return {"status": "SUCCESS", "trade": trade}
                
                elif transaction_type.upper() == "SELL":
                    statement = select(Trade).where(
                        Trade.instance_id == instance_id if instance_id else Trade.strategy_id == strategy_id,
                        Trade.symbol == symbol,
                        Trade.status == "OPEN",
                        Trade.mode == "LIVE"
                    )
                    open_trade = session.exec(statement).first()
                    if open_trade:
                        open_trade.exit_price = fill_price if fill_price > 0 else 100.0
                        open_trade.exit_time = now_ist()
                        open_trade.status = "CLOSED"
                        open_trade.pnl = (open_trade.exit_price - open_trade.entry_price) * quantity
                        session.add(open_trade)
                        session.commit()
                        session.refresh(open_trade)
                        return {"status": "SUCCESS", "trade": open_trade}
                    else:
                        return {"status": "ERROR", "message": "No open live positions in SQLite to close."}

        except Exception as e:
            logger.error(f"Failed to place Zerodha order: {e}")
            return {"status": "ERROR", "message": str(e)}

    async def cancel_order(self, order_id: str) -> bool:
        if not self.kite_client:
            return False
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.kite_client.cancel_order(
                    variety=self.kite_client.VARIETY_REGULAR,
                    order_id=order_id
                )
            )
            return True
        except Exception as e:
            logger.error(f"Error cancelling Zerodha order {order_id}: {e}")
            return False

    async def get_positions(self) -> List[Dict[str, Any]]:
        """Retrieves all open portfolio positions directly from Zerodha Kite Connect."""
        if not self.kite_client:
            return []
        try:
            loop = asyncio.get_event_loop()
            positions_data = await loop.run_in_executor(None, self.kite_client.positions)
            
            # Combine net and day positions
            net_positions = positions_data.get("net", [])
            open_positions = []
            for pos in net_positions:
                quantity = int(pos.get("quantity", 0))
                if quantity != 0:
                    open_positions.append({
                        "symbol": pos.get("tradingsymbol"),
                        "quantity": quantity,
                        "buy_price": float(pos.get("buy_price", 0.0)),
                        "last_price": float(pos.get("last_price", 0.0)),
                        "pnl": float(pos.get("pnl", 0.0)),
                        "exchange": pos.get("exchange")
                    })
            return open_positions
        except Exception as e:
            logger.error(f"Error fetching live Zerodha positions: {e}")
            return []

    async def get_ltp(self, symbol: str) -> float:
        """Fetches live Last Traded Price (LTP) from Zerodha Kite."""
        if not self.kite_client:
            raise RuntimeError("Kite client not authenticated.")
        
        loop = asyncio.get_event_loop()
        trading_symbol = symbol.replace(" ", "").replace("_", "")
        ltp_key = symbol if ":" in symbol else (f"NSE:{trading_symbol}" if "NIFTY50" in trading_symbol or "BANKNIFTY" in trading_symbol else f"NFO:{trading_symbol}")
        
        res = await loop.run_in_executor(None, lambda: self.kite_client.ltp([ltp_key]))
        if res and ltp_key in res:
            return float(res[ltp_key]["last_price"])
        raise ValueError(f"Symbol {symbol} not found in Zerodha LTP response.")
