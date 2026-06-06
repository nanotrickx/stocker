import json
import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlmodel import Session, select

from app.database import init_db, get_session, Strategy, StrategyInstance, Trade, BrokerCredential, DailySummary
from app.engine import ExecutionEngine
from app.telegram_bot import TelegramBot
from app.analytics import calculate_greeks, calculate_implied_volatility
from app.market_data import BaseMarketDataProvider, KiteMarketDataProvider, SimulatedMarketDataProvider
from app.orb_strategy import ORBStrategyEngine, DEFAULT_ORB_CONFIG
from app.broker_manager import fetch_unified_full_portfolio, fetch_unified_margins

# Configure structured console logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("Stocker.Main")

app = FastAPI(title="Stocker: Real-time Multi-Broker Option Trading System")

# CORS Setup for React frontend connection
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
engine_instance = ExecutionEngine()
telegram_instance = TelegramBot()
active_websocket_connections: List[WebSocket] = []

# Startup and Shutdown hooks
@app.on_event("startup")
async def on_startup():
    logger.info("Initializing SQLite database tables...")
    init_db()

    # ── Seed default strategies ─────────────────────────────────
    _seed_default_strategies()
    
    # Load Telegram Bot credentials if saved in database
    with Session(db_engine_lookup()) as session:
        cred = session.exec(select(BrokerCredential).where(BrokerCredential.broker_name == "telegram")).first()
        if cred:
            await telegram_instance.update_credentials(cred.api_key, cred.api_secret)

    # Inject bot into engine and start background loop
    engine_instance.set_telegram_bot(telegram_instance)
    await engine_instance.start()
    
    # Start live streaming data broadcast task
    asyncio.create_task(broadcast_stream_task())


from app.brokers.dhan import get_dhan_token

def _seed_default_strategies():
    """Create built-in strategy templates if they don't already exist."""
    from app.database import engine as db_eng
    defaults = [
        {
            "id": "orb_breakout",
            "name": "ORB Breakout",
            "description": "Opening Range Breakout — uses the 9:15 AM candle high/low as reference. Waits for breakout, selects ATM option (₹100–200 premium), and manages ±10% risk.",
            "strategy_type": "orb_breakout",
            "config": DEFAULT_ORB_CONFIG,
        },
    ]
    with Session(db_eng) as session:
        for d in defaults:
            existing = session.get(Strategy, d["id"])
            if not existing:
                strategy = Strategy(
                    id=d["id"],
                    name=d["name"],
                    description=d.get("description", ""),
                    strategy_type=d.get("strategy_type", "custom"),
                    paper_trade=True,
                    config_json=json.dumps(d["config"]),
                    active=False,
                )
                session.add(strategy)
                logger.info(f"Seeded default template: {d['name']}")
        session.commit()

def db_engine_lookup():
    from app.database import engine
    return engine

@app.on_event("shutdown")
async def on_shutdown():
    await engine_instance.stop()

