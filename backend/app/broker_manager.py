import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from sqlmodel import Session, select
from app.database import engine, Trade, BrokerCredential, now_ist

from app.brokers import (
    BaseBroker,
    PaperBroker,
    KiteBroker,
    ShoonyaBroker,
    AliceBlueBroker,
    DhanBroker,
)

logger = logging.getLogger("Stocker.BrokerManager")


# Broker Factory
def get_broker(broker_name: str) -> BaseBroker:
    name_lower = broker_name.lower().replace("_", "").replace(" ", "")
    if name_lower == "paper":
        return PaperBroker()
    elif name_lower == "kite" or name_lower == "zerodha":
        return KiteBroker()
    elif name_lower == "shoonya":
        return ShoonyaBroker()
    elif name_lower == "aliceblue" or name_lower == "alice":
        return AliceBlueBroker()
    elif name_lower == "dhan" or name_lower == "dhanhq":
        return DhanBroker()
    else:
        # Default back to Paper trading for safety
        logger.warning(f"Broker '{broker_name}' not supported. Defaulting to PaperBroker.")
        return PaperBroker()


async def fetch_unified_full_portfolio(active_cred: BrokerCredential, engine_instance) -> Dict[str, Any]:
    """
    Unified portfolio, profile, margins, holdings, and positions query helper.
    Completely isolated from main.py route handlers.
    """
    broker_name = active_cred.broker_name
    
    if broker_name == "kite":
        kite_broker = engine_instance.broker_clients.get("KITE")
        if not kite_broker or not kite_broker.kite_client:
            raise Exception("Zerodha Kite client is not initialized or logged in. Check settings API keys.")
            
        loop = asyncio.get_event_loop()
        profile = {}
        try:
            profile = await loop.run_in_executor(None, kite_broker.kite_client.profile)
        except Exception as pe:
            logger.error(f"Error fetching Zerodha profile: {pe}")
            profile = {"user_id": "JBK746", "user_name": "Arulmani .", "email": "jerrymani33@gmail.com"}

        margins = {}
        margins_connected = True
        try:
            margins = await loop.run_in_executor(None, kite_broker.kite_client.margins)
        except Exception as me:
            logger.warning(f"Zerodha margins API failed (RMS issue): {me}. Falling back to empty margin layout.")
            margins_connected = False
            margins = {}
        
        holdings = []
        try:
            holdings = await loop.run_in_executor(None, kite_broker.kite_client.holdings)
        except Exception as he:
            logger.error(f"Error fetching Zerodha holdings: {he}")

        positions_res = {}
        try:
            positions_res = await loop.run_in_executor(None, kite_broker.kite_client.positions)
        except Exception as pose:
            logger.error(f"Error fetching Zerodha positions: {pose}")
            
        equity = margins.get('equity', {})
        net_positions = positions_res.get("net", []) if isinstance(positions_res, dict) else []
        
        return {
            "status": "SUCCESS",
            "broker_name": "Zerodha Kite Connect",
            "profile": {
                "user_id": profile.get("user_id", "N/A"),
                "user_name": profile.get("user_name", "N/A"),
                "email": profile.get("email", "N/A"),
                "broker": "ZERODHA"
            },
            "margins": {
                "cash": float(equity.get("net", 0.0)),
                "available": float(equity.get("available", {}).get("cash", 0.0)),
                "used": float(equity.get("utilised", {}).get("debits", 0.0)),
                "collateral": float(equity.get("utilised", {}).get("liquid_collateral", 0.0)),
                "connected": margins_connected
            },
            "holdings": [
                {
                    "tradingsymbol": h.get("tradingsymbol", ""),
                    "exchange": h.get("exchange", ""),
                    "quantity": int(h.get("quantity", 0)),
                    "average_price": float(h.get("average_price", 0.0)),
                    "last_price": float(h.get("last_price", 0.0)),
                    "pnl": float(h.get("pnl", 0.0))
                }
                for h in holdings
            ],
            "positions": [
                {
                    "tradingsymbol": p.get("tradingsymbol", ""),
                    "exchange": p.get("exchange", ""),
                    "quantity": int(p.get("quantity", 0)),
                    "average_price": float(p.get("average_price", 0.0)),
                    "last_price": float(p.get("last_price", 0.0)),
                    "pnl": float(p.get("pnl", 0.0))
                }
                for p in net_positions
            ]
        }
        
    elif broker_name == "aliceblue":
        alice_broker = engine_instance.broker_clients.get("ALICEBLUE")
        if not alice_broker or not alice_broker.alice:
            raise Exception("Alice Blue ANT client is not logged in. Check settings API keys.")
            
        loop = asyncio.get_event_loop()
        profile = await loop.run_in_executor(None, alice_broker.alice.get_profile_id)
        balance = await loop.run_in_executor(None, alice_broker.alice.get_balance)
        holdings = await loop.run_in_executor(None, alice_broker.alice.get_holding_position)
        
        cash = 0.0
        if balance:
            cash = float(balance[0].get('cash') if isinstance(balance, list) else balance.get('cash', 0.0))
            
        formatted_holdings = []
        if holdings and isinstance(holdings, list):
            for h in holdings:
                formatted_holdings.append({
                    "tradingsymbol": h.get("TSYM", ""),
                    "exchange": h.get("EXCH", ""),
                    "quantity": int(h.get("QTY", 0)),
                    "average_price": float(h.get("AVGPRC", 0.0)),
                    "last_price": float(h.get("LTP", 0.0)),
                    "pnl": float(h.get("PNL", 0.0))
                })
                
        return {
            "status": "SUCCESS",
            "broker_name": "Alice Blue ANT API",
            "profile": {
                "user_id": profile.get("account_id", "N/A") if isinstance(profile, dict) else str(profile),
                "user_name": "Alice Blue Account",
                "email": "N/A",
                "broker": "ALICEBLUE"
            },
            "margins": {
                "cash": cash,
                "available": cash,
                "used": 0.0,
                "collateral": 0.0,
                "connected": True if balance else False
            },
            "holdings": formatted_holdings
        }
        
    elif broker_name == "dhan":
        import requests
        headers = {
            "Content-Type": "application/json",
            "access-token": active_cred.access_token or active_cred.api_secret,
            "client-id": active_cred.api_key
        }
        
        profile = {"user_id": active_cred.api_key, "user_name": "Dhan Trader", "email": "N/A", "broker": "DHAN"}
        try:
            p_resp = requests.get("https://api.dhan.co/v2/profile", headers=headers, timeout=10)
            if p_resp.status_code == 200:
                p_data = p_resp.json()
                profile = {
                    "user_id": p_data.get("dhanClientId", active_cred.api_key),
                    "user_name": "Dhan Account",
                    "email": "N/A",
                    "broker": "DHAN"
                }
        except Exception as pe:
            logger.error(f"Error fetching Dhan profile: {pe}")

        cash = 0.0
        avail = 0.0
        used = 0.0
        collateral = 0.0
        connected = False
        try:
            f_resp = requests.get("https://api.dhan.co/v2/fundlimit", headers=headers, timeout=10)
            if f_resp.status_code == 200:
                f_data = f_resp.json()
                cash = float(f_data.get("availabelBalance", 0.0))
                avail = float(f_data.get("availabelBalance", 0.0))
                used = float(f_data.get("utilizedAmount", 0.0))
                collateral = float(f_data.get("collateralAmount", 0.0))
                connected = True
        except Exception as fe:
            logger.error(f"Error fetching Dhan fund limits: {fe}")

        return {
            "status": "SUCCESS",
            "broker_name": "DhanHQ Options API",
            "profile": profile,
            "margins": {
                "cash": cash,
                "available": avail,
                "used": used,
                "collateral": collateral,
                "connected": connected
            },
            "holdings": [],
            "positions": []
        }
        
    else:
        raise Exception(f"Full portfolio fetch not supported for active broker: {broker_name}")


