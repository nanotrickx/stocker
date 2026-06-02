import logging
import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional
from sqlmodel import Session, select
from app.database import engine, Trade, BrokerCredential, now_ist
from app.brokers.base import BaseBroker

logger = logging.getLogger("Stocker.Brokers.Paper")

class PaperBroker(BaseBroker):
    """
    Simulated Broker that executes trades locally using SQLite DB.
    Ideal for paper-trading options and stocks.
    """
    def __init__(self):
        self.mock_balance = 100000.0  # 1 Lakh mock capital

    async def login(self, credentials: Dict[str, Any]) -> bool:
        logger.info("PaperBroker login successful (sandbox environment).")
        return True

    async def get_profile(self) -> Dict[str, Any]:
        with Session(engine) as session:
            # Calculate total active paper trade P&L
            statement = select(Trade).where(Trade.status == "OPEN", Trade.mode == "PAPER")
            open_trades = session.exec(statement).all()
            
            # Simple mock calculations
            used_margin = sum(trade.entry_price * trade.quantity for trade in open_trades)
            available_balance = self.mock_balance - used_margin
            
            return {
                "broker": "PAPER",
                "client_id": "PAPER_TRADER_01",
                "client_name": "Paper Simulator Account",
                "available_funds": available_balance,
                "used_margin": used_margin,
                "total_equity": self.mock_balance
            }

    async def get_live_quotes(self, symbols: List[str]) -> Dict[str, Any]:
        # Strictly query active live broker instead of standard mock dictionary!
        quotes = {}
        for symbol in symbols:
            try:
                ltp = await self.get_ltp(symbol)
                if ltp > 0.0:
                    quotes[symbol] = {
                        "last_price": ltp,
                        "ohlc": {"open": ltp, "high": ltp, "low": ltp, "close": ltp}
                    }
            except Exception:
                pass
        return quotes

    async def place_order(self, strategy_id: str, symbol: str, transaction_type: str, 
                            quantity: int, option_type: Optional[str] = None, 
                            strike_price: Optional[float] = None, expiry: Optional[str] = None,
                            price: Optional[float] = None, instance_id: Optional[int] = None) -> Dict[str, Any]:
        
        # In Paper Trading, orders are executed immediately at the specified price or real-time LTP
        if price is None:
            try:
                fill_price = await self.get_ltp(symbol)
                if fill_price <= 0.0:
                    raise RuntimeError("LTP resolved to 0.0 due to active broker disconnect.")
            except Exception as e:
                logger.error(f"[PAPER] Order placement failed due to active broker disconnect: {e}")
                return {"status": "ERROR", "message": f"Active broker disconnected or live quote not found: {e}"}
        else:
            fill_price = price
        
        with Session(engine) as session:
            if transaction_type.upper() == "BUY":
                # Create a new paper trade position
                trade = Trade(
                    strategy_id=strategy_id,
                    instance_id=instance_id,
                    symbol=symbol,
                    option_type=option_type,
                    strike_price=strike_price,
                    expiry=expiry,
                    quantity=quantity,
                    entry_price=fill_price,
                    status="OPEN",
                    mode="PAPER",
                    broker_order_id=f"PAPER_ORD_{int(datetime.utcnow().timestamp())}"
                )
                session.add(trade)
                session.commit()
                session.refresh(trade)
                logger.info(f"[PAPER BUY] Created position: {symbol} at {fill_price} | Qty: {quantity}")
                return {"status": "SUCCESS", "trade": trade}
            
            elif transaction_type.upper() == "SELL":
                # Close the existing paper trade position for this symbol/strategy
                statement = select(Trade).where(
                    Trade.instance_id == instance_id if instance_id else Trade.strategy_id == strategy_id,
                    Trade.symbol == symbol,
                    Trade.status == "OPEN",
                    Trade.mode == "PAPER"
                )
                open_trade = session.exec(statement).first()
                
                if open_trade:
                    open_trade.exit_price = fill_price
                    open_trade.exit_time = now_ist()
                    open_trade.status = "CLOSED"
                    # Calculate realized P&L: (Exit - Entry) * quantity
                    open_trade.pnl = (fill_price - open_trade.entry_price) * quantity
                    session.add(open_trade)
                    session.commit()
                    session.refresh(open_trade)
                    logger.info(f"[PAPER SELL] Closed position: {symbol} at {fill_price} | P&L: {open_trade.pnl}")
                    return {"status": "SUCCESS", "trade": open_trade}
                else:
                    return {"status": "ERROR", "message": "No open paper position found to close"}
        
        return {"status": "ERROR", "message": "Unknown transaction type"}

    async def cancel_order(self, order_id: str) -> bool:
        return True

    async def get_positions(self) -> List[Dict[str, Any]]:
        with Session(engine) as session:
            statement = select(Trade).where(Trade.status == "OPEN", Trade.mode == "PAPER")
            open_trades = session.exec(statement).all()
            return [
                {
                    "trade_id": t.id,
                    "strategy_id": t.strategy_id,
                    "symbol": t.symbol,
                    "option_type": t.option_type,
                    "strike_price": t.strike_price,
                    "quantity": t.quantity,
                    "entry_price": t.entry_price,
                    "entry_time": t.entry_time.isoformat(),
                    "mode": t.mode
                }
                for t in open_trades
            ]

    async def get_ltp(self, symbol: str) -> float:
        # Try to fetch actual live LTP from Zerodha Kite or Dhan if active
        try:
            with Session(engine) as session:
                active_cred = session.exec(select(BrokerCredential).where(
                    BrokerCredential.broker_name != "telegram",
                    BrokerCredential.active == True
                )).first()
                
                if active_cred:
                    if active_cred.broker_name == "kite":
                        token = active_cred.access_token
                        if token:
                            from kiteconnect import KiteConnect
                            kite = KiteConnect(api_key=active_cred.api_key)
                            kite.set_access_token(token)
                            loop = asyncio.get_event_loop()
                            ltp_key = symbol if ":" in symbol else f"NSE:{symbol}"
                            res = await loop.run_in_executor(None, lambda: kite.ltp([ltp_key]))
                            if res and ltp_key in res:
                                return float(res[ltp_key]["last_price"])
                    elif active_cred.broker_name == "dhan":
                        from app.brokers.dhan import DhanBroker
                        dhan = DhanBroker()
                        success = await dhan.login({
                            "api_key": active_cred.api_key,
                            "api_secret": active_cred.api_secret,
                            "access_token": active_cred.access_token,
                            "totp_secret": active_cred.totp_secret
                        })
                        if success:
                            return await dhan.get_ltp(symbol)
        except Exception as e:
            logger.error(f"PaperBroker actual LTP query failed: {e}")
            
        # Under strict user request: NEVER use mock fallback data! Raise exception to prevent incorrect paper trading execution.
        raise RuntimeError(f"PaperBroker: Active live broker feed disconnected or quote not found for symbol '{symbol}'")