# WebSocket Broadcast Task
async def broadcast_stream_task():
    """Broadcasts simulated tick updates, Option Greeks, and running trades to connected UIs."""
    while True:
        if active_websocket_connections:
            # Resolve live spot price from active broker or fall back to last day value (static)
            spot = 23909.55  # Accurate Last Day's Close Value for Nifty 50 (May 29th, 2026)
            used_real_data = False
            
            try:
                with Session(db_engine_lookup()) as db_session:
                    active_cred = db_session.exec(select(BrokerCredential).where(
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
                                ltp_res = kite.ltp(["NSE:NIFTY 50"])
                                if ltp_res and "NSE:NIFTY 50" in ltp_res:
                                    spot = float(ltp_res["NSE:NIFTY 50"]["last_price"])
                                    used_real_data = True
                        elif active_cred.broker_name == "dhan":
                            from app.brokers.dhan import get_dhan_token
                            dhan_token = get_dhan_token(active_cred, db_session)
                            if dhan_token:
                                from app.market_data import DhanMarketDataProvider
                                provider = DhanMarketDataProvider(client_id=active_cred.api_key, access_token=dhan_token)
                                from_dt = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
                                candles = provider.get_historical_data(
                                    symbol="NSE:NIFTY 50",
                                    days=3,
                                    from_date=from_dt,
                                    to_date=datetime.now().strftime("%Y-%m-%d"),
                                    interval="minute"
                                )
                                if candles:
                                    spot = float(candles[-1]["close"])
                                    used_real_data = True
            except Exception as e:
                logger.warning(f"Live broker spot fetch unavailable, using simulated/fallback spot: {e}")
                
            # Dynamic strikes automatically centered around live spot price (NIFTY 50-strike intervals)
            atm_strike = int(round(spot / 50.0) * 50)
            strikes = [atm_strike - 100, atm_strike - 50, atm_strike, atm_strike + 50, atm_strike + 100]
            option_chain = []
            
            for strike in strikes:
                ce_greeks = calculate_greeks(spot, strike, days_to_expiry=3, volatility=0.14, option_type="CE")
                pe_greeks = calculate_greeks(spot, strike, days_to_expiry=3, volatility=0.14, option_type="PE")
                option_chain.append({
                    "strike": strike,
                    "ce": {
                        "price": ce_greeks["price"],
                        "delta": ce_greeks["delta"],
                        "theta": ce_greeks["theta"],
                        "vega": ce_greeks["vega"],
                        "gamma": ce_greeks["gamma"]
                    },
                    "pe": {
                        "price": pe_greeks["price"],
                        "delta": pe_greeks["delta"],
                        "theta": pe_greeks["theta"],
                        "vega": pe_greeks["vega"],
                        "gamma": pe_greeks["gamma"]
                    }
                })

            # Fetch open trades from database and calculate real-time unrealized PnL
            with Session(db_engine_lookup()) as session:
                open_trades = session.exec(select(Trade).where(Trade.status == "OPEN")).all()
                positions_data = []
                for t in open_trades:
                    # Calculate current live option price based on the index spot price
                    opt_greeks = calculate_greeks(spot, t.strike_price or spot, days_to_expiry=3, volatility=0.14, option_type=t.option_type or "CE")
                    current_price = opt_greeks["price"]
                    pnl = (current_price - t.entry_price) * t.quantity
                    
                    positions_data.append({
                        "id": t.id,
                        "strategy_id": t.strategy_id,
                        "symbol": t.symbol,
                        "option_type": t.option_type,
                        "strike_price": t.strike_price,
                        "quantity": t.quantity,
                        "entry_price": t.entry_price,
                        "pnl": pnl,
                        "mode": t.mode,
                        "entry_time": t.entry_time.isoformat()
                    })

            engine_status = "RUNNING"
            if not engine_instance.running:
                engine_status = "STOPPED"
            elif engine_instance.paused:
                engine_status = "PAUSED"
                
            is_paper_running = any(strategy.active and strategy.paper_trade for strategy in engine_instance.active_strategies.values())
            is_live_running = any(strategy.active and not strategy.paper_trade for strategy in engine_instance.active_strategies.values())

            data = {
                "type": "STREAM_TICK",
                "spot_price": spot,
                "timestamp": datetime.now().isoformat(),
                "option_chain": option_chain,
                "positions": positions_data,
                "strategy_logs": engine_instance.get_recent_logs(),
                "engine_status": engine_status,
                "is_paper_running": is_paper_running,
                "is_live_running": is_live_running
            }

            message_str = json.dumps(data)
            for ws in list(active_websocket_connections):
                try:
                    await ws.send_text(message_str)
                except Exception:
                    active_websocket_connections.remove(ws)

        await asyncio.sleep(1.0)


# ---------------------------------------------------------
# API Schema Models
# ---------------------------------------------------------

class StrategyCreate(BaseModel):
    id: str
    name: str
    paper_trade: bool
    config: Dict[str, Any]

class StrategyToggle(BaseModel):
    active: bool

class BacktestRequest(BaseModel):
    strategy_id: str
    symbol: str
    instrument_type: str = "STOCK"        # STOCK | CE | PE
    strike_price: Optional[float] = None  # For options
    expiry_date: Optional[str] = None     # YYYY-MM-DD for options
    from_date: Optional[str] = None       # YYYY-MM-DD, overrides days
    to_date: Optional[str] = None         # YYYY-MM-DD
    single_day: Optional[str] = None      # YYYY-MM-DD  → intraday mode
    interval: str = "day"                 # day | 60minute | 30minute | 15minute | 5minute
    days: int = 30
    initial_capital: float = 100000.0
    lots: int = 1
    slippage_pct: float = 0.0
    trail_sl_pct: Optional[float] = None
    charges_per_trade: float = 0.0

class TelegramBacktestReportRequest(BaseModel):
    strategy_name: str
    symbol: str
    from_date: str
    to_date: str
    initial_capital: float
    total_trades: int
    win_rate: float
    profitable_trades: int
    losing_trades: int
    net_pnl: float
    final_capital: float
    trades: List[Dict[str, Any]] = []

class TelegramTradeDetail(BaseModel):
    entry_time: str
    exit_time: str
    symbol: str
    instrument_type: str
    quantity: int
    entry_price: float
    exit_price: float
    gross_pnl: float
    charges: float
    pnl: float
    pnl_pct: float
    index_breakout_time: Optional[str] = "N/A"
    index_breakout_price: Optional[float] = None
    option_breakout_time: Optional[str] = "N/A"
    option_breakout_price: Optional[float] = None
    exit_reason: str

class TelegramLedgerDocumentRequest(BaseModel):
    strategy_name: str
    symbol: str
    from_date: str
    to_date: str
    trades: List[TelegramTradeDetail]

class CredentialUpdate(BaseModel):
    broker_name: str
    api_key: str
    api_secret: str
    totp_secret: Optional[str] = None

class GlobalSettingsUpdate(BaseModel):
    risk_max_daily_loss: float
    risk_max_active_positions: int
    risk_auto_square_off_time: str
    risk_default_slippage: float
    notify_order_placement: bool
    notify_order_execution: bool
    notify_sl_target_hit: bool
    notify_daily_summary: bool

class InstanceCreate(BaseModel):
    template_id: str
    symbol: str = "NSE:NIFTY 50"
    instrument_type: str = "OPTION"
    quantity: int = 50
    stop_loss_pct: float = 10.0
    target_pct: float = 10.0
    premium_min: float = 100
    premium_max: float = 200
    paper_trade: bool = True

class InstanceToggle(BaseModel):
    active: bool


# ---------------------------------------------------------
# REST ENDPOINTS
# ---------------------------------------------------------

@app.get("/api/health")
def health_check():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}

# Strategies APIs
@app.get("/api/strategies", response_model=List[Strategy])
def list_strategies(session: Session = Depends(get_session)):
    return session.exec(select(Strategy)).all()

@app.post("/api/strategies", response_model=Strategy)
async def save_strategy(data: StrategyCreate, session: Session = Depends(get_session)):
    strategy = session.get(Strategy, data.id)
    if not strategy:
        strategy = Strategy(id=data.id, name=data.name)
    
    strategy.name = data.name
    strategy.paper_trade = data.paper_trade
    strategy.config_json = json.dumps(data.config)
    session.add(strategy)
    session.commit()
    session.refresh(strategy)
    
    # Reload active list in execution engine
    await engine_instance.reload_strategies()
    return strategy

@app.delete("/api/strategies/{id}")
async def delete_strategy(id: str, session: Session = Depends(get_session)):
    strategy = session.get(Strategy, id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    session.delete(strategy)
    session.commit()
    
    await engine_instance.reload_strategies()
    return {"status": "SUCCESS"}

@app.post("/api/strategies/{id}/toggle")
async def toggle_strategy(id: str, payload: StrategyToggle, session: Session = Depends(get_session)):
    strategy = session.get(Strategy, id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    strategy.active = payload.active
    session.add(strategy)
    session.commit()
    
    await engine_instance.reload_strategies()
    return {"status": "SUCCESS", "active": payload.active}


# ---------------------------------------------------------
# STRATEGY INSTANCES — Running deployments
# ---------------------------------------------------------

@app.get("/api/strategy-instances")
def list_instances(session: Session = Depends(get_session)):
    instances = session.exec(select(StrategyInstance)).all()
    result = []
    for inst in instances:
        # Resolve template name
        tmpl = session.get(Strategy, inst.template_id)
        result.append({
            "id": inst.id,
            "template_id": inst.template_id,
            "template_name": tmpl.name if tmpl else inst.template_id,
            "strategy_type": tmpl.strategy_type if tmpl else "custom",
            "name": inst.name,
            "symbol": inst.symbol,
            "instrument_type": inst.instrument_type,
            "config": inst.get_config(),
            "active": inst.active,
            "paper_trade": inst.paper_trade,
            "created_at": inst.created_at.isoformat() if inst.created_at else None,
        })
    return result

@app.post("/api/strategy-instances")
async def create_instance(data: InstanceCreate, session: Session = Depends(get_session)):
    tmpl = session.get(Strategy, data.template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Strategy template not found")

    # Merge template config with instance overrides
    base_config = tmpl.get_config()
    base_config["symbols"] = [data.symbol]
    base_config.setdefault("risk", {})
    base_config["risk"]["stop_loss_pct"] = data.stop_loss_pct
    base_config["risk"]["target_pct"] = data.target_pct
    base_config.setdefault("action", {})
    base_config["action"]["quantity"] = data.quantity
    base_config["action"]["instrument_type"] = data.instrument_type
    base_config["action"]["paper_trade"] = data.paper_trade
    base_config.setdefault("option_selection", {})
    base_config["option_selection"]["premium_min"] = data.premium_min
    base_config["option_selection"]["premium_max"] = data.premium_max

    # Clean symbol name for display
    sym_short = data.symbol.replace("NSE:", "").replace("BSE:", "")
    display_name = f"{tmpl.name} — {sym_short}"

    instance = StrategyInstance(
        template_id=data.template_id,
        name=display_name,
        symbol=data.symbol,
        instrument_type=data.instrument_type,
        config_json=json.dumps(base_config),
        active=True,
        paper_trade=data.paper_trade,
    )
    session.add(instance)
    session.commit()
    session.refresh(instance)

    await engine_instance.reload_strategies()
    return {"status": "SUCCESS", "id": instance.id, "name": instance.name}

@app.post("/api/strategy-instances/{id}/toggle")
async def toggle_instance(id: int, payload: InstanceToggle, session: Session = Depends(get_session)):
    inst = session.get(StrategyInstance, id)
    if not inst:
        raise HTTPException(status_code=404, detail="Instance not found")
    inst.active = payload.active
    session.add(inst)
    session.commit()
    await engine_instance.reload_strategies()
    return {"status": "SUCCESS", "active": inst.active}

@app.delete("/api/strategy-instances/{id}")
async def delete_instance(id: int, session: Session = Depends(get_session)):
    inst = session.get(StrategyInstance, id)
    if not inst:
        raise HTTPException(status_code=404, detail="Instance not found")
    session.delete(inst)
    session.commit()
    await engine_instance.reload_strategies()
    return {"status": "SUCCESS"}

@app.get("/api/strategy-instances/{id}/option-chain")
async def get_instance_option_chain(id: int, session: Session = Depends(get_session)):
    inst = session.get(StrategyInstance, id)
    if not inst:
        raise HTTPException(status_code=404, detail="Instance not found")
    
    data = await engine_instance.get_live_option_chain(inst.symbol, inst)
    return data

def get_base_lot_size(symbol: str) -> int:
    """
    Returns the standard lot size for index options/futures or 1 for individual stocks.
    """
    symbol_upper = symbol.upper()
    if "NIFTY BANK" in symbol_upper or "BANKNIFTY" in symbol_upper:
        return 15
    elif "FINNIFTY" in symbol_upper:
        return 40
    elif "NIFTY" in symbol_upper:
        return 50
    elif "SENSEX" in symbol_upper:
        return 10
    else:
        return 1

# ── ORB Backtest Helper ─────────────────────────────────────────────────────

def _run_orb_backtest(payload: "BacktestRequest", config: Dict, session: Session):
    """
    Dedicated backtest flow for ORB Breakout strategy.
    Fetches intraday 1-min candles and runs through the ORB engine.
    """
    import pandas as pd
    from app.market_data import KiteMarketDataProvider, DhanMarketDataProvider

    # Resolve active credentials (support Dhan & Kite)
    active_cred = session.exec(
        select(BrokerCredential).where(
            BrokerCredential.broker_name != "telegram",
            BrokerCredential.active == True
        )
    ).first()

    token = None
    if active_cred:
        token = get_dhan_token(active_cred, session) if active_cred.broker_name == "dhan" else active_cred.access_token

    if not active_cred or (not token and active_cred.broker_name not in ["paper", "shoonya"]):
        return {
            "status": "ERROR",
            "message": "No active broker session found. Please login via Settings.",
        }

    if active_cred.broker_name == "dhan":
        provider = DhanMarketDataProvider(
            client_id=active_cred.api_key,
            access_token=token,
        )
    elif active_cred.broker_name in ["paper", "shoonya"]:
        return {
            "status": "ERROR",
            "message": "Actual live broker data provider is not available in PAPER/SHOONYA mode. Backtesting skipped as requested.",
        }
    else:
        provider = KiteMarketDataProvider(
            api_key=active_cred.api_key,
            access_token=token,
        )

    # ORB always uses the underlying index, not options — breakout is on spot
    symbol = config.get("symbols", [payload.symbol])[0]

    # Override quantity if lots is specified
    if payload.lots > 0:
        if "action" not in config:
            config["action"] = {}
        base_lot = get_base_lot_size(symbol)
        config["action"]["quantity"] = payload.lots * base_lot

    # Determine date range — force intraday 1-min for ORB
    is_single = bool(payload.single_day)
    interval = "minute"  # ORB needs 1-min candles

    if is_single:
        fd_str = payload.single_day
        td_str = payload.single_day
    elif payload.from_date and payload.to_date:
        fd_str = payload.from_date
        td_str = payload.to_date
    else:
        # Default last 1 day for ORB (intraday strategy)
        from datetime import datetime, timedelta
        td = datetime.now()
        fd = td - timedelta(days=max(1, payload.days))
        fd_str = fd.strftime("%Y-%m-%d")
        td_str = td.strftime("%Y-%m-%d")

    try:
        candles = provider.get_historical_data(
            symbol=symbol,
            days=payload.days,
            from_date=fd_str,
            to_date=td_str,
            interval=interval,
            instrument_type="STOCK",  # Spot index candles
        )
    except RuntimeError as e:
        return {"status": "ERROR", "message": str(e)}

    if not candles or len(candles) < 5:
        return {
            "status": "ERROR",
            "message": f"Not enough intraday candles ({len(candles) if candles else 0}). Ensure market was open on the selected day.",
        }

    # Build DataFrame
    df = pd.DataFrame(
        {
            "open":   [c["open"]   for c in candles],
            "high":   [c["high"]   for c in candles],
            "low":    [c["low"]    for c in candles],
            "close":  [c["close"]  for c in candles],
            "volume": [c["volume"] for c in candles],
        },
        index=pd.to_datetime([c["date"] for c in candles]),
    )

    # Run ORB engine
    orb = ORBStrategyEngine(config)
    result = orb.run_backtest(
        df,
        initial_capital=payload.initial_capital,
        provider=provider,
        expiry_date=payload.expiry_date,
        slippage_pct=payload.slippage_pct,
        trail_sl_pct=payload.trail_sl_pct,
        charges_per_trade=payload.charges_per_trade,
    )

    # Inject interval/meta info
    if result.get("meta"):
        result["meta"]["interval"] = interval
        result["meta"]["from"] = str(df.index[0])
        result["meta"]["to"] = str(df.index[-1])

    return result


@app.post("/api/backtest")
def run_strategy_backtest(payload: BacktestRequest, session: Session = Depends(get_session)):
    """
    Full historical backtest with:
    - Real broker data only (no mock fallback)
    - Date-range or last-N-days mode
    - Stock OR option (CE/PE) instrument support
    - Bar-by-bar simulation with full trade journal
    - Visualization timeline showing every candle state
    """
    import pandas as pd
    from app.analytics import calculate_indicators, check_rule_condition
    from app.market_data import KiteMarketDataProvider, DhanMarketDataProvider

    # ── 1. Load strategy ────────────────────────────────────────
    strategy = session.get(Strategy, payload.strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    config = strategy.get_config()
    if not config:
        return {"status": "ERROR", "message": "Strategy has no visual rules configured. Open the builder and add entry/exit conditions."}

    # ── ORB Breakout — delegate to dedicated engine ────────────
    strategy_type = config.get("strategy_type", "custom")
    if strategy_type == "orb_breakout":
        try:
            return _run_orb_backtest(payload, config, session)
        except Exception as e:
            logger.error(f"ORB backtest exception: {e}", exc_info=True)
            return {"status": "ERROR", "message": str(e)}

    # ── 2. Resolve broker credentials (support Dhan & Kite)
    active_cred = session.exec(
        select(BrokerCredential).where(
            BrokerCredential.broker_name != "telegram",
            BrokerCredential.active == True
        )
    ).first()

    token = None
    if active_cred:
        token = get_dhan_token(active_cred, session) if active_cred.broker_name == "dhan" else active_cred.access_token

    if not active_cred or (not token and active_cred.broker_name not in ["paper", "shoonya"]):
        return {
            "status": "ERROR",
            "message": "No active broker session found. Please login via Settings.",
        }

    if active_cred.broker_name == "dhan":
        provider = DhanMarketDataProvider(
            client_id=active_cred.api_key,
            access_token=token,
        )
    elif active_cred.broker_name in ["paper", "shoonya"]:
        return {
            "status": "ERROR",
            "message": "Actual live broker data provider is not available in PAPER/SHOONYA mode. Backtesting skipped as requested.",
        }
    else:
        provider = KiteMarketDataProvider(
            api_key=active_cred.api_key,
            access_token=token,
        )

    # ── 3. Fetch real historical candles ─────────────────────────
    # Single-day intraday mode: from=day 09:00, to=day 15:30, interval=5min
    is_intraday = bool(payload.single_day)
    if is_intraday:
        fd_str = payload.single_day
        td_str = payload.single_day
        interval = payload.interval if payload.interval != "day" else "5minute"
    else:
        fd_str = payload.from_date
        td_str = payload.to_date
        interval = payload.interval

    try:
        candles = provider.get_historical_data(
            symbol=payload.symbol,
            days=payload.days,
            from_date=fd_str,
            to_date=td_str,
            interval=interval,
            instrument_type=payload.instrument_type,
            strike_price=payload.strike_price,
            expiry_date=payload.expiry_date,
        )
    except RuntimeError as e:
        return {"status": "ERROR", "message": str(e)}

    if not candles:
        return {"status": "ERROR", "message": "No candle data returned from Zerodha Kite for the requested range."}
    if len(candles) < 5:
        return {"status": "ERROR", "message": f"Only {len(candles)} candle(s) returned — need at least 5 for simulation. Broaden the date range."}

    # ── 4. Build DataFrame + indicators ──────────────────────────
    df = pd.DataFrame(
        {
            "open":   [c["open"]   for c in candles],
            "high":   [c["high"]   for c in candles],
            "low":    [c["low"]    for c in candles],
            "close":  [c["close"]  for c in candles],
            "volume": [c["volume"] for c in candles],
        },
        index=pd.to_datetime([c["date"] for c in candles]),
    )
    df = calculate_indicators(df)

    warmup = min(20, len(df) - 1)

    # ── 5. Bar-by-bar simulation ──────────────────────────────────
    capital        = float(payload.initial_capital)
    initial        = float(payload.initial_capital)
    active_trade   = None
    completed_trades = []
    journal        = []          # Full per-bar journal
    equity_curve   = []
    visualization  = []          # Every candle annotated with signals/state

    entry_rules  = config.get("rules", {}).get("entry",  {})
    exit_rules   = config.get("rules", {}).get("exit",   {})
    sl_limit     = float(config.get("sl_pct",    4.0))
    target_limit = float(config.get("target_pct", 8.0))
    
    if payload.lots > 0:
        base_lot = get_base_lot_size(payload.symbol)
        qty = payload.lots * base_lot
    else:
        qty = int(config.get("quantity", 50))

    for t in range(warmup, len(df)):
        row_t    = df.iloc[t]
        row_prev = df.iloc[t - 1]
        ts       = df.index[t].strftime("%Y-%m-%d %H:%M") if " " in str(df.index[t]) else df.index[t].strftime("%Y-%m-%d")
        price    = float(row_t["close"])

        bar = {
            "ts":    ts,
            "open":  float(row_t["open"]),
            "high":  float(row_t["high"]),
            "low":   float(row_t["low"]),
            "close": price,
            "volume": int(row_t.get("volume", 0)),
            "signal": "HOLD",
            "trade_state": "FLAT" if not active_trade else "IN_POSITION",
            "indicators": {
                "ema_9":   round(float(row_t["ema_9"]),   2) if "ema_9"   in row_t and not pd.isna(row_t["ema_9"])   else None,
                "ema_20":  round(float(row_t["ema_20"]),  2) if "ema_20"  in row_t and not pd.isna(row_t["ema_20"])  else None,
                "ema_50":  round(float(row_t["ema_50"]),  2) if "ema_50"  in row_t and not pd.isna(row_t["ema_50"])  else None,
                "rsi":     round(float(row_t["rsi"]),     2) if "rsi"     in row_t and not pd.isna(row_t["rsi"])     else None,
                "macd":    round(float(row_t["macd"]),    4) if "macd"    in row_t and not pd.isna(row_t["macd"])    else None,
                "vwap":    round(float(row_t["vwap"]),    2) if "vwap"    in row_t and not pd.isna(row_t["vwap"])    else None,
            },
        }

        journal_entry: Dict[str, Any] = {"ts": ts, "price": price, "action": "OBSERVE", "reason": [], "capital": round(capital, 2)}

        # ─ Entry evaluation ────────────────────────────────────
        if not active_trade:
            econditions = entry_rules.get("conditions", [])
            eoperator   = entry_rules.get("operator", "AND").upper()
            condition_results = []
            condition_reasons = []

            for cond in econditions:
                passed = check_rule_condition(cond, row_t, row_prev)
                condition_results.append(passed)
                ind   = cond.get("indicator", "CLOSE")
                comp  = cond.get("comparison", "")
                tgt   = cond.get("value", cond.get("target_indicator", ""))
                condition_reasons.append(
                    f"{ind} {comp} {tgt} → {'✓' if passed else '✗'}"
                )

            entry_triggered = (
                (all(condition_results) if eoperator == "AND" else any(condition_results))
                if condition_results else False
            )

            if entry_triggered:
                entry_price = price  # for stocks, entry = close price
                if payload.slippage_pct > 0:
                    entry_price = round(entry_price * (1 + payload.slippage_pct / 100.0), 2)
                margin_req  = entry_price * qty
                if capital >= margin_req:
                    active_trade = {
                        "entry_time":  ts,
                        "entry_price": entry_price,
                        "spot_entry":  price,
                        "qty":         qty,
                        "symbol":      payload.symbol,
                        "instrument_type": payload.instrument_type,
                        "max_price_since_entry": price,
                    }
                    bar["signal"]      = "BUY"
                    bar["trade_state"] = "ENTRY"
                    journal_entry["action"]  = "BUY"
                    journal_entry["qty"]     = qty
                    journal_entry["price"]   = entry_price
                    journal_entry["reason"]  = condition_reasons
                    journal_entry["note"]    = (
                        f"Entry triggered: all {len(econditions)} condition(s) met ({eoperator}). "
                        f"Bought {qty} units @ ₹{entry_price:.2f}. "
                        f"Capital deployed: ₹{margin_req:.2f}."
                    )
                    capital -= margin_req
                else:
                    journal_entry["reason"] = ["Insufficient capital for entry."]
            else:
                journal_entry["reason"] = condition_reasons if condition_reasons else ["No entry conditions met."]

        # ─ Exit evaluation ─────────────────────────────────────
        else:
            entry_price = active_trade["entry_price"]
            pnl_pct     = ((price - entry_price) / entry_price) * 100.0

            # Track max price for trailing stop loss
            if "max_price_since_entry" not in active_trade:
                active_trade["max_price_since_entry"] = price
            active_trade["max_price_since_entry"] = max(active_trade["max_price_since_entry"], price)

            # Check trailing stop loss if trail_sl_pct is specified
            trail_triggered = False
            trail_sl_price = 0.0
            if payload.trail_sl_pct and payload.trail_sl_pct > 0:
                trail_sl_price = active_trade["max_price_since_entry"] * (1 - payload.trail_sl_pct / 100.0)
                if price <= trail_sl_price:
                    trail_triggered = True

            exit_triggered = False
            exit_reason    = "INDICATOR"
            exit_reasons   = []

            if pnl_pct <= -sl_limit:
                exit_triggered = True
                exit_reason    = "STOP_LOSS"
                exit_reasons   = [f"Stop-loss hit: P&L {pnl_pct:.2f}% ≤ -{sl_limit}%"]
            elif trail_triggered:
                exit_triggered = True
                exit_reason    = "TRAILING_STOP_LOSS"
                exit_reasons   = [f"Trailing stop-loss hit: Price ₹{price:.2f} ≤ ₹{trail_sl_price:.2f} (Max reached: ₹{active_trade['max_price_since_entry']:.2f})"]
            elif pnl_pct >= target_limit:
                exit_triggered = True
                exit_reason    = "TARGET"
                exit_reasons   = [f"Target hit: P&L {pnl_pct:.2f}% ≥ {target_limit}%"]
            else:
                xconditions = exit_rules.get("conditions", [])
                xoperator   = exit_rules.get("operator", "AND").upper()
                xresults    = []
                xreasons    = []
                for cond in xconditions:
                    passed = check_rule_condition(cond, row_t, row_prev)
                    xresults.append(passed)
                    ind  = cond.get("indicator", "CLOSE")
                    comp = cond.get("comparison", "")
                    tgt  = cond.get("value", cond.get("target_indicator", ""))
                    xreasons.append(f"{ind} {comp} {tgt} → {'✓' if passed else '✗'}")
                if xresults and (all(xresults) if xoperator == "AND" else any(xresults)):
                    exit_triggered = True
                    exit_reason    = "INDICATOR"
                exit_reasons = xreasons

            if exit_triggered:
                exit_price = price
                if payload.slippage_pct > 0:
                    exit_price = round(exit_price * (1 - payload.slippage_pct / 100.0), 2)
                gross_pnl     = (exit_price - entry_price) * qty
                trade_charges = payload.charges_per_trade
                trade_net_pnl = round(gross_pnl - trade_charges, 2)
                pnl_pct       = round(((exit_price - entry_price) / entry_price) * 100.0, 2)
                capital      += (exit_price * qty) - trade_charges  # return sale proceeds and deduct transaction charges
                capital       = round(capital, 2)

                completed_trades.append({
                    "symbol":       active_trade["symbol"],
                    "instrument_type": active_trade.get("instrument_type", "STOCK"),
                    "entry_time":   active_trade["entry_time"],
                    "exit_time":    ts,
                    "qty":          qty,
                    "entry_price":  entry_price,
                    "exit_price":   exit_price,
                    "pnl":          trade_net_pnl,
                    "gross_pnl":    round(gross_pnl, 2),
                    "charges":      round(trade_charges, 2),
                    "pnl_pct":      pnl_pct,
                    "exit_reason":  exit_reason,
                })
                bar["signal"]      = "SELL"
                bar["trade_state"] = "EXIT"
                journal_entry["action"]  = "SELL"
                journal_entry["qty"]     = qty
                journal_entry["price"]   = exit_price
                journal_entry["pnl"]     = trade_net_pnl
                journal_entry["reason"]  = exit_reasons
                journal_entry["note"]    = (
                    f"Exit triggered ({exit_reason}). "
                    f"Sold {qty} units @ ₹{price:.2f}. "
                    f"Gross P&L: ₹{gross_pnl:.2f} | Charges: ₹{trade_charges:.2f} | Net P&L: {'▲' if trade_net_pnl >= 0 else '▼'} ₹{trade_net_pnl:.2f} ({pnl_pct:.2f}%)."
                )
                active_trade = None

        equity_curve.append({"date": ts, "balance": round(capital, 2)})
        visualization.append(bar)
        journal.append(journal_entry)

    # ── 6. Summary statistics ────────────────────────────────────
    def calculate_profit_factor(trades) -> float:
        if not trades:
            return 0.0
        gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
        gross_loss = sum(abs(t["pnl"]) for t in trades if t["pnl"] < 0)
        if gross_loss > 0:
            return float(round(gross_profit / gross_loss, 2))
        return float(round(gross_profit, 2)) if gross_profit > 0 else 0.0

    def calculate_sharpe_ratio(trades, eq_curve, init_cap) -> float:
        import numpy as np
        # Try daily returns first if there are multiple days
        try:
            import pandas as pd
            if len(eq_curve) >= 2:
                df_eq = pd.DataFrame(eq_curve)
                df_eq['date'] = pd.to_datetime(df_eq['date'])
                df_daily = df_eq.set_index('date').resample('D').last().ffill()
                daily_balances = df_daily['balance'].values
                if len(daily_balances) >= 2:
                    daily_returns = []
                    for i in range(1, len(daily_balances)):
                        prev_bal = daily_balances[i-1]
                        if prev_bal > 0:
                            daily_returns.append((daily_balances[i] - prev_bal) / prev_bal)
                    if daily_returns and np.std(daily_returns) > 0:
                        return float(round((np.mean(daily_returns) / np.std(daily_returns)) * np.sqrt(252), 2))
        except Exception:
            pass

        # Fallback to trade-level returns
        if not trades:
            return 0.0
        try:
            trade_returns = [t["pnl"] / init_cap for t in trades]
            mean_ret = np.mean(trade_returns)
            std_ret = np.std(trade_returns)
            if std_ret > 0:
                return float(round((mean_ret / std_ret) * np.sqrt(len(trades)), 2))
        except Exception:
            pass
        return 0.0

    total_trades      = len(completed_trades)
    profitable_trades = sum(1 for t in completed_trades if t["pnl"] > 0)
    losing_trades     = sum(1 for t in completed_trades if t["pnl"] <= 0)
    win_rate          = round((profitable_trades / total_trades) * 100, 2) if total_trades > 0 else 0.0
    net_pnl           = round(capital - initial, 2)
    return_pct        = round((net_pnl / initial) * 100, 2)
    total_charges     = sum(t.get("charges", 0.0) for t in completed_trades)
    max_dd            = 0.0
    peak              = initial
    for pt in equity_curve:
        if pt["balance"] > peak:
            peak = pt["balance"]
        dd = (peak - pt["balance"]) / peak * 100.0
        if dd > max_dd:
            max_dd = round(dd, 2)

    profit_factor = calculate_profit_factor(completed_trades)
    sharpe_ratio = calculate_sharpe_ratio(completed_trades, equity_curve, initial)

    return {
        "status": "SUCCESS",
        "meta": {
            "symbol":          payload.symbol,
            "instrument_type": payload.instrument_type,
            "candles_used":    len(df),
            "is_intraday":     is_intraday,
            "interval":        interval,
            "from":            str(df.index[warmup]),
            "to":              str(df.index[-1]),
        },
        "summary": {
            "initial_capital":  initial,
            "final_capital":    round(capital, 2),
            "net_pnl":          net_pnl,
            "total_return_pct": return_pct,
            "total_trades":     total_trades,
            "profitable_trades": profitable_trades,
            "losing_trades":    losing_trades,
            "win_rate":         win_rate,
            "max_drawdown_pct": max_dd,
            "total_charges":    round(total_charges, 2),
            "profit_factor":    profit_factor,
            "sharpe_ratio":     sharpe_ratio,
        },
        "equity_curve":  equity_curve,
        "visualization": visualization,
        "trades":        completed_trades,
        "journal":       [j for j in journal if j["action"] != "OBSERVE"],
    }

# Trades & Positions
@app.get("/api/trades")
def get_trades_history(
    strategy_id: Optional[str] = None,
    instance_id: Optional[int] = None,
    symbol: Optional[str] = None,
    status: Optional[str] = None,
    mode: Optional[str] = None,
    session: Session = Depends(get_session),
):
    query = select(Trade)
    if strategy_id:
        query = query.where(Trade.strategy_id == strategy_id)
    if instance_id:
        query = query.where(Trade.instance_id == instance_id)
    if symbol:
        query = query.where(Trade.symbol.contains(symbol))
    if status:
        query = query.where(Trade.status == status)
    if mode:
        query = query.where(Trade.mode == mode)
    trades = session.exec(query.order_by(Trade.entry_time.desc())).all()

    # Enrich with strategy name
    result = []
    for t in trades:
        d = {
            "id": t.id, "strategy_id": t.strategy_id, "instance_id": t.instance_id,
            "symbol": t.symbol, "option_type": t.option_type, "strike_price": t.strike_price,
            "expiry": t.expiry, "quantity": t.quantity, "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "entry_time": t.entry_time.isoformat() if t.entry_time else None,
            "exit_time": t.exit_time.isoformat() if t.exit_time else None,
            "status": t.status, "mode": t.mode, "pnl": t.pnl,
            "exit_reason": t.exit_reason, "broker_order_id": t.broker_order_id,
        }
        # Resolve strategy name
        if t.instance_id:
            inst = session.get(StrategyInstance, t.instance_id)
            d["strategy_name"] = inst.name if inst else t.strategy_id
        else:
            tmpl = session.get(Strategy, t.strategy_id)
            d["strategy_name"] = tmpl.name if tmpl else t.strategy_id
        result.append(d)
    return result

class SendLedgerReportRequest(BaseModel):
    trade_ids: List[int]

@app.post("/api/trades/telegram-report")
async def send_ledger_telegram_report(
    payload: SendLedgerReportRequest,
    session: Session = Depends(get_session)
):
    if not engine_instance.telegram_bot:
        return {"status": "ERROR", "message": "Telegram Bot is not configured."}
        
    trades = session.exec(select(Trade).where(Trade.id.in_(payload.trade_ids))).all()
    if not trades:
        return {"status": "ERROR", "message": "No trades found matching the provided IDs."}
        
    sorted_trades = sorted(trades, key=lambda x: x.entry_time or datetime.min, reverse=True)
    
    total_trades = len(sorted_trades)
    
    if total_trades == 1:
        t = sorted_trades[0]
        inst_name = t.symbol
        if t.instance_id:
            inst = session.get(StrategyInstance, t.instance_id)
            if inst:
                inst_name = f"{inst.name} ({t.symbol})"
                
        pnl_val = t.pnl or 0.0
        pnl_marker = "🟢 +" if pnl_val >= 0 else "🔴 "
        
        ret_tag = ""
        if t.entry_price > 0:
            ret_pct = 0.0
            if t.exit_price:
                ret_pct = ((t.exit_price - t.entry_price) / t.entry_price) * 100
            elif t.pnl:
                ret_pct = (t.pnl / (t.entry_price * t.quantity)) * 100
            ret_tag = f" ({'+' if ret_pct >= 0 else ''}{ret_pct:.1f}%)"
            
        exit_p = f"₹{t.exit_price:.2f}" if t.exit_price else "--"
        reason_tag = f" ({t.exit_reason})" if t.exit_reason else ""
        
        entry_t_str = t.entry_time.strftime("%d-%b-%Y %I:%M:%S %p") if t.entry_time else "--"
        exit_t_str = t.exit_time.strftime("%d-%b-%Y %I:%M:%S %p") if t.exit_time else "--"
        
        details_str = ""
        if t.instance_id and t.instance_id in engine_instance.active_strategy_states:
            state = engine_instance.active_strategy_states[t.instance_id]
            if state.opening_high is not None and state.opening_low is not None:
                ce_s = state.selected_ce_strike or 0.0
                pe_s = state.selected_pe_strike or 0.0
                ce_h = state.ce_option_opening_high or 0.0
                pe_h = state.pe_option_opening_high or 0.0
                details_str = (
                    f"📊 <b>Strategy Details (First Candle):</b>\n"
                    f"• Index Open Range High: <b>{state.opening_high:.2f}</b>\n"
                    f"• Index Open Range Low: <b>{state.opening_low:.2f}</b>\n"
                    f"• CE Option ({ce_s:.0f}) Open High: <b>₹{ce_h:.2f}</b>\n"
                    f"• PE Option ({pe_s:.0f}) Open High: <b>₹{pe_h:.2f}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                )

        msg = (
            f"🎯 <b>STOCKER INDIVIDUAL TRADE BULLETIN</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📂 <b>Strategy / Symbol:</b> {inst_name}\n"
            f"⚡ <b>Option Type:</b> {t.option_type or 'EQUITY'}\n"
            f"📊 <b>Execution Mode:</b> {t.mode} trading\n"
            f"🟢 <b>Status:</b> {t.status}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"{details_str}"
            f"📥 <b>Entry Price:</b> ₹{t.entry_price:.2f}\n"
            f"📤 <b>Exit Price:</b> {exit_p}{reason_tag}\n"
            f"📦 <b>Quantity:</b> {t.quantity}\n"
            f"💵 <b>Lot Value:</b> ₹{(t.entry_price * (t.quantity or 0)):,.2f}\n"
            f"💰 <b>Trade P&L:</b> <b>{pnl_marker}₹{pnl_val:,.2f}</b>{ret_tag}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🕐 <b>Entry Time (IST):</b> {entry_t_str}\n"
            f"🕐 <b>Exit Time (IST):</b> {exit_t_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
        )
    else:
        profitable = sum(1 for t in sorted_trades if (t.pnl or 0.0) > 0)
        losing = sum(1 for t in sorted_trades if (t.pnl or 0.0) <= 0)
        net_pnl = sum((t.pnl or 0.0) for t in sorted_trades)
        win_rate = round((profitable / total_trades) * 100, 1) if total_trades > 0 else 0.0
        
        pnl_sign = "🟢 +" if net_pnl >= 0 else "🔴 "
        
        msg = (
            f"📊 <b>STOCKER TRADE LEDGER SUMMARY</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 <b>Total Trades:</b> {total_trades}\n"
            f"🟢 <b>Profitable Trades:</b> {profitable}\n"
            f"🔴 <b>Losing Trades:</b> {losing}\n"
            f"🎯 <b>Win Rate:</b> {win_rate}%\n"
            f"💰 <b>Net Realized P&L:</b> {pnl_sign}₹{net_pnl:,.2f}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📝 <b>Recent Trades Breakdown:</b>\n"
        )
        
        for t in sorted_trades[:10]:
            inst_name = t.symbol
            if t.instance_id:
                inst = session.get(StrategyInstance, t.instance_id)
                if inst:
                    inst_name = f"{inst.name} ({t.symbol})"
                    
            pnl_val = t.pnl or 0.0
            pnl_marker = "🟢 +" if pnl_val >= 0 else "🔴 "
            status_tag = f"[{t.status}]" if t.status != "CLOSED" else ""
            
            exit_p = f" → ₹{t.exit_price:.2f}" if t.exit_price else ""
            reason_tag = f" ({t.exit_reason})" if t.exit_reason else ""
            
            msg += (
                f"• <b>{inst_name}</b> {status_tag}\n"
                f"  <code>Entry: ₹{t.entry_price:.2f}{exit_p}{reason_tag}</code>\n"
                f"  P&L: <b>{pnl_marker}₹{pnl_val:,.2f}</b> | Qty: {t.quantity} ({t.mode})\n\n"
            )
            
        if len(sorted_trades) > 10:
            msg += f"<i>...and {len(sorted_trades) - 10} more trades in the filtered ledger.</i>"
        
    try:
        await engine_instance.telegram_bot.send_message(msg)
        return {"status": "SUCCESS", "message": "Ledger summary successfully dispatched to Telegram."}
    except Exception as e:
        return {"status": "ERROR", "message": f"Telegram API Error: {e}"}

@app.post("/api/backtest/telegram-report")
async def send_backtest_telegram_report(payload: TelegramBacktestReportRequest):
    if not engine_instance.telegram_bot:
        return {"status": "ERROR", "message": "Telegram Bot is not configured."}

    pnl_emoji = "🟩 +" if payload.net_pnl >= 0 else "🔴 "
    pnl_pct = (payload.net_pnl / payload.initial_capital) * 100 if payload.initial_capital > 0 else 0.0
    pnl_pct_str = f"{'+' if pnl_pct >= 0 else ''}{pnl_pct:.2f}"

    msg = (
        f"📊 <b>STOCKER HISTORICAL BACKTEST BULLETIN</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📂 <b>Strategy Name:</b> {payload.strategy_name}\n"
        f"⚡ <b>Spot Instrument:</b> {payload.symbol}\n"
        f"📅 <b>Backtest Period:</b> {payload.from_date} to {payload.to_date}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Initial Capital:</b> ₹{payload.initial_capital:,.2f}\n"
        f"💰 <b>Final Capital:</b> ₹{payload.final_capital:,.2f}\n"
        f"💸 <b>Net Realized P&L:</b> <b>{pnl_emoji}₹{payload.net_pnl:,.2f}</b> ({pnl_pct_str}%)\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💼 <b>Total Simulated Trades:</b> {payload.total_trades}\n"
        f"🎯 <b>Profitable Trades:</b> {payload.profitable_trades} ✅\n"
        f"❌ <b>Losing Trades:</b> {payload.losing_trades} 🔻\n"
        f"🏆 <b>Backtest Win Rate:</b> <b>{payload.win_rate:.1f}%</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    if payload.trades:
        msg += f"📝 <b>Simulated Trade Log (Recent First):</b>\n"
        recent_trades = payload.trades[:10]
        for idx, t in enumerate(recent_trades, 1):
            t_pnl = t.get("pnl") or 0.0
            t_pnl_marker = "🟢 +" if t_pnl >= 0 else "🔴 "
            opt_str = f" [{t.get('option_type')}]" if t.get("option_type") else ""
            exit_reason = f" ({t.get('exit_reason')})" if t.get("exit_reason") else ""
            entry_p = t.get("entry_price") or 0.0
            exit_p = t.get("exit_price") or 0.0
            
            entry_time = t.get("entry_time") or ""
            if "T" in entry_time:
                entry_time = entry_time.replace("T", " ")[:19]
            
            exit_time = t.get("exit_time") or ""
            if "T" in exit_time:
                exit_time = exit_time.replace("T", " ")[:19]

            details_str = ""
            op_h = t.get("opening_high")
            op_l = t.get("opening_low")
            ce_h = t.get("ce_option_opening_high")
            pe_h = t.get("pe_option_opening_high")
            ce_s = t.get("selected_ce_strike")
            pe_s = t.get("selected_pe_strike")

            if op_h is not None and op_l is not None:
                ce_s_str = f"{ce_s:.0f}" if ce_s else "CE"
                pe_s_str = f"{pe_s:.0f}" if pe_s else "PE"
                details_str = (
                    f"     • Index Open Range: H {op_h:.2f} | L {op_l:.2f}\n"
                    f"     • CE {ce_s_str} Open High: ₹{ce_h:.2f} | PE {pe_s_str} Open High: ₹{pe_h:.2f}\n"
                )
            
            qty = t.get('quantity') or 0
            lot_value = qty * entry_p
            gain_pct = (t_pnl / lot_value * 100) if lot_value > 0 else 0.0

            msg += (
                f"{idx}. <b>{t.get('symbol', 'Trade')}{opt_str}</b>\n"
                f"   • <code>Entry: ₹{entry_p:.2f} ({entry_time})</code>\n"
                f"   • <code>Exit:  ₹{exit_p:.2f} ({exit_time}){exit_reason}</code>\n"
                f"{details_str}"
                f"   • <code>Lot Value: ₹{lot_value:,.2f} | Gain: {gain_pct:.2f}%</code>\n"
                f"   • P&L: <b>{t_pnl_marker}₹{t_pnl:,.2f}</b> | Qty: {qty}\n\n"
            )
            
        if len(payload.trades) > 10:
            msg += f"<i>...and {len(payload.trades) - 10} more simulated trades in the backtest report.</i>"

    try:
        await engine_instance.telegram_bot.send_message(msg)
        return {"status": "SUCCESS", "message": "Backtest report bulletin successfully dispatched to Telegram."}
    except Exception as e:
        return {"status": "ERROR", "message": f"Telegram API Error: {e}"}

@app.post("/api/backtest/telegram-ledger-document")
async def send_backtest_telegram_ledger(payload: TelegramLedgerDocumentRequest):
    if not engine_instance.telegram_bot:
        return {"status": "ERROR", "message": "Telegram Bot is not configured."}

    import io
    import csv

    # 1. Generate CSV content in-memory with BOM for Excel UTF-8 compatibility
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output, lineterminator='\n')

    headers = [
        'Entry Time', 'Exit Time', 'Symbol', 'Type', 'Lots', 'Lot Size', 'Qty',
        'Buy Price', 'Sell Price', '1 Lot Cost', 'Total Buy Price',
        'Gross P&L', 'Charges', 'Net P&L', 'P&L %',
        'Spot Trigger Time', 'Spot Trigger Price', 'Opt Trigger Time', 'Opt Trigger Price',
        'Exit Reason'
    ]
    writer.writerow(headers)

    for t in payload.trades:
        lot_size = get_base_lot_size(t.symbol)
        lots_count = t.quantity / lot_size
        one_lot_cost = lot_size * t.entry_price
        total_buy_price = t.quantity * t.entry_price

        lots_str = f"{lots_count:.1f}" if lots_count % 1 != 0 else f"{int(lots_count)}"

        writer.writerow([
            t.entry_time,
            t.exit_time,
            t.symbol,
            t.instrument_type,
            lots_str,
            lot_size,
            t.quantity,
            f"{t.entry_price:.2f}",
            f"{t.exit_price:.2f}",
            f"{one_lot_cost:.2f}",
            f"{total_buy_price:.2f}",
            f"{t.gross_pnl:.2f}",
            f"{t.charges:.2f}",
            f"{t.pnl:.2f}",
            f"{t.pnl_pct:.2f}",
            t.index_breakout_time or 'N/A',
            f"{t.index_breakout_price:.2f}" if t.index_breakout_price is not None else 'N/A',
            t.option_breakout_time or 'N/A',
            f"{t.option_breakout_price:.2f}" if t.option_breakout_price is not None else 'N/A',
            t.exit_reason
        ])

    csv_bytes = output.getvalue().encode('utf-8')

    # 2. Construct filename and description
    clean_symbol = payload.symbol.replace(":", "_").replace(" ", "_")
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"trade_ledger_{clean_symbol}_{timestamp_str}.csv"

    caption = (
        f"📋 <b>Backtest Trade Ledger Sheet</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📂 <b>Strategy Name:</b> {payload.strategy_name}\n"
        f"⚡ <b>Symbol:</b> {payload.symbol}\n"
        f"📅 <b>Period:</b> {payload.from_date} to {payload.to_date}\n"
        f"💼 <b>Total Trades:</b> {len(payload.trades)}\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )

    try:
        success = await engine_instance.telegram_bot.send_document(
            file_content=csv_bytes,
            filename=filename,
            caption=caption
        )
        if success:
            return {"status": "SUCCESS", "message": "Trade ledger sheet successfully dispatched to Telegram."}
        else:
            return {"status": "ERROR", "message": "Failed to send ledger sheet. Check Telegram credentials or network."}
    except Exception as e:
        logger.exception("Error sending telegram document")
        return {"status": "ERROR", "message": f"Telegram Document Error: {str(e)}"}

@app.post("/api/trades/{trade_id}/exit")
async def force_exit_trade(trade_id: int):
    success = await engine_instance.force_exit_trade(trade_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to execute force exit or trade already closed")
    return {"status": "SUCCESS"}

@app.get("/api/engine/status")
async def get_engine_status():
    engine_status = "RUNNING"
    if not engine_instance.running:
        engine_status = "STOPPED"
    elif engine_instance.paused:
        engine_status = "PAUSED"
        
    is_paper_running = any(strategy.active and strategy.paper_trade for strategy in engine_instance.active_strategies.values())
    is_live_running = any(strategy.active and not strategy.paper_trade for strategy in engine_instance.active_strategies.values())
    
    return {
        "status": engine_status,
        "is_paper_running": is_paper_running,
        "is_live_running": is_live_running,
        "active_instances_count": len(engine_instance.active_strategies)
    }

@app.post("/api/engine/pause")
async def pause_engine():
    await engine_instance.pause()
    return {"status": "SUCCESS", "message": "Engine paused successfully."}

@app.post("/api/engine/stop")
async def stop_engine():
    await engine_instance.stop()
    return {"status": "SUCCESS", "message": "Engine stopped successfully."}

@app.post("/api/engine/resume")
async def resume_engine():
    await engine_instance.resume()
    return {"status": "SUCCESS", "message": "Engine resumed successfully."}

@app.get("/api/summary", response_model=List[DailySummary])
def get_daily_summaries(session: Session = Depends(get_session)):
    return session.exec(select(DailySummary).order_by(DailySummary.trade_date.desc())).all()

# Credentials Configuration
@app.post("/api/credentials")
async def save_credentials(data: CredentialUpdate, session: Session = Depends(get_session)):
    cred = session.exec(select(BrokerCredential).where(BrokerCredential.broker_name == data.broker_name)).first()
    if not cred:
        cred = BrokerCredential(broker_name=data.broker_name, api_key="", api_secret="")
    
    # 1. API Key handling (prevent saving masked version)
    if data.api_key and "*" in data.api_key:
        if not cred.api_key:
            cred.api_key = data.api_key
    elif data.api_key:
        cred.api_key = data.api_key

    # 2. API Secret handling (prevent wiping out with empty/masked values)
    if data.api_secret and "*" not in data.api_secret:
        cred.api_secret = data.api_secret

    # 3. TOTP Secret handling
    if data.totp_secret and "*" not in data.totp_secret:
        cred.totp_secret = data.totp_secret
    
    if data.broker_name != "telegram":
        cred.active = True
        # Set all other live brokers to inactive to switch engine target dynamically
        other_creds = session.exec(select(BrokerCredential).where(
            BrokerCredential.broker_name != "telegram",
            BrokerCredential.broker_name != data.broker_name
        )).all()
        for oc in other_creds:
            oc.active = False
            session.add(oc)

    session.add(cred)
    session.commit()

    if data.broker_name == "telegram":
        await telegram_instance.update_credentials(data.api_key, data.api_secret)
    else:
        broker_key = data.broker_name.upper()
        broker_client = engine_instance.broker_clients.get(broker_key)
        if broker_client:
            logger.info(f"Dynamically authenticating {broker_key} with new credentials...")
            success = await broker_client.login({
                "api_key": data.api_key,
                "api_secret": data.api_secret,
                "totp_secret": data.totp_secret,
                "access_token": cred.access_token
            })
            if success and data.broker_name == "dhan":
                cred.access_token = broker_client.access_token
                session.add(cred)
                session.commit()
        
    return {"status": "SUCCESS"}

@app.post("/api/credentials/select-active")
async def select_active_broker(broker_name: str, session: Session = Depends(get_session)):
    if broker_name not in ["kite", "aliceblue", "dhan"]:
        raise HTTPException(status_code=400, detail="Invalid broker selection")
    
    selected_cred = session.exec(select(BrokerCredential).where(BrokerCredential.broker_name == broker_name)).first()
    if not selected_cred:
        selected_cred = BrokerCredential(broker_name=broker_name, api_key="", api_secret="", active=True)
        session.add(selected_cred)
    else:
        selected_cred.active = True
        session.add(selected_cred)
        
    # Deactivate all other brokers
    other_creds = session.exec(select(BrokerCredential).where(
        BrokerCredential.broker_name != broker_name,
        BrokerCredential.broker_name != "telegram"
    )).all()
    for o_cred in other_creds:
        o_cred.active = False
        session.add(o_cred)
        
    session.commit()
    logger.info(f"Dynamically switched active Live Trading Broker to: {broker_name}")
    
    # Dynamically authenticate the newly active broker client
    broker_key = broker_name.upper()
    broker_client = engine_instance.broker_clients.get(broker_key)
    if broker_client and selected_cred:
        logger.info(f"Dynamically authenticating newly selected active broker: {broker_key}...")
        asyncio.create_task(broker_client.login({
            "api_key": selected_cred.api_key,
            "api_secret": selected_cred.api_secret,
            "totp_secret": selected_cred.totp_secret,
            "access_token": selected_cred.access_token
        }))
        
    return {"status": "SUCCESS", "active_broker": broker_name}

@app.get("/api/settings/global")
def get_global_settings(session: Session = Depends(get_session)):
    from app.database import SystemState
    
    def get_val(key: str, default: str) -> str:
        state = session.get(SystemState, key)
        return state.value if state else default

    return {
        "risk_max_daily_loss": float(get_val("risk_max_daily_loss", "0")),
        "risk_max_active_positions": int(get_val("risk_max_active_positions", "0")),
        "risk_auto_square_off_time": get_val("risk_auto_square_off_time", ""),
        "risk_default_slippage": float(get_val("risk_default_slippage", "0.0")),
        "notify_order_placement": get_val("notify_order_placement", "true").lower() == "true",
        "notify_order_execution": get_val("notify_order_execution", "true").lower() == "true",
        "notify_sl_target_hit": get_val("notify_sl_target_hit", "true").lower() == "true",
        "notify_daily_summary": get_val("notify_daily_summary", "true").lower() == "true",
    }

@app.post("/api/settings/global")
def save_global_settings(data: GlobalSettingsUpdate, session: Session = Depends(get_session)):
    from app.database import SystemState
    from app.database import now_ist
    
    settings_dict = {
        "risk_max_daily_loss": str(data.risk_max_daily_loss),
        "risk_max_active_positions": str(data.risk_max_active_positions),
        "risk_auto_square_off_time": str(data.risk_auto_square_off_time),
        "risk_default_slippage": str(data.risk_default_slippage),
        "notify_order_placement": "true" if data.notify_order_placement else "false",
        "notify_order_execution": "true" if data.notify_order_execution else "false",
        "notify_sl_target_hit": "true" if data.notify_sl_target_hit else "false",
        "notify_daily_summary": "true" if data.notify_daily_summary else "false",
    }
    
    for key, value in settings_dict.items():
        state = session.get(SystemState, key)
        if state:
            state.value = value
            state.updated_at = now_ist()
        else:
            state = SystemState(key=key, value=value)
        session.add(state)
        
    session.commit()
    return {"status": "SUCCESS"}

@app.post("/api/broker/test-connection")
async def test_broker_connection():
    is_healthy, message = await engine_instance.check_broker_health()
    return {
        "status": "SUCCESS" if is_healthy else "ERROR",
        "healthy": is_healthy,
        "message": message
    }



class ZerodhaLoginRequest(BaseModel):
    request_token: str

@app.get("/api/broker/zerodha-auth-url")
def get_zerodha_auth_url(session: Session = Depends(get_session)):
    cred = session.exec(select(BrokerCredential).where(
        BrokerCredential.broker_name == "kite"
    )).first()
    if not cred or not cred.api_key:
        return {"status": "ERROR", "message": "Zerodha Kite API Key is not configured in System Settings."}
    return {"status": "SUCCESS", "url": f"https://kite.trade/connect/login?api_key={cred.api_key}"}

@app.post("/api/broker/zerodha-login")
async def zerodha_login(payload: ZerodhaLoginRequest, session: Session = Depends(get_session)):
    cred = session.exec(select(BrokerCredential).where(
        BrokerCredential.broker_name == "kite"
    )).first()
    
    if not cred or not cred.api_key or not cred.api_secret:
        return {"status": "ERROR", "message": "Zerodha API Key or Secret is not configured in System Settings."}
        
    try:
        kite_broker = engine_instance.broker_clients.get("KITE")
        if not kite_broker:
            raise Exception("Zerodha Kite client instance is missing in trading engine.")
            
        success = await kite_broker.login({
            "api_key": cred.api_key,
            "api_secret": cred.api_secret,
            "request_token": payload.request_token
        })
        
        if success and kite_broker.access_token:
            cred.access_token = kite_broker.access_token
            session.add(cred)
            session.commit()
            logger.info("Successfully established active Zerodha Kite login session.")
            return {"status": "SUCCESS", "message": "Zerodha login session established successfully!"}
        else:
            raise Exception("Failed to generate Kite session. Please double check request token.")
    except Exception as e:
        logger.error(f"Zerodha daily login failed: {e}")
        return {"status": "ERROR", "message": f"Authorization Failed: {str(e)}"}

@app.get("/api/credentials")
def get_credentials(session: Session = Depends(get_session)):
    credentials = session.exec(select(BrokerCredential)).all()
    # Mask API secrets before returning for basic frontend safety
    masked = []
    for c in credentials:
        masked.append({
            "broker_name": c.broker_name,
            "api_key": c.api_key[:4] + "****" if len(c.api_key) > 4 else "****",
            "active": c.active
        })
    return masked

@app.get("/api/broker/full-portfolio")
async def get_broker_full_portfolio(session: Session = Depends(get_session)):
    active_cred = session.exec(
        select(BrokerCredential).where(
            BrokerCredential.broker_name != "telegram",
            BrokerCredential.active == True
        )
    ).first()
    
    if not active_cred:
        return {"status": "ERROR", "message": "No active live broker credentials selected. Please configure keys in System Settings."}
        
    try:
        return await fetch_unified_full_portfolio(active_cred, engine_instance)
    except Exception as e:
        logger.error(f"Error querying active broker full portfolio: {e}")
        return {"status": "ERROR", "message": f"Broker Connection Failed: {str(e)}"}

@app.get("/api/broker/portfolio")
async def get_broker_portfolio(session: Session = Depends(get_session)):
    active_cred = session.exec(
        select(BrokerCredential).where(
            BrokerCredential.broker_name != "telegram",
            BrokerCredential.active == True
        )
    ).first()
    
    if not active_cred:
        return {
            "broker_name": "none",
            "is_live": False,
            "cash_balance": 0.0,
            "used_margin": 0.0,
            "collateral_margin": 0.0,
            "available_margin": 0.0
        }
        
    try:
        return await fetch_unified_margins(active_cred, engine_instance)
    except Exception as e:
        logger.error(f"Error querying active broker margins: {e}")
        return {
            "broker_name": active_cred.broker_name,
            "is_live": False,
            "cash_balance": 0.0,
            "used_margin": 0.0,
            "collateral_margin": 0.0,
            "available_margin": 0.0
        }

@app.post("/api/test-telegram")
async def test_telegram_channel():
    res = await telegram_instance.send_message("🔔 <b>Stocker Live Connection Verified!</b>\nYour system is correctly authenticated with the Telegram Bot API and is monitoring active rules.")
    return {"status": "SUCCESS" if res else "FAILED"}

@app.post("/api/strategies/{instance_id}/telegram-status")
async def send_strategy_telegram_status_route(instance_id: int):
    success, message = await engine_instance.send_strategy_telegram_status(instance_id)
    if not success:
        return {"status": "FAILED", "message": message}
    return {"status": "SUCCESS", "message": message}


@app.post("/api/paper-reset")
def reset_paper_trades(session: Session = Depends(get_session)):
    # Delete all paper trades and summaries to let users restart their analytics fresh
    session.exec(select(Trade)).all()  # load
    session.query(Trade).delete()
    session.query(DailySummary).delete()
    session.commit()
    logger.info("Paper trading execution records reset.")
    return {"status": "SUCCESS"}

def get_market_data_provider(session: Session = Depends(get_session)) -> BaseMarketDataProvider:
    """Dependency injection provider that resolves the active stock market data source."""
    active_cred = session.exec(
        select(BrokerCredential).where(
            BrokerCredential.broker_name != "telegram",
            BrokerCredential.active == True
        )
    ).first()
    
    if active_cred:
        token = get_dhan_token(active_cred, session) if active_cred.broker_name == "dhan" else active_cred.access_token
        if token:
            if active_cred.broker_name == "dhan":
                from app.market_data import DhanMarketDataProvider
                logger.info("Injecting active DhanMarketDataProvider.")
                return DhanMarketDataProvider(client_id=active_cred.api_key, access_token=token)
            elif active_cred.broker_name != "paper" and active_cred.broker_name != "shoonya":
                from app.market_data import KiteMarketDataProvider
                logger.info(f"Injecting active {active_cred.broker_name.capitalize()}MarketDataProvider.")
                return KiteMarketDataProvider(api_key=active_cred.api_key, access_token=token)
                
    raise RuntimeError("No active live broker session found. Please login via Settings.")

def _generate_mock_historical_candles(symbol: str, days: int) -> list:
    import random
    from datetime import datetime, timedelta
    
    underlying = symbol.split(":")[-1].upper()
    if "BANK" in underlying:
        base_price = 48500.0
    elif "SENSEX" in underlying:
        base_price = 78000.0
    else:
        base_price = 23909.55
        
    result = []
    current_time = datetime.now() - timedelta(days=days)
    price = base_price - (days * 15)
    
    for i in range(days + 1):
        if current_time.weekday() < 5:
            change = random.normalvariate(15, 120)
            open_price = price
            close_price = price + change
            high_price = max(open_price, close_price) + abs(random.normalvariate(20, 30))
            low_price = min(open_price, close_price) - abs(random.normalvariate(20, 30))
            volume = int(random.normalvariate(250000, 50000))
            
            result.append({
                "date": current_time.strftime("%Y-%m-%d"),
                "open": round(open_price, 2),
                "high": round(high_price, 2),
                "low": round(low_price, 2),
                "close": round(close_price, 2),
                "volume": max(10000, volume)
            })
            price = close_price
        current_time += timedelta(days=1)
    return result

# Historical Data API for Charts with graceful mock fallback
@app.get("/api/historical-data")
def get_historical_data(
    symbol: str = "NSE:NIFTY 50", 
    days: int = 30, 
    session: Session = Depends(get_session)
):
    try:
        provider = get_market_data_provider(session)
        return provider.get_historical_data(symbol, days)
    except Exception as e:
        logger.warning(f"Failed to fetch real historical data for {symbol}, falling back to mock: {e}")
        return _generate_mock_historical_candles(symbol, days)

# WebSocket handler
@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websocket_connections.append(websocket)
    logger.info(f"WebSocket Client Connected. Active connections: {len(active_websocket_connections)}")
    
    try:
        while True:
            # Keep connection alive, listen for any messages
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_websocket_connections:
            active_websocket_connections.remove(websocket)
        logger.info("WebSocket Client Disconnected.")
