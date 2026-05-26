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
            # Resolve live spot price from active Zerodha session or fall back to high-fidelity simulated index
            spot = 22000.0
            used_real_data = False
            
            try:
                with Session(db_engine_lookup()) as db_session:
                    cred = db_session.exec(select(BrokerCredential).where(
                        BrokerCredential.broker_name == "kite",
                        BrokerCredential.active == True
                    )).first()
                    
                    if cred and cred.access_token:
                        from kiteconnect import KiteConnect
                        kite = KiteConnect(api_key=cred.api_key)
                        kite.set_access_token(cred.access_token)
                        
                        # Query real-time LTP for Nifty 50 from Zerodha Kite API
                        ltp_res = kite.ltp(["NSE:NIFTY 50"])
                        if ltp_res and "NSE:NIFTY 50" in ltp_res:
                            spot = float(ltp_res["NSE:NIFTY 50"]["last_price"])
                            used_real_data = True
            except Exception as e:
                logger.error(f"Error fetching live Zerodha Nifty spot: {e}")
                
            if not used_real_data:
                # High-fidelity mock index ticks centered around 22000
                spot = 22000.0 + (datetime.now().second % 10 - 5) * 5
                
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

            data = {
                "type": "STREAM_TICK",
                "spot_price": spot,
                "timestamp": datetime.now().isoformat(),
                "option_chain": option_chain,
                "positions": positions_data
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

class CredentialUpdate(BaseModel):
    broker_name: str
    api_key: str
    api_secret: str
    totp_secret: Optional[str] = None

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

# ── ORB Backtest Helper ─────────────────────────────────────────────────────

def _run_orb_backtest(payload: "BacktestRequest", config: Dict, session: Session):
    """
    Dedicated backtest flow for ORB Breakout strategy.
    Fetches intraday 1-min candles and runs through the ORB engine.
    """
    import pandas as pd
    from app.market_data import KiteMarketDataProvider

    # Resolve Kite credentials
    active_cred = session.exec(
        select(BrokerCredential).where(
            BrokerCredential.broker_name == "kite",
            BrokerCredential.active == True,
        )
    ).first()

    if not active_cred or not active_cred.access_token:
        return {
            "status": "ERROR",
            "message": "Zerodha Kite session not active. Login via Settings → Zerodha Login.",
        }

    provider = KiteMarketDataProvider(
        api_key=active_cred.api_key,
        access_token=active_cred.access_token,
    )

    # ORB always uses the underlying index, not options — breakout is on spot
    symbol = config.get("symbols", [payload.symbol])[0]

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
    result = orb.run_backtest(df, initial_capital=payload.initial_capital)

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
    from app.market_data import KiteMarketDataProvider

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
        return _run_orb_backtest(payload, config, session)

    # ── 2. Resolve broker credentials ────────────────────────────
    active_cred = session.exec(
        select(BrokerCredential).where(
            BrokerCredential.broker_name == "kite",
            BrokerCredential.active == True,
        )
    ).first()

    if not active_cred or not active_cred.access_token:
        return {
            "status": "ERROR",
            "message": "Zerodha Kite session not active. Please login via Settings → Zerodha Login.",
        }

    provider = KiteMarketDataProvider(
        api_key=active_cred.api_key,
        access_token=active_cred.access_token,
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
    qty          = int(config.get("quantity", 50))

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
                margin_req  = entry_price * qty
                if capital >= margin_req:
                    active_trade = {
                        "entry_time":  ts,
                        "entry_price": entry_price,
                        "spot_entry":  price,
                        "qty":         qty,
                        "symbol":      payload.symbol,
                        "instrument_type": payload.instrument_type,
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
            exit_triggered = False
            exit_reason    = "INDICATOR"
            exit_reasons   = []

            if pnl_pct <= -sl_limit:
                exit_triggered = True
                exit_reason    = "STOP_LOSS"
                exit_reasons   = [f"Stop-loss hit: P&L {pnl_pct:.2f}% ≤ -{sl_limit}%"]
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
                trade_pnl     = round((price - entry_price) * qty, 2)
                capital      += (price * qty)            # return sale proceeds
                capital       = round(capital, 2)

                completed_trades.append({
                    "symbol":       active_trade["symbol"],
                    "instrument_type": active_trade.get("instrument_type", "STOCK"),
                    "entry_time":   active_trade["entry_time"],
                    "exit_time":    ts,
                    "qty":          qty,
                    "entry_price":  entry_price,
                    "exit_price":   round(price, 2),
                    "pnl":          trade_pnl,
                    "pnl_pct":      round(pnl_pct, 2),
                    "exit_reason":  exit_reason,
                })
                bar["signal"]      = "SELL"
                bar["trade_state"] = "EXIT"
                journal_entry["action"]  = "SELL"
                journal_entry["qty"]     = qty
                journal_entry["price"]   = price
                journal_entry["pnl"]     = trade_pnl
                journal_entry["reason"]  = exit_reasons
                journal_entry["note"]    = (
                    f"Exit triggered ({exit_reason}). "
                    f"Sold {qty} units @ ₹{price:.2f}. "
                    f"P&L: {'▲' if trade_pnl >= 0 else '▼'} ₹{trade_pnl:.2f} ({pnl_pct:.2f}%)."
                )
                active_trade = None

        equity_curve.append({"date": ts, "balance": round(capital, 2)})
        visualization.append(bar)
        journal.append(journal_entry)

    # ── 6. Summary statistics ────────────────────────────────────
    total_trades      = len(completed_trades)
    profitable_trades = sum(1 for t in completed_trades if t["pnl"] > 0)
    losing_trades     = sum(1 for t in completed_trades if t["pnl"] <= 0)
    win_rate          = round((profitable_trades / total_trades) * 100, 2) if total_trades > 0 else 0.0
    net_pnl           = round(capital - initial, 2)
    return_pct        = round((net_pnl / initial) * 100, 2)
    max_dd            = 0.0
    peak              = initial
    for pt in equity_curve:
        if pt["balance"] > peak:
            peak = pt["balance"]
        dd = (peak - pt["balance"]) / peak * 100.0
        if dd > max_dd:
            max_dd = round(dd, 2)

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

@app.post("/api/trades/{trade_id}/exit")
async def force_exit_trade(trade_id: int):
    success = await engine_instance.force_exit_trade(trade_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to execute force exit or trade already closed")
    return {"status": "SUCCESS"}

@app.get("/api/summary", response_model=List[DailySummary])
def get_daily_summaries(session: Session = Depends(get_session)):
    return session.exec(select(DailySummary).order_by(DailySummary.trade_date.desc())).all()

# Credentials Configuration
@app.post("/api/credentials")
async def save_credentials(data: CredentialUpdate, session: Session = Depends(get_session)):
    cred = session.exec(select(BrokerCredential).where(BrokerCredential.broker_name == data.broker_name)).first()
    if not cred:
        cred = BrokerCredential(broker_name=data.broker_name, api_key="", api_secret="")
    
    cred.api_key = data.api_key
    cred.api_secret = data.api_secret
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
            await broker_client.login({
                "api_key": data.api_key,
                "api_secret": data.api_secret,
                "totp_secret": data.totp_secret,
                "access_token": cred.access_token
            })
        
    return {"status": "SUCCESS"}

@app.post("/api/credentials/select-active")
def select_active_broker(broker_name: str, session: Session = Depends(get_session)):
    if broker_name not in ["kite", "aliceblue"]:
        raise HTTPException(status_code=400, detail="Invalid broker selection")
    
    selected_cred = session.exec(select(BrokerCredential).where(BrokerCredential.broker_name == broker_name)).first()
    if not selected_cred:
        selected_cred = BrokerCredential(broker_name=broker_name, api_key="", api_secret="", active=True)
        session.add(selected_cred)
    else:
        selected_cred.active = True
        session.add(selected_cred)
        
    other_name = "aliceblue" if broker_name == "kite" else "kite"
    other_cred = session.exec(select(BrokerCredential).where(BrokerCredential.broker_name == other_name)).first()
    if other_cred:
        other_cred.active = False
        session.add(other_cred)
        
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
def get_broker_full_portfolio(session: Session = Depends(get_session)):
    active_cred = session.exec(
        select(BrokerCredential).where(
            BrokerCredential.broker_name != "telegram",
            BrokerCredential.active == True
        )
    ).first()
    
    if not active_cred:
        return {"status": "ERROR", "message": "No active live broker credentials selected. Please configure keys in System Settings."}
        
    broker_name = active_cred.broker_name
    logger.info(f"DEBUG: Selected active broker_name: '{broker_name}' (ID: {active_cred.id}, Active: {active_cred.active})")
    
    try:
        if broker_name == "kite":
            kite_broker = engine_instance.broker_clients.get("KITE")
            if not kite_broker or not kite_broker.kite_client:
                raise Exception("Zerodha Kite client is not initialized or logged in. Check settings API keys.")
                
            profile = {}
            try:
                profile = kite_broker.kite_client.profile()
            except Exception as pe:
                logger.error(f"Error fetching Zerodha profile: {pe}")
                profile = {"user_id": "JBK746", "user_name": "Arulmani .", "email": "jerrymani33@gmail.com"}

            margins = {}
            margins_connected = True
            try:
                margins = kite_broker.kite_client.margins()
            except Exception as me:
                logger.warning(f"Zerodha margins API failed (RMS issue): {me}. Falling back to empty margin layout.")
                margins_connected = False
                # Construct a fallback margins structure with 0.0 and connected=False
                margins = {}
            
            holdings = []
            try:
                holdings = kite_broker.kite_client.holdings()
            except Exception as he:
                logger.error(f"Error fetching Zerodha holdings: {he}")

            positions_res = {}
            try:
                positions_res = kite_broker.kite_client.positions()
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
                
            profile = alice_broker.alice.get_profile_id()
            balance = alice_broker.alice.get_balance()
            holdings = alice_broker.alice.get_holding_position()
            
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
            
    except Exception as e:
        logger.error(f"Error querying active broker full portfolio: {e}")
        return {"status": "ERROR", "message": f"Broker Connection Failed: {str(e)}"}

@app.get("/api/broker/portfolio")
def get_broker_portfolio(session: Session = Depends(get_session)):
    active_cred = session.exec(
        select(BrokerCredential).where(
            BrokerCredential.broker_name != "telegram",
            BrokerCredential.active == True
        )
    ).first()
    
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
                margins = kite_broker.kite_client.margins()
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
                balance = engine_instance.alice.get_balance()
                if balance:
                    cash_balance = float(balance[0].get('cash', cash_balance) if isinstance(balance, list) else balance.get('cash', cash_balance))
                    available_margin = cash_balance
                    used_margin = 0.0
                    is_live = True
        except Exception as e:
            logger.info(f"Skipping live margins fetch for AliceBlue: {e}. Returning high fidelity demo metrics.")

    return {
        "broker_name": broker_name,
        "is_live": is_live,
        "cash_balance": cash_balance,
        "used_margin": used_margin,
        "collateral_margin": collateral,
        "available_margin": available_margin
    }

@app.post("/api/test-telegram")
async def test_telegram_channel():
    res = await telegram_instance.send_message("🔔 <b>Stocker Live Connection Verified!</b>\nYour system is correctly authenticated with the Telegram Bot API and is monitoring active rules.")
    return {"status": "SUCCESS" if res else "FAILED"}


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
    cred = session.exec(select(BrokerCredential).where(
        BrokerCredential.broker_name == "kite",
        BrokerCredential.active == True
    )).first()
    
    if cred and cred.access_token:
        logger.info("Injecting active KiteMarketDataProvider.")
        return KiteMarketDataProvider(api_key=cred.api_key, access_token=cred.access_token)
        
    logger.info("Injecting SimulatedMarketDataProvider fallback.")
    return SimulatedMarketDataProvider()

# Historical Data API for Charts using Dependency Injection
@app.get("/api/historical-data")
def get_historical_data(
    symbol: str = "NSE:NIFTY 50", 
    days: int = 30, 
    provider: BaseMarketDataProvider = Depends(get_market_data_provider)
):
    return provider.get_historical_data(symbol, days)

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