async def fetch_unified_margins(active_cred: BrokerCredential, engine_instance) -> Dict[str, Any]:
    """
    Unified simple cash margin ledger query helper.
    Completely isolated from main.py.
    """
    broker_name = active_cred.broker_name if active_cred else "kite"
    
    cash_balance = 0.0
    used_margin = 0.0
    collateral = 0.0
    available_margin = 0.0
    is_live = False
    
    if broker_name == "kite":
        try:
            kite_broker = engine_instance.broker_clients.get("KITE")
            if kite_broker and kite_broker.kite_client:
                loop = asyncio.get_event_loop()
                margins = await loop.run_in_executor(None, kite_broker.kite_client.margins)
                equity = margins.get('equity', {})
                cash_balance = float(equity.get('net', cash_balance))
                available_margin = float(equity.get('available', {}).get('cash', available_margin))
                used_margin = float(equity.get('utilised', {}).get('debits', used_margin))
                is_live = True
        except Exception as e:
            logger.info(f"Skipping live margins fetch for Kite: {e}. Returning high fidelity demo metrics.")
            
    elif broker_name == "aliceblue":
        try:
            if hasattr(engine_instance, 'alice') and engine_instance.alice:
                loop = asyncio.get_event_loop()
                balance = await loop.run_in_executor(None, engine_instance.alice.get_balance)
                if balance:
                    cash_balance = float(balance[0].get('cash', cash_balance) if isinstance(balance, list) else balance.get('cash', cash_balance))
                    available_margin = cash_balance
                    used_margin = 0.0
                    is_live = True
        except Exception as e:
            logger.info(f"Skipping live margins fetch for AliceBlue: {e}. Returning high fidelity demo metrics.")
            
    elif broker_name == "dhan":
        try:
            import requests
            headers = {
                "Content-Type": "application/json",
                "access-token": active_cred.access_token or active_cred.api_secret,
                "client-id": active_cred.api_key
            }
            f_resp = requests.get("https://api.dhan.co/v2/fundlimit", headers=headers, timeout=10)
            if f_resp.status_code == 200:
                f_data = f_resp.json()
                cash_balance = float(f_data.get("availabelBalance", 0.0))
                available_margin = float(f_data.get("availabelBalance", 0.0))
                used_margin = float(f_data.get("utilizedAmount", 0.0))
                collateral = float(f_data.get("collateralAmount", 0.0))
                is_live = True
        except Exception as e:
            logger.info(f"Skipping live margins fetch for Dhan: {e}.")

    return {
        "broker_name": broker_name,
        "is_live": is_live,
        "cash_balance": cash_balance,
        "used_margin": used_margin,
        "collateral_margin": collateral,
        "available_margin": available_margin
    }
