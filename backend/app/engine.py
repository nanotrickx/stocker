import json
import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Dict, List, Any, Optional, Tuple
from sqlmodel import Session, select
from app.database import engine as db_engine, Strategy, StrategyInstance, Trade, BrokerCredential, DailySummary, SystemState, now_ist, IST
from app.broker_manager import get_broker
from app.analytics import calculate_indicators, check_rule_condition
from app.orb_strategy import ORBState
import pandas as pd

logger = logging.getLogger("Stocker.Engine")

class ExecutionEngine:
    def __init__(self):
        self.active_strategies: Dict[int, StrategyInstance] = {}
        self.broker_clients = {
            "PAPER": get_broker("PAPER"),
            "KITE": get_broker("KITE"),
            "SHOONYA": get_broker("SHOONYA"),
            "ALICEBLUE": get_broker("ALICEBLUE"),
            "DHAN": get_broker("DHAN")
        }
        self.telegram_bot = None  # Injected later
        self.running = False
        self.historical_data_cache: Dict[str, pd.DataFrame] = {}
        self.orb_states: Dict[str, ORBState] = {}  # per-strategy ORB state
        self._kite_client = None  # cached KiteConnect instance
        self.daily_start_sent: Dict[str, bool] = {}
        self.daily_summary_sent: Dict[str, bool] = {}
        self.pre_market_health_check_sent: Dict[str, bool] = {}
        self.strategy_logs: List[Dict[str, Any]] = []

    def log_strategy_activity(self, instance_id: int, strategy_name: str, message: str):
        """Append a log entry in memory with a capped size of 100 entries to ensure 0% performance overhead."""
        if message.startswith("[EVAL]"):
            is_live = False
            try:
                is_live = self._get_kite_client() is not None
            except Exception:
                pass
            feed_label = "🟢 [LIVE]" if is_live else "🟡 [SIMULATED]"
            message = message.replace("[EVAL]", f"[EVAL] {feed_label}")
            
        log_entry = {
            "timestamp": now_ist().strftime("%H:%M:%S"),
            "strategy_id": instance_id,
            "strategy_name": strategy_name,
            "message": message
        }
        self.strategy_logs.append(log_entry)
        if len(self.strategy_logs) > 100:
            self.strategy_logs.pop(0)

    def is_market_holiday_today(self) -> Tuple[bool, Optional[str]]:
        """Check if today is weekend or an exchange declared holiday."""
        now = now_ist()
        if now.weekday() >= 5:
            return True, "Weekend (Saturday/Sunday)"
        
        # Comprehensive NSE Trading Holiday List for 2026
        holidays_2026 = {
            "2026-01-26": "Republic Day",
            "2026-03-03": "Holi",
            "2026-03-26": "Shri Ram Navami",
            "2026-03-31": "Shri Mahavir Jayanti",
            "2026-04-03": "Good Friday",
            "2026-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
            "2026-05-01": "Maharashtra Day",
            "2026-05-28": "Bakri Id (Eid-ul-Adha)",
            "2026-06-26": "Muharram",
            "2026-09-14": "Ganesh Chaturthi",
            "2026-10-02": "Mahatma Gandhi Jayanti",
            "2026-10-21": "Dussehra",
            "2026-11-25": "Guru Nanak Jayanti",
            "2026-12-25": "Christmas"
        }
        
        date_str = now.strftime("%Y-%m-%d")
        if date_str in holidays_2026:
            return True, holidays_2026[date_str]
            
        return False, None

    def get_recent_logs(self) -> List[Dict[str, Any]]:
        """Retrieve the in-memory strategy activity logs."""
        return self.strategy_logs

    def set_telegram_bot(self, telegram_bot):
        self.telegram_bot = telegram_bot

    async def check_broker_health(self) -> Tuple[bool, str]:
        """
        Validates the current active broker's connectivity.
        Returns:
            Tuple[bool, str]: (is_healthy, detail_message)
        """
        try:
            with Session(db_engine) as session:
                active_cred = session.exec(select(BrokerCredential).where(
                    BrokerCredential.broker_name != "telegram",
                    BrokerCredential.active == True
                )).first()
                
                if not active_cred:
                    return False, "No active broker credentials configured in the database."

                broker_name = active_cred.broker_name
                
                if broker_name == "kite":
                    kite_broker = self.broker_clients.get("KITE")
                    if not kite_broker or not kite_broker.kite_client:
                        return False, "Zerodha Kite client is not initialized. Needs manual login."
                    try:
                        # Attempt a lightweight margins call to verify API session token
                        kite_broker.kite_client.margins()
                        return True, "Zerodha Kite connection is active and healthy."
                    except Exception as e:
                        return False, f"Zerodha Kite API session is inactive or expired: {e}"

                elif broker_name == "aliceblue":
                    alice_broker = self.broker_clients.get("ALICEBLUE")
                    if not alice_broker or not hasattr(alice_broker, 'alice') or not alice_broker.alice:
                        return False, "Alice Blue client is not initialized. Needs manual login."
                    try:
                        balance = alice_broker.alice.get_balance()
                        if balance:
                            return True, "Alice Blue connection is active and healthy."
                        return False, "Alice Blue returned an empty balance check."
                    except Exception as e:
                        return False, f"Alice Blue API session is inactive or expired: {e}"
                        
                elif broker_name == "dhan":
                    dhan_broker = self.broker_clients.get("DHAN")
                    if not dhan_broker or not dhan_broker.access_token:
                        return False, "Dhan client is not initialized or access token is missing."
                    try:
                        profile = await dhan_broker.get_profile()
                        if profile and profile.get("status") != "ERROR":
                            return True, "Dhan connection is active and healthy."
                        return False, f"Dhan API returned unhealthy state: {profile}"
                    except Exception as e:
                        return False, f"Dhan API connection error during health check: {e}"

                elif broker_name == "paper":
                    return True, "Paper trading sandbox environment is active."
                    
                else:
                    return False, f"Unknown broker broker_name '{broker_name}' configured."
        except Exception as e:
            return False, f"Unexpected error during connection health check: {e}"

    def _get_system_state(self, key: str) -> Optional[str]:
        try:
            with Session(db_engine) as session:
                state = session.get(SystemState, key)
                return state.value if state else None
        except Exception as e:
            logger.warning(f"Error fetching system state for {key}: {e}")
            return None

    def _set_system_state(self, key: str, value: str):
        try:
            with Session(db_engine) as session:
                state = session.get(SystemState, key)
                if state:
                    state.value = value
                    state.updated_at = now_ist()
                else:
                    state = SystemState(key=key, value=value)
                session.add(state)
                session.commit()
        except Exception as e:
            logger.warning(f"Error setting system state for {key}: {e}")

    def get_or_create_orb_state(self, strategy: StrategyInstance, config: dict, spot: float = 0.0) -> ORBState:
        now = now_ist()
        sid = strategy.id
        today_key = f"{sid}_{now.strftime('%Y%m%d')}"

        if "_day_keys" not in self.orb_states:
            self.orb_states["_day_keys"] = {}
        day_keys = self.orb_states["_day_keys"]

        if sid in self.orb_states and day_keys.get(sid) != today_key:
            del self.orb_states[sid]

        if sid not in self.orb_states:
            state = ORBState()
            self.orb_states[sid] = state
            day_keys[sid] = today_key

            # Reconstruct today's ORBState from SQLite to handle server restarts safely
            try:
                with Session(db_engine) as db_session:
                    today_start = datetime.combine(now.date(), time.min, tzinfo=IST)
                    today_end = datetime.combine(now.date(), time.max, tzinfo=IST)
                    trades_today = db_session.exec(select(Trade).where(
                        Trade.instance_id == sid,
                        Trade.entry_time >= today_start,
                        Trade.entry_time <= today_end
                    )).all()

                    risk = config.get("risk", {})
                    sl_pct = risk.get("stop_loss_pct", 10.0)

                    if trades_today:
                        state.trades_taken = []
                        # Sort by entry time to preserve exact logical sequence
                        sorted_trades = sorted(trades_today, key=lambda x: x.entry_time)
                        for t in sorted_trades:
                            direction = "BULLISH" if t.option_type == "CE" else "BEARISH"
                            state.trades_taken.append(direction)
                            if t.exit_reason == "STOP_LOSS":
                                state.first_trade_hit_sl = True

                        open_trade = next((t for t in sorted_trades if t.status == "OPEN"), None)
                        if open_trade:
                            state.phase = "IN_POSITION"
                            state.selected_option_type = open_trade.option_type
                            state.selected_strike = open_trade.strike_price
                            state.entry_price = open_trade.entry_price
                            state.entry_time = open_trade.entry_time.isoformat()
                            
                            # Estimate target and SL levels based on first trade exit behavior
                            current_target_pct = 15.0 if any(t.exit_reason == "STOP_LOSS" for t in trades_today) else 10.0
                            state.target_price = round(open_trade.entry_price * (1 + current_target_pct / 100), 2)
                            state.stop_loss_price = round(open_trade.entry_price * (1 - sl_pct / 100), 2)
                            state.breakout_price = spot
                            state.breakout_time = open_trade.entry_time.isoformat()
                            logger.info(f"ORB [{strategy.name}] Server restart detected active trade: restored {open_trade.symbol} @ ₹{open_trade.entry_price}. Phase → IN_POSITION.")
                        else:
                            # Re-calibrate phase when all trades today are closed
                            any_sl = any(t.exit_reason == "STOP_LOSS" for t in trades_today)
                            if any_sl and len(state.trades_taken) < 2:
                                state.first_trade_hit_sl = True
                                state.phase = "WAITING_BREAKOUT"
                                # Opposite side breakouts triggers are active
                                state.index_high_broke_out = False
                                state.index_low_broke_out = False
                                logger.info(f"ORB [{strategy.name}] Server restart detected closed SL trade: restored Phase → WAITING_BREAKOUT for opposite direction.")
                            else:
                                state.phase = "DONE"
                                logger.info(f"ORB [{strategy.name}] Server restart detected profit or 2 trades taken: restored Phase → DONE.")
            except Exception as e:
                logger.error(f"Error restoring ORB daily trades state from DB: {e}")

        return self.orb_states[sid]

    async def send_strategy_telegram_status(self, instance_id: int) -> Tuple[bool, str]:
        """
        Generates and sends a rich, real-time Telegram status update bulletin for an active strategy.
        """
        try:
            if not self.telegram_bot:
                return False, "Telegram Bot is not initialized."

            with Session(db_engine) as session:
                instance = session.get(StrategyInstance, instance_id)
                if not instance:
                    return False, f"Strategy deployment instance ID {instance_id} not found."

                config = instance.get_config()
                symbol = instance.symbol
                strategy_type = config.get("strategy_type", "custom")
                active_status = "🟢 ACTIVE/RUNNING" if instance.active else "🔴 PAUSED/INACTIVE"
                mode_status = "SANDBOX (PAPER)" if instance.paper_trade else "LIVE TRADING"

                if strategy_type == "orb_breakout":
                    # Estimate current spot price for state reconstruction if not in memory
                    spot_price = 0.0
                    try:
                        spot_price = await self.fetch_live_spot(symbol)
                    except Exception:
                        pass
                    
                    state = self.get_or_create_orb_state(instance, config, spot_price)

                    # Calculate dynamic metrics for real-time reporting
                    spot_price = await self.fetch_live_spot(symbol)
                    
                    ce_breakout_status = "🔴 Waiting"
                    pe_breakout_status = "🔴 Waiting"
                    
                    if state.selected_ce_strike:
                        curr_ce = round(max(0.5, max(0, spot_price - state.selected_ce_strike) + state.selected_ce_strike * 0.002), 2)
                        if curr_ce >= state.ce_option_opening_high:
                            ce_breakout_status = f"✅ BREACHED (₹{curr_ce} >= ₹{state.ce_option_opening_high})"
                        else:
                            ce_breakout_status = f"⏳ WAITING (₹{curr_ce} / Target: ₹{state.ce_option_opening_high})"
                            
                    if state.selected_pe_strike:
                        curr_pe = round(max(0.5, max(0, state.selected_pe_strike - spot_price) + state.selected_pe_strike * 0.002), 2)
                        if curr_pe >= state.pe_option_opening_high:
                            pe_breakout_status = f"✅ BREACHED (₹{curr_pe} >= ₹{state.pe_option_opening_high})"
                        else:
                            pe_breakout_status = f"⏳ WAITING (₹{curr_pe} / Target: ₹{state.pe_option_opening_high})"

                    # Check for active trade
                    active_trade = session.exec(select(Trade).where(
                        Trade.instance_id == instance_id,
                        Trade.status == "OPEN"
                    )).first()

                    trade_section = "🟢 <b>Active Positions:</b> None"
                    if active_trade:
                        opt_str = f"{active_trade.strike_price} {active_trade.option_type}"
                        trade_section = (
                            f"📈 <b>Active Position Details:</b>\n"
                            f"• <b>Contract:</b> {opt_str}\n"
                            f"• <b>Entry:</b> ₹{active_trade.entry_price} @ {active_trade.entry_time.strftime('%I:%M %p')}\n"
                            f"• <b>Quantity:</b> {active_trade.quantity}\n"
                            f"• <b>Current LTP:</b> ₹{spot_price}\n"
                            f"• <b>Unrealized P&L:</b> <b>₹{active_trade.pnl:.2f}</b>"
                        )

                    message = (
                        f"📊 <b>Stocker Live Algorithm Status</b>\n\n"
                        f"⚙️ <b>Strategy:</b> {instance.name}\n"
                        f"💼 <b>Asset:</b> <code>{symbol}</code>\n"
                        f"⚡ <b>Engine Phase:</b> <code>{state.phase}</code>\n"
                        f"🚦 <b>Status:</b> {active_status} | <b>{mode_status}</b>\n\n"
                        f"📋 <b>Opening Candle Parameters (1-Min):</b>\n"
                        f"• <b>Spot High:</b> ₹{state.opening_high}\n"
                        f"• <b>Spot Low:</b> ₹{state.opening_low}\n\n"
                        f"🔒 <b>Strike Lock Options Targets:</b>\n"
                        f"• <b>CE strike:</b> {state.selected_ce_strike} CE\n"
                        f"  - <i>Trigger Target:</i> ₹{state.ce_option_opening_high}\n"
                        f"  - <i>Current Breakout Status:</i> {ce_breakout_status}\n"
                        f"• <b>PE strike:</b> {state.selected_pe_strike} PE\n"
                        f"  - <i>Trigger Target:</i> ₹{state.pe_option_opening_high}\n"
                        f"  - <i>Current Breakout Status:</i> {pe_breakout_status}\n\n"
                        f"{trade_section}\n\n"
                        f"⏰ <b>Entry Cutoff:</b> 11:00 AM IST\n"
                        f"🕒 <b>Reported At:</b> {now_ist().strftime('%I:%M:%S %p')}"
                    )

                    await self.telegram_bot.send_message(message)
                    return True, "Strategy status bulletin successfully dispatched."

                else:
                    # Custom standard strategy type fallback
                    message = (
                        f"📊 <b>Stocker Live Algorithm Status</b>\n\n"
                        f"⚙️ <b>Strategy:</b> {instance.name}\n"
                        f"💼 <b>Asset:</b> <code>{symbol}</code>\n"
                        f"🚦 <b>Status:</b> {active_status} | <b>{mode_status}</b>\n"
                        f"🕒 <b>Reported At:</b> {now_ist().strftime('%I:%M:%S %p')}"
                    )
                    await self.telegram_bot.send_message(message)
                    return True, "Custom strategy status bulletin successfully dispatched."

        except Exception as e:
            logger.error(f"Error sending strategy Telegram status for instance {instance_id}: {e}")
            return False, f"Unexpected server error: {e}"

    async def start(self):
        """Start the trading execution engine background threads/loops."""
        self.running = True
        logger.info("Stocker Execution Engine Started.")
        
        # Load and authorize active broker client sessions dynamically on boot
        try:
            with Session(db_engine) as session:
                active_creds = session.exec(select(BrokerCredential).where(
                    BrokerCredential.broker_name != "telegram",
                    BrokerCredential.active == True
                )).all()
                
                for cred in active_creds:
                    broker_key = cred.broker_name.upper()
                    broker_client = self.broker_clients.get(broker_key)
                    if broker_client:
                        logger.info(f"Automatically authenticating stored {broker_key} session on boot...")
                        await broker_client.login({
                            "api_key": cred.api_key,
                            "api_secret": cred.api_secret,
                            "totp_secret": cred.totp_secret,
                            "access_token": cred.access_token
                        })
        except Exception as e:
            logger.error(f"Error restoring active broker session on startup: {e}")

        # Check if daily summary has already been sent today, and load all system state sent flags from DB
        try:
            with Session(db_engine) as session:
                today = now_ist().date()
                today_str = today.strftime("%Y-%m-%d")
                
                # Pre-populate daily summary from DailySummary table
                summary = session.exec(select(DailySummary).where(DailySummary.trade_date == today)).first()
                if summary:
                    self.daily_summary_sent[today_str] = True
                    logger.info(f"Loaded today's DailySummary from database. EOD Telegram notifications already completed.")
                
                # Query all today's SystemState records to populate in-memory send caches
                states = session.exec(select(SystemState).where(SystemState.key.like(f"%_{today_str}"))).all()
                for state in states:
                    if state.value == "true":
                        if state.key.startswith("daily_start_sent_"):
                            self.daily_start_sent[today_str] = True
                            logger.info(f"Loaded daily start status from DB: already sent today.")
                        elif state.key.startswith("pre_market_health_check_sent_"):
                            self.pre_market_health_check_sent[today_str] = True
                            logger.info(f"Loaded pre-market health check status from DB: already sent today.")
                        elif state.key.startswith("daily_summary_sent_"):
                            self.daily_summary_sent[today_str] = True
                            logger.info(f"Loaded daily EOD summary status from DB: already sent today.")
        except Exception as e:
            logger.warning(f"Could not load today's daily system state sent flags on startup: {e}")

        asyncio.create_task(self.engine_loop())

    async def stop(self):
        """Stop the trading execution engine."""
        self.running = False
        logger.info("Stocker Execution Engine Stopped.")

    async def reload_strategies(self):
        """Loads and refreshes active strategy instances from the SQLite database."""
        with Session(db_engine) as session:
            statement = select(StrategyInstance).where(StrategyInstance.active == True)
            db_instances = session.exec(statement).all()
            
            # Update active list
            self.active_strategies = {inst.id: inst for inst in db_instances}
            logger.info(f"Reloaded {len(self.active_strategies)} active strategy instances from database.")

    def select_option_strike(self, spot: float, symbol: str, option_type: str, strike_selection: str) -> float:
        """
        Determines the strike price based on current spot and strike rule.
        - ATM: At The Money (nearest index boundary)
        - ITM: In The Money (deep in the money)
        - OTM: Out of The Money (out of the money)
        """
        step = 50 if "NIFTY50" in symbol or "NIFTY" in symbol else (100 if "BANK" in symbol else 10)
        atm = round(spot / step) * step

        if strike_selection == "ATM":
            return atm
        elif strike_selection == "ITM":
            # Call ITM is below spot, Put ITM is above spot
            return atm - step if option_type.upper() == "CE" else atm + step
        elif strike_selection == "OTM":
            # Call OTM is above spot, Put OTM is below spot
            return atm + step if option_type.upper() == "CE" else atm - step
        return atm

    async def fetch_ohlc_candles(self, symbol: str, strategy: Optional[StrategyInstance] = None) -> pd.DataFrame:
        """
        Fetch candle data for technical indicator calculations.
        If active Zerodha Kite credentials exist, queries real-time 1-minute candles.
        Otherwise, falls back to sandbox simulation (unless strict paper/live strategy).
        """
        if symbol in self.historical_data_cache:
            return self.historical_data_cache[symbol]

        # Try to pull real Zerodha or Dhan candles
        try:
            from app.database import engine as db_engine, BrokerCredential
            from sqlmodel import Session, select
            with Session(db_engine) as session:
                cred_kite = session.exec(select(BrokerCredential).where(
                    BrokerCredential.broker_name == "kite",
                    BrokerCredential.active == True
                )).first()
                cred_dhan = session.exec(select(BrokerCredential).where(
                    BrokerCredential.broker_name == "dhan",
                    BrokerCredential.active == True
                )).first()
                
            if cred_kite and cred_kite.api_key and cred_kite.access_token:
                logger.info(f"Active Zerodha credentials detected. Querying 1-minute candles from Kite for {symbol}...")
                from kiteconnect import KiteConnect
                import asyncio
                
                kite = KiteConnect(api_key=cred_kite.api_key)
                kite.set_access_token(cred_kite.access_token)
                
                # Resolve Standard tokens
                instrument_token = 256265 if "NIFTY 50" in symbol else 260105
                to_date = now_ist()
                from_date = to_date - timedelta(days=3)
                
                loop = asyncio.get_event_loop()
                candles = await loop.run_in_executor(
                    None, 
                    lambda: kite.historical_data(
                        instrument_token=instrument_token,
                        from_date=from_date,
                        to_date=to_date,
                        interval="minute"
                    )
                )
                
                if candles:
                    logger.info(f"Successfully loaded {len(candles)} real candles from Zerodha.")
                    dates = [c["date"] for c in candles]
                    df = pd.DataFrame({
                        "open": [float(c["open"]) for c in candles],
                        "high": [float(c["high"]) for c in candles],
                        "low": [float(c["low"]) for c in candles],
                        "close": [float(c["close"]) for c in candles],
                        "volume": [int(c["volume"]) for c in candles]
                    }, index=pd.DatetimeIndex(dates))
                    
                    df = calculate_indicators(df)
                    self.historical_data_cache[symbol] = df
                    return df

            elif cred_dhan:
                from app.brokers.dhan import get_dhan_token
                dhan_token = get_dhan_token(cred_dhan, session)
                if dhan_token:
                    logger.info(f"Active Dhan credentials detected. Querying 1-minute candles from Dhan for {symbol}...")
                    from app.market_data import DhanMarketDataProvider
                    import asyncio
                    provider = DhanMarketDataProvider(client_id=cred_dhan.api_key, access_token=dhan_token)
                
                to_date = now_ist()
                from_date = to_date - timedelta(days=3)
                
                loop = asyncio.get_event_loop()
                candles = await loop.run_in_executor(
                    None,
                    lambda: provider.get_historical_data(
                        symbol=symbol,
                        days=3,
                        from_date=from_date.strftime("%Y-%m-%d"),
                        to_date=to_date.strftime("%Y-%m-%d"),
                        interval="minute"
                    )
                )
                if candles:
                    logger.info(f"Successfully loaded {len(candles)} real candles from Dhan.")
                    dates = [c["timestamp"] for c in candles]
                    df = pd.DataFrame({
                        "open": [float(c["open"]) for c in candles],
                        "high": [float(c["high"]) for c in candles],
                        "low": [float(c["low"]) for c in candles],
                        "close": [float(c["close"]) for c in candles],
                        "volume": [int(c["volume"]) for c in candles]
                    }, index=pd.DatetimeIndex(dates))
                    
                    df = calculate_indicators(df)
                    self.historical_data_cache[symbol] = df
                    return df
        except Exception as e:
            logger.warning(f"Live broker historical fetch skipped/failed: {e}.")
            if strategy is not None:
                logger.error(f"Cannot generate mock candles for active deployed strategy '{strategy.name}'. Only real broker feed is permitted.")
                return pd.DataFrame()

        # Under strict user request: NEVER use mock fallback data! Return empty DataFrame to halt all trading.
        logger.warning(f"Active broker data feed disconnected or missing credentials for '{symbol}'. Strictly halting trading (empty candle dataset).")
        return pd.DataFrame()

    async def evaluate_strategy_entry(self, strategy: StrategyInstance, last_price: float):
        """Evaluates entry conditions for a strategy if no active positions exist."""
        config = strategy.get_config()
        if not config:
            return

        symbols = config.get("symbols", [])
        if not symbols:
            return

        symbol = symbols[0]  # Standard single target symbol
        
        # Fetch latest OHLC and inject current LTP
        df = await self.fetch_ohlc_candles(symbol, strategy)
        if df.empty:
            return
        
        # Append current quote as a final row
        new_row = df.iloc[-1].copy()
        new_row["close"] = last_price
        
        # Create full series to calculate current indicators
        new_time = df.index[-1] + pd.Timedelta(minutes=1)
        new_row_df = pd.DataFrame([new_row], index=[new_time])
        df_eval = pd.concat([df, new_row_df], ignore_index=False)
        df_eval = calculate_indicators(df_eval)
        
        last_row = df_eval.iloc[-1]
        prev_row = df_eval.iloc[-2]

        rules = config.get("rules", {}).get("entry", {})
        conditions = rules.get("conditions", [])
        operator = rules.get("operator", "AND").upper()

        if not conditions:
            return

        # Check conditions
        results = []
        for cond in conditions:
            res = check_rule_condition(cond, last_row, prev_row)
            results.append(res)

        entry_triggered = all(results) if operator == "AND" else any(results)

        # Performance-safe logging of condition evaluation
        cond_msgs = []
        for c, r in zip(conditions, results):
            cond_msgs.append(f"{c.get('indicator')}({c.get('period')}) {c.get('comparison')} -> {'✓' if r else '✗'}")
        
        self.log_strategy_activity(
            strategy.id,
            strategy.name,
            f"[EVAL] Custom strategy entry check: {', '.join(cond_msgs)} (Triggered: {entry_triggered})"
        )

        if entry_triggered:
            # Entry condition met! Execute Option Buy Order
            action = config.get("action", {})
            opt_type = action.get("option_type", "CE")
            strike_rule = action.get("strike_selection", "ATM")
            qty = action.get("quantity", 50)
            
            strike = self.select_option_strike(last_price, symbol, opt_type, strike_rule)
            option_symbol = f"{symbol}_{now_ist().strftime('%d%b%y').upper()}_{int(strike)}_{opt_type}"

            broker_mode = "PAPER"
            if not strategy.paper_trade:
                with Session(db_engine) as db_session:
                    statement = select(BrokerCredential).where(
                        BrokerCredential.broker_name != "telegram",
                        BrokerCredential.active == True
                    )
                    cred = db_session.exec(statement).first()
                    if cred:
                        broker_mode = cred.broker_name.upper()
                    else:
                        broker_mode = "KITE"

            broker = self.broker_clients.get(broker_mode) or self.broker_clients["PAPER"]
            
            logger.info(f"🚀 Strategy '{strategy.name}' triggered ENTRY! Placing {opt_type} Buy.")
            
            # Use real market execution (price=None) for live fills, and dynamically resolve Dhan/Kite quote for paper trading
            res = await broker.place_order(
                strategy_id=strategy.template_id,
                symbol=option_symbol,
                transaction_type="BUY",
                quantity=qty,
                option_type=opt_type,
                strike_price=strike,
                expiry="WEEKLY",
                price=None,
                instance_id=strategy.id
            )

            if res.get("status") == "SUCCESS":
                trade = res["trade"]
                self.log_strategy_activity(
                    strategy.id,
                    strategy.name,
                    f"[TRIGGER] BUY entry hit! Symbol: {trade.symbol} @ ₹{trade.entry_price} (Qty: {trade.quantity} | Mode: {'PAPER' if strategy.paper_trade else 'LIVE'})"
                )
                if self.telegram_bot:
                    await self.telegram_bot.send_message(
                        f"🟢 <b>BUY TRIGGERED</b>\n\n"
                        f"<b>Strategy:</b> {strategy.name}\n"
                        f"<b>Symbol:</b> {trade.symbol}\n"
                        f"<b>Entry Price:</b> ₹{trade.entry_price}\n"
                        f"<b>Qty:</b> {trade.quantity}\n"
                        f"<b>Mode:</b> {'PAPER' if strategy.paper_trade else 'LIVE'}\n"
                        f"🕐 <b>Buy Time (IST):</b> {trade.entry_time.strftime('%d-%b-%Y %I:%M:%S %p')}"
                    )

    async def force_exit_trade(self, trade_id: int, reason: str = "MANUAL_FORCE_EXIT") -> bool:
        """Manually forces a sell order and closes an active position by ID."""
        with Session(db_engine) as session:
            trade = session.get(Trade, trade_id)
            if not trade or trade.status != "OPEN":
                logger.warning(f"Force exit requested for invalid or closed trade {trade_id}")
                return False
            
            # Find the active strategy template or instance
            if trade.instance_id:
                strategy = session.get(StrategyInstance, trade.instance_id)
            else:
                strategy = session.get(Strategy, trade.strategy_id)
            if not strategy:
                logger.warning(f"Strategy template/instance not found for trade {trade_id}")
                return False
            
            # Resolve broker client
            broker_mode = "PAPER"
            if not strategy.paper_trade:
                statement = select(BrokerCredential).where(
                    BrokerCredential.broker_name != "telegram",
                    BrokerCredential.active == True
                )
                cred = session.exec(statement).first()
                if cred:
                    broker_mode = cred.broker_name.upper()
                else:
                    broker_mode = "KITE"
            
            broker = self.broker_clients.get(broker_mode) or self.broker_clients["PAPER"]
            
            # Get current LTP of option symbol
            try:
                current_ltp = await broker.get_ltp(trade.symbol)
            except Exception as e:
                logger.error(f"Error getting LTP for force exit of trade {trade.id}: {e}")
                current_ltp = trade.entry_price # Fallback to entry price so we don't block square-off!
            
            res = await broker.place_order(
                strategy_id=trade.strategy_id,
                symbol=trade.symbol,
                transaction_type="SELL",
                quantity=trade.quantity,
                price=current_ltp,
                instance_id=trade.instance_id
            )
            
            if res.get("status") == "SUCCESS":
                closed_trade: Trade = res["trade"]
                
                # Commit exit reason
                db_trade = session.get(Trade, closed_trade.id)
                if db_trade:
                    db_trade.exit_reason = reason
                    session.add(db_trade)
                    session.commit()
                
                # Notify on Telegram
                if self.telegram_bot:
                    pnl_color = "🟢" if closed_trade.pnl >= 0 else "🔴"
                    pct_pnl = ((closed_trade.exit_price - closed_trade.entry_price) / closed_trade.entry_price) * 100
                    await self.telegram_bot.send_message(
                        f"🛑 <b>MANUAL FORCE EXIT TRIGGERED</b>\n\n"
                        f"<b>Strategy:</b> {strategy.name}\n"
                        f"<b>Symbol:</b> {closed_trade.symbol}\n"
                        f"<b>Exit Price:</b> ₹{closed_trade.exit_price} (Entry: ₹{closed_trade.entry_price})\n"
                        f"<b>Qty:</b> {closed_trade.quantity}\n"
                        f"<b>PnL:</b> ₹{round(closed_trade.pnl, 2)} ({round(pct_pnl, 2)}%)\n"
                        f"<b>Mode:</b> {'PAPER' if strategy.paper_trade else 'LIVE'}\n"
                        f"🕐 <b>Buy Time (IST):</b> {closed_trade.entry_time.strftime('%d-%b-%Y %I:%M:%S %p')}\n"
                        f"🕐 <b>Sell Time (IST):</b> {closed_trade.exit_time.strftime('%d-%b-%Y %I:%M:%S %p')}"
                    )
                return True
            return False

    async def evaluate_strategy_exit(self, strategy: StrategyInstance, active_trade: Trade, current_ltp: float):
        """Evaluates dynamic SL, Trailing SL, Targets, and exit conditions for an active position."""
        config = strategy.get_config()
        if not config:
            return

        # Simple SL & Target Check
        entry_price = active_trade.entry_price
        pnl = (current_ltp - entry_price) * active_trade.quantity
        pct_pnl = ((current_ltp - entry_price) / entry_price) * 100

        action = config.get("action", {})
        stop_loss_pct = action.get("stop_loss_pct", 5.0)  # 5% SL default
        target_pct = action.get("target_pct", 10.0)      # 10% Target default

        exit_triggered = False
        reason = "INDICATOR"

        # Check hard SL
        if pct_pnl <= -stop_loss_pct:
            exit_triggered = True
            reason = "STOP_LOSS"
            logger.info(f"🔴 Stop Loss Hit for strategy '{strategy.name}' at {pct_pnl}% P&L")

        # Check hard Target
        elif pct_pnl >= target_pct:
            exit_triggered = True
            reason = "TARGET"
            logger.info(f"🟢 Target Hit for strategy '{strategy.name}' at {pct_pnl}% P&L")

        # Check timeframe intraday exit: square-off standard time 15:15
        else:
            now_time = now_ist().time()
            if now_time >= time(15, 15):
                exit_triggered = True
                reason = "TIMELINE"
                logger.info(f"🕒 Intraday Timeline Squareoff hit for strategy '{strategy.name}'")

        # Evaluate custom exit rules
        cond_msgs = []
        if not exit_triggered:
            symbol = config.get("symbols", [active_trade.symbol])[0]
            df = await self.fetch_ohlc_candles(symbol)
            new_row = df.iloc[-1].copy()
            new_row["close"] = current_ltp
            
            new_time = df.index[-1] + pd.Timedelta(minutes=1)
            new_row_df = pd.DataFrame([new_row], index=[new_time])
            df_eval = pd.concat([df, new_row_df], ignore_index=False)
            df_eval = calculate_indicators(df_eval)
            
            last_row = df_eval.iloc[-1]
            prev_row = df_eval.iloc[-2]

            rules = config.get("rules", {}).get("exit", {})
            conditions = rules.get("conditions", [])
            operator = rules.get("operator", "OR").upper()

            if conditions:
                results = []
                for cond in conditions:
                    res = check_rule_condition(cond, last_row, prev_row)
                    results.append(res)

                exit_triggered = all(results) if operator == "AND" else any(results)
                for c, r in zip(conditions, results):
                    cond_msgs.append(f"{c.get('indicator')}({c.get('period')}) {c.get('comparison')} -> {'✓' if r else '✗'}")
                if exit_triggered:
                    reason = "INDICATOR_EXIT"

        custom_exit_str = f" | Exit Rules: {', '.join(cond_msgs)}" if cond_msgs else ""
        self.log_strategy_activity(
            strategy.id,
            strategy.name,
            f"[EVAL] Phase: IN_POSITION ({active_trade.symbol}). LTP: ₹{current_ltp:.2f} | P&L: ₹{pnl:.2f} ({pct_pnl:.2f}% | SL: -{stop_loss_pct}%, Target: +{target_pct}%){custom_exit_str} (Triggered: {exit_triggered})"
        )

        if exit_triggered:
            broker_mode = "PAPER"
            if not strategy.paper_trade:
                with Session(db_engine) as db_session:
                    statement = select(BrokerCredential).where(
                        BrokerCredential.broker_name != "telegram",
                        BrokerCredential.active == True
                    )
                    cred = db_session.exec(statement).first()
                    if cred:
                        broker_mode = cred.broker_name.upper()
                    else:
                        broker_mode = "KITE"

            broker = self.broker_clients.get(broker_mode) or self.broker_clients["PAPER"]
            
            res = await broker.place_order(
                strategy_id=strategy.template_id,
                symbol=active_trade.symbol,
                transaction_type="SELL",
                quantity=active_trade.quantity,
                price=current_ltp,
                instance_id=strategy.id
            )

            if res.get("status") == "SUCCESS":
                trade: Trade = res["trade"]
                trade.exit_reason = reason
                self.log_strategy_activity(
                    strategy.id,
                    strategy.name,
                    f"[TRIGGER] EXIT triggered! Symbol: {trade.symbol} @ ₹{trade.exit_price} (Reason: {reason} | P&L: ₹{trade.pnl:.2f} | Mode: {'PAPER' if strategy.paper_trade else 'LIVE'})"
                )
                
                # Commit reason to database
                with Session(db_engine) as session:
                    db_trade = session.get(Trade, trade.id)
                    if db_trade:
                        db_trade.exit_reason = reason
                        session.add(db_trade)
                        session.commit()

                pnl_color = "🟢" if trade.pnl >= 0 else "🔴"
                # Send immediate Telegram Notification
                if self.telegram_bot:
                    await self.telegram_bot.send_message(
                        f"{pnl_color} <b>SELL TRIGGERED ({reason})</b>\n\n"
                        f"<b>Strategy:</b> {strategy.name}\n"
                        f"<b>Symbol:</b> {trade.symbol}\n"
                        f"<b>Exit Price:</b> ₹{trade.exit_price} (Entry: ₹{trade.entry_price})\n"
                        f"<b>Qty:</b> {trade.quantity}\n"
                        f"<b>PnL:</b> ₹{round(trade.pnl, 2)} ({round(pct_pnl, 2)}%)\n"
                        f"<b>Mode:</b> {'PAPER' if strategy.paper_trade else 'LIVE'}\n"
                        f"🕐 <b>Buy Time (IST):</b> {trade.entry_time.strftime('%d-%b-%Y %I:%M:%S %p')}\n"
                        f"🕐 <b>Sell Time (IST):</b> {trade.exit_time.strftime('%d-%b-%Y %I:%M:%S %p')}"
                    )

    # ── Real-time LTP from Kite ─────────────────────────────────────────

    def _get_kite_client(self):
        """Lazy-init a KiteConnect client from stored credentials."""
        if self._kite_client:
            return self._kite_client
        try:
            with Session(db_engine) as session:
                cred = session.exec(select(BrokerCredential).where(
                    BrokerCredential.broker_name == "kite",
                    BrokerCredential.active == True
                )).first()
            if cred and cred.api_key and cred.access_token:
                from kiteconnect import KiteConnect
                kite = KiteConnect(api_key=cred.api_key)
                kite.set_access_token(cred.access_token)
                self._kite_client = kite
                return kite
        except Exception as e:
            logger.warning(f"Could not init Kite client: {e}")
        return None

    def _sync_active_broker_token(self, active_cred: BrokerCredential, session: Session) -> str:
        """Helper to ensure active broker's token is fresh in DB and synced in-memory."""
        broker_name = active_cred.broker_name.upper()
        if broker_name == "DHAN":
            from app.brokers.dhan import get_dhan_token
            fresh_token = get_dhan_token(active_cred, session)
            dhan_broker = self.broker_clients.get("DHAN")
            if dhan_broker and fresh_token and dhan_broker.access_token != fresh_token:
                logger.info("Dhan token has changed or renewed. Updating in-memory Dhan broker token...")
                dhan_broker.access_token = fresh_token
            return "DHAN"
        return broker_name

    async def fetch_live_spot(self, symbol: str, strategy: Optional[StrategyInstance] = None) -> float:
        """
        Fetch real-time LTP from the active broker (Dhan or Zerodha).
        Strictly halts trading (returns 0.0) if broker is disconnected or quote is not found.
        Includes a 1.5-second cache to prevent Dhan 429 Rate Limit (1 request/sec).
        """
        now_time_check = datetime.now()
        if not hasattr(self, "ltp_cache"):
            self.ltp_cache = {}

        if symbol in self.ltp_cache:
            cached_val, cached_time = self.ltp_cache[symbol]
            if (now_time_check - cached_time).total_seconds() < 1.5:
                return cached_val

        try:
            with Session(db_engine) as session:
                active_cred = session.exec(select(BrokerCredential).where(
                    BrokerCredential.broker_name != "telegram",
                    BrokerCredential.active == True
                )).first()

                if active_cred:
                    broker_name = self._sync_active_broker_token(active_cred, session)
                    if broker_name == "DHAN":
                        dhan_broker = self.broker_clients.get("DHAN")
                        if dhan_broker and dhan_broker.access_token:
                            val = await dhan_broker.get_ltp(symbol)
                            val_float = float(val)
                            self.ltp_cache[symbol] = (val_float, now_time_check)
                            return val_float
                    elif broker_name == "KITE":
                        kite = self._get_kite_client()
                        if kite:
                            loop = asyncio.get_event_loop()
                            ltp_key = symbol if ":" in symbol else f"NSE:{symbol}"
                            ltp_res = await loop.run_in_executor(None, lambda: kite.ltp([ltp_key]))
                            if ltp_res and ltp_key in ltp_res:
                                val_float = float(ltp_res[ltp_key]["last_price"])
                                self.ltp_cache[symbol] = (val_float, now_time_check)
                                return val_float
        except Exception as e:
            logger.error(f"LTP fetch failed for active broker: {e}")
            self._kite_client = None  # reset on error

        # Check if holiday/weekend to avoid generating mock trades
        is_holiday, reason = self.is_market_holiday_today()
        if is_holiday:
            return 0.0

        # Under strict user request: NEVER use mock fallback data! Return 0.0 to halt all trading.
        logger.warning(f"Active broker disconnected or quote not found for '{symbol}'. Strictly halting trading (0.0 spot).")
        return 0.0

    async def get_nearest_option_expiry(self, symbol: str) -> datetime.date:
        """Resolve standard weekly expiry date for Nifty / BankNifty options dynamically."""
        now = now_ist()
        nearest_expiry_date = None
        try:
            kite = self._get_kite_client()
            if kite:
                loop = asyncio.get_event_loop()
                all_nfo = await loop.run_in_executor(None, lambda: kite.instruments("NFO"))
                if all_nfo:
                    opt_name = "NIFTY" if "NIFTY" in symbol and "BANK" not in symbol else "BANKNIFTY"
                    opts = [i for i in all_nfo if i["name"] == opt_name and i["segment"] == "NFO-OPT"]
                    if opts:
                        from datetime import datetime as dt_class
                        expiries = []
                        for o in opts:
                            if o.get("expiry"):
                                if isinstance(o["expiry"], str):
                                    expiries.append(dt_class.strptime(o["expiry"], "%Y-%m-%d").date())
                                else:
                                    expiries.append(o["expiry"])
                        
                        today = now.date()
                        valid_expiries = sorted([e for e in expiries if e >= today])
                        if valid_expiries:
                            nearest_expiry_date = valid_expiries[0]
        except Exception as e:
            logger.debug(f"Kite dynamic expiry lookup failed: {e}")

        if nearest_expiry_date is None:
            # Fallback math (assume next Thursday)
            days_ahead = 3 - now.weekday()
            if days_ahead < 0 or (days_ahead == 0 and now.time() > time(15, 30)):
                days_ahead += 7
            nearest_expiry_date = (now + timedelta(days=days_ahead)).date()
            
        return nearest_expiry_date

    async def get_live_option_premiums(self, underlying_symbol: str, options: List[Tuple[float, str]]) -> Dict[Tuple[float, str], float]:
        """
        Fetches live option premiums for a list of (strike, option_type) from the active broker (Dhan or Zerodha/Kite).
        Includes error handling and returns a dict mapping (strike, option_type) -> float.
        """
        res = {}
        if not options:
            return res

        try:
            with Session(db_engine) as session:
                active_cred = session.exec(select(BrokerCredential).where(
                    BrokerCredential.broker_name != "telegram",
                    BrokerCredential.active == True
                )).first()

                if not active_cred:
                    logger.error("get_live_option_premiums: No active broker credentials found.")
                    return res

                broker_name = self._sync_active_broker_token(active_cred, session)
            nearest_expiry_date = await self.get_nearest_option_expiry(underlying_symbol)

            if broker_name == "DHAN":
                dhan_broker = self.broker_clients.get("DHAN")
                if dhan_broker and dhan_broker.access_token:
                    # Format for Dhan bulk quote search, e.g. NSE:NIFTY 50_04JUN26_23250_CE
                    expiry_raw_str = nearest_expiry_date.strftime("%d%b%y").upper()
                    dhan_symbols = []
                    sym_map = {}
                    for strike, opt_type in options:
                        dhan_sym = f"{underlying_symbol}_{expiry_raw_str}_{int(strike)}_{opt_type}"
                        dhan_symbols.append(dhan_sym)
                        sym_map[dhan_sym] = (strike, opt_type)
                    
                    quotes = await dhan_broker.get_live_quotes(dhan_symbols)
                    for dhan_sym, q in quotes.items():
                        if dhan_sym in sym_map:
                            res[sym_map[dhan_sym]] = float(q["last_price"])
            elif broker_name == "KITE":
                kite = self._get_kite_client()
                if kite:
                    year_str = nearest_expiry_date.strftime("%y")
                    month_val = str(nearest_expiry_date.month)
                    day_str = f"{nearest_expiry_date.day:02d}"
                    
                    month_char = month_val
                    if month_val == "10":
                        month_char = "O"
                    elif month_val == "11":
                        month_char = "N"
                    elif month_val == "12":
                        month_char = "D"
                    
                    underlying_prefix = "NIFTY" if "NIFTY" in underlying_symbol and "BANK" not in underlying_symbol else "BANKNIFTY"
                    
                    kite_symbols = []
                    sym_map = {}
                    for strike, opt_type in options:
                        kite_sym = f"NFO:{underlying_prefix}{year_str}{month_char}{day_str}{int(strike)}{opt_type}"
                        kite_symbols.append(kite_sym)
                        sym_map[kite_sym] = (strike, opt_type)
                    
                    loop = asyncio.get_event_loop()
                    real_quotes = await loop.run_in_executor(None, lambda: kite.ltp(kite_symbols))
                    if real_quotes:
                        for kite_sym, q in real_quotes.items():
                            if kite_sym in sym_map:
                                res[sym_map[kite_sym]] = float(q["last_price"])
        except Exception as e:
            logger.error(f"get_live_option_premiums failed: {e}")

        return res

    async def get_live_option_chain(self, symbol: str, strategy: StrategyInstance) -> Dict[str, Any]:
        """
        Fetches live option chain data for the given index symbol.
        Constructs strikes around the ATM and resolves real-time premiums from Zerodha or sandbox.
        """
        import math
        # 1. Fetch live spot price
        spot = await self.fetch_live_spot(symbol, strategy)
        if spot <= 0.0:
            if strategy is not None:
                return {
                    "underlying": symbol,
                    "spot_price": 0.0,
                    "atm_strike": 0,
                    "expiry_date": "N/A",
                    "broker": "OFFLINE",
                    "chain": []
                }
            spot = 24500.0 if "NIFTY" in symbol and "BANK" not in symbol else 52000.0

        # 2. Determine strike steps
        step = 50 if "NIFTY" in symbol and "BANK" not in symbol else 100
        atm = round(spot / step) * step

        # 3. Generate 7 strikes (ATM, 3 ITM, 3 OTM)
        strikes = [atm + (i * step) for i in range(-3, 4)]
        
        # 4. Resolve standard weekly expiry string for Zerodha Kite Connect
        nearest_expiry_date = await self.get_nearest_option_expiry(symbol)

        year_str = nearest_expiry_date.strftime("%y")
        month_val = str(nearest_expiry_date.month)
        day_str = f"{nearest_expiry_date.day:02d}"
        
        month_char = month_val
        if month_val == "10":
            month_char = "O"
        elif month_val == "11":
            month_char = "N"
        elif month_val == "12":
            month_char = "D"
            
        underlying_prefix = "NIFTY" if "NIFTY" in symbol and "BANK" not in symbol else "BANKNIFTY"
        
        # 5. Build option trading symbols to query
        option_queries = []
        option_symbol_map = {}
        for strike in strikes:
            for opt_type in ["CE", "PE"]:
                tradingsymbol = f"{underlying_prefix}{year_str}{month_char}{day_str}{int(strike)}{opt_type}"
                kite_symbol = f"NFO:{tradingsymbol}"
                option_queries.append(kite_symbol)
                option_symbol_map[kite_symbol] = {
                    "strike": strike,
                    "opt_type": opt_type,
                    "tradingsymbol": tradingsymbol
                }

        # 6. Try to pull real LTP from Zerodha Kite client or Dhan if active and authorized
        active_broker = "KITE"
        try:
            with Session(db_engine) as session:
                active_cred = session.exec(select(BrokerCredential).where(
                    BrokerCredential.broker_name != "telegram",
                    BrokerCredential.active == True
                )).first()
                if active_cred:
                    active_broker = self._sync_active_broker_token(active_cred, session)
        except Exception as db_err:
            logger.debug(f"Failed to query active broker in option chain fetch: {db_err}")

        kite_connected = False
        real_quotes = {}
        
        if active_broker == "DHAN":
            try:
                dhan_broker = self.broker_clients.get("DHAN")
                if dhan_broker and dhan_broker.access_token:
                    # Format for Dhan bulk quote search, e.g. NSE:NIFTY 50_04JUN26_23250_CE
                    expiry_raw_str = nearest_expiry_date.strftime("%d%b%y").upper()
                    dhan_symbols = []
                    dhan_symbol_to_kite = {}
                    for strike in strikes:
                        for opt_type in ["CE", "PE"]:
                            dhan_sym = f"{symbol}_{expiry_raw_str}_{int(strike)}_{opt_type}"
                            dhan_symbols.append(dhan_sym)
                            
                            tradingsymbol = f"{underlying_prefix}{year_str}{month_char}{day_str}{int(strike)}{opt_type}"
                            kite_symbol = f"NFO:{tradingsymbol}"
                            dhan_symbol_to_kite[dhan_sym] = kite_symbol
                    
                    quotes = await dhan_broker.get_live_quotes(dhan_symbols)
                    if quotes:
                        real_quotes = {dhan_symbol_to_kite[k]: v for k, v in quotes.items() if k in dhan_symbol_to_kite}
                        kite_connected = True
            except Exception as e:
                logger.debug(f"Dhan LTP option chain fetch failed: {e}")
        else:
            try:
                kite = self._get_kite_client()
                if kite:
                    loop = asyncio.get_event_loop()
                    real_quotes = await loop.run_in_executor(None, lambda: kite.ltp(option_queries))
                    if real_quotes:
                        kite_connected = True
            except Exception as e:
                logger.debug(f"Kite LTP option chain fetch failed: {e}")

        # If strict strategy and broker is offline, DO NOT return simulated premiums!
        if strategy is not None and not kite_connected:
            return {
                "underlying": symbol,
                "spot_price": spot,
                "atm_strike": atm,
                "expiry_date": nearest_expiry_date.strftime("%d-%b-%Y"),
                "broker": "OFFLINE",
                "chain": []
            }

        # 7. Construct final option chain rows
        chain_rows = {}
        for strike in strikes:
            chain_rows[strike] = {"strike": strike, "CE": None, "PE": None}

        for kite_symbol, meta in option_symbol_map.items():
            strike = meta["strike"]
            opt_type = meta["opt_type"]
            tradingsymbol = meta["tradingsymbol"]
            
            last_price = 0.0
            if kite_connected and kite_symbol in real_quotes:
                last_price = float(real_quotes[kite_symbol]["last_price"])
            else:
                intrinsic = max(0.0, spot - strike) if opt_type == "CE" else max(0.0, strike - spot)
                distance_pct = abs(spot - strike) / spot
                extrinsic_base = 150.0 if "NIFTY" in symbol and "BANK" not in symbol else 400.0
                extrinsic = max(5.0, extrinsic_base * math.exp(-15 * distance_pct))
                last_price = round(intrinsic + extrinsic, 2)
            
            chain_rows[strike][opt_type] = {
                "tradingsymbol": tradingsymbol,
                "last_price": last_price,
                "is_atm": strike == atm
            }

        return {
            "underlying": symbol,
            "spot_price": spot,
            "atm_strike": atm,
            "expiry_date": nearest_expiry_date.strftime("%d-%b-%Y"),
            "broker": active_broker if kite_connected else "SANDBOX",
            "chain": list(chain_rows.values())
        }

    async def record_option_chain_snapshot(self, symbol: str):
        """Records a 1-minute snapshot of the live option chain to a local day folder."""
        now = now_ist()
        now_time = now.time()
        
        # 1. Ensure market is open and not weekend/holiday
        if now_time < time(9, 15) or now_time > time(15, 30):
            return
            
        is_holiday, _ = self.is_market_holiday_today()
        if is_holiday:
            return
            
        # 2. Only record once per minute
        today_str = now.strftime("%Y-%m-%d")
        minute_key = now.strftime("%H:%M")
        
        if not hasattr(self, "_recorded_minutes"):
            self._recorded_minutes = {}
            
        rec_key = f"{symbol}_{today_str}_{minute_key}"
        if self._recorded_minutes.get(rec_key):
            return  # Already recorded this minute!
            
        # 3. Pull option chain via get_live_option_chain
        # Pass strategy=None to allow math/sandbox fallback only if broker is completely unreachable
        chain_data = await self.get_live_option_chain(symbol, strategy=None)
        if not chain_data or chain_data.get("broker") == "OFFLINE" or not chain_data.get("chain"):
            return  # No active data or broker offline
            
        # 4. Construct snapshot structure
        snapshot = {
            "timestamp": now.isoformat(),
            "spot_price": chain_data["spot_price"],
            "atm_strike": chain_data["atm_strike"],
            "expiry_date": chain_data["expiry_date"],
            "chain": []
        }
        
        for row in chain_data["chain"]:
            strike = row["strike"]
            ce = row.get("CE") or {}
            pe = row.get("PE") or {}
            snapshot["chain"].append({
                "strike": strike,
                "CE_price": ce.get("last_price", 0.0),
                "CE_symbol": ce.get("tradingsymbol", ""),
                "PE_price": pe.get("last_price", 0.0),
                "PE_symbol": pe.get("tradingsymbol", "")
            })
            
        # 5. Write to local day folder
        import os
        import json
        
        # Base data directory inside backend
        base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "option_chains", today_str)
        os.makedirs(base_dir, exist_ok=True)
        
        file_name = symbol.replace("NSE:", "").replace(" ", "_") + ".json"
        file_path = os.path.join(base_dir, file_name)
        
        # Load existing snapshots
        snapshots = []
        if os.path.exists(file_path):
            try:
                with open(file_path, "r") as f:
                    snapshots = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read existing option chain file {file_path}: {e}")
                
        # Append and save
        snapshots.append(snapshot)
        try:
            with open(file_path, "w") as f:
                json.dump(snapshots, f, indent=2)
            self._recorded_minutes[rec_key] = True
            logger.info(f"Recorded option chain snapshot for {symbol} at {minute_key} to {file_path}")
        except Exception as e:
            logger.error(f"Failed to save option chain snapshot for {symbol}: {e}")

    # ── ORB Live Evaluation ───────────────────────────────────────────

    async def evaluate_orb_strategy(self, strategy: StrategyInstance, spot: float):
        """Evaluate ORB breakout strategy in real-time for paper/live trading."""
        config = strategy.get_config()
        now = now_ist()
        now_time = now.time()

        # Only run during market hours
        if now_time < time(9, 15) or now_time > time(15, 15):
            return

        # Get or create ORB state for this strategy
        state = self.get_or_create_orb_state(strategy, config, spot)
        if state.phase == "DONE":
            return

        # ── Phase: WAITING_OPENING_CANDLE ──
        if state.phase == "WAITING_OPENING_CANDLE":
            self.log_strategy_activity(
                strategy.id,
                strategy.name,
                "[EVAL] Phase: WAITING_OPENING_CANDLE. Waiting for opening 1-min candle completion (at 09:16 AM)."
            )
            # Wait until 09:16 (first candle complete)
            if now_time >= time(9, 16):
                # Fetch the 9:15 candle from Kite
                symbol = config.get("symbols", ["NSE:NIFTY 50"])[0]
                candle = await self._fetch_915_candle(symbol)
                if not candle:
                    logger.warning(f"ORB [{strategy.name}]: Failed to fetch real 9:15 AM opening candle from Dhan/Zerodha. Halting strategy entry.")
                    return

                state.opening_high = candle["high"]
                state.opening_low = candle["low"]
                state.opening_close = candle["close"]

                # Pre-select CE and PE strikes based on opening close to measure option breakout high
                step = 50 if "NIFTY" in symbol else 100

                # Setup CE strike (Strictly ATM)
                state.selected_ce_strike = round(state.opening_close / step) * step

                # Setup PE strike (Strictly ATM)
                state.selected_pe_strike = round(state.opening_close / step) * step

                # Set opening high on options charts mathematically
                state.ce_option_opening_high = round(max(0.5, max(0, state.opening_high - state.selected_ce_strike) + state.selected_ce_strike * 0.002), 2)
                state.pe_option_opening_high = round(max(0.5, max(0, state.selected_pe_strike - state.opening_low) + state.selected_pe_strike * 0.002), 2)

                state.phase = "WAITING_BREAKOUT"
                logger.info(f"ORB [{strategy.name}] Opening candle: H={candle['high']} L={candle['low']}. Selected CE={state.selected_ce_strike} (H={state.ce_option_opening_high}), PE={state.selected_pe_strike} (H={state.pe_option_opening_high})")

                if self.telegram_bot:
                    alert_key = f"orb_range_alert_sent_{strategy.id}_{now.strftime('%Y%m%d')}"
                    if self._get_system_state(alert_key) != "true":
                        self._set_system_state(alert_key, "true")
                        ts_str = now.strftime("%d-%b-%Y %I:%M:%S %p")
                        await self.telegram_bot.send_message(
                            f"🎯 <b>ORB Opening Range Set (1-Min)</b>\n\n"
                            f"<b>Strategy:</b> {strategy.name}\n"
                            f"<b>Nifty High:</b> ₹{candle['high']}\n"
                            f"<b>Nifty Low:</b> ₹{candle['low']}\n"
                            f"<b>Option CE:</b> {state.selected_ce_strike} CE (First Min High: ₹{state.ce_option_opening_high})\n"
                            f"<b>Option PE:</b> {state.selected_pe_strike} PE (First Min High: ₹{state.pe_option_opening_high})\n"
                            f"⏰ <b>Time:</b> {ts_str}\n"
                            f"<b>Waiting for double breakout...</b>"
                        )

        # ── Phase: WAITING_BREAKOUT ──
        elif state.phase == "WAITING_BREAKOUT":
            # Don't take new entries after 11 am IST
            if now_time > time(11, 0):
                return

            # Query real-time premiums from broker feed
            real_ce_premium = 0.0
            real_pe_premium = 0.0
            
            try:
                symbol = config.get("symbols", ["NSE:NIFTY 50"])[0]
                premiums = await self.get_live_option_premiums(
                    underlying_symbol=symbol,
                    options=[
                        (state.selected_ce_strike, "CE"),
                        (state.selected_pe_strike, "PE")
                    ]
                )
                real_ce_premium = premiums.get((state.selected_ce_strike, "CE"), 0.0)
                real_pe_premium = premiums.get((state.selected_pe_strike, "PE"), 0.0)
            except Exception as e:
                logger.error(f"ORB Live premiums fetch failed: {e}")

            # If broker offline / didn't send data, strictly disable mock fallback for paper/live trading
            if real_ce_premium <= 0.0 or real_pe_premium <= 0.0:
                self.log_strategy_activity(
                    strategy.id,
                    strategy.name,
                    f"[SYSTEM] Live Option Premiums currently unavailable from broker feed. Trading suspended."
                )
                return

            current_ce_premium = real_ce_premium
            current_pe_premium = real_pe_premium

            ce_status = "Broke out" if state.index_high_broke_out else f"Spot ₹{spot:.2f} <= High ₹{state.opening_high:.2f}"
            pe_status = "Broke out" if state.index_low_broke_out else f"Spot ₹{spot:.2f} >= Low ₹{state.opening_low:.2f}"
            self.log_strategy_activity(
                strategy.id,
                strategy.name,
                f"[EVAL] Phase: WAITING_BREAKOUT. CE Premium: ₹{current_ce_premium:.2f} (Target High: ₹{state.ce_option_opening_high:.2f} | Index: {ce_status}). PE Premium: ₹{current_pe_premium:.2f} (Target High: ₹{state.pe_option_opening_high:.2f} | Index: {pe_status})."
            )

            # Check index breakout
            if spot > state.opening_high and "BULLISH" not in state.trades_taken:
                state.index_high_broke_out = True

            if spot < state.opening_low and "BEARISH" not in state.trades_taken:
                state.index_low_broke_out = True

            # Double breakout trigger CE
            trigger_buy = False
            selected_type = None
            selected_strike = None
            est_prem = 0.0

            if state.index_high_broke_out:
                if current_ce_premium > state.ce_option_opening_high:
                    trigger_buy = True
                    selected_type = "CE"
                    selected_strike = state.selected_ce_strike
                    est_prem = state.ce_option_opening_high
                    state.breakout_direction = "BULLISH"

            # Double breakout trigger PE
            if state.index_low_broke_out and not trigger_buy:
                if current_pe_premium > state.pe_option_opening_high:
                    trigger_buy = True
                    selected_type = "PE"
                    selected_strike = state.selected_pe_strike
                    est_prem = state.pe_option_opening_high
                    state.breakout_direction = "BEARISH"

            if trigger_buy:
                state.selected_option_type = selected_type
                state.selected_strike = selected_strike
                state.entry_price = est_prem
                state.entry_time = now.isoformat()

                # Determine target percentage
                # "If first breakout hits SL 10% then wait for low breakout. After low keep target 15%."
                current_target_pct = 15.0 if state.first_trade_hit_sl else 10.0

                state.target_price = round(est_prem * (1 + current_target_pct / 100), 2)
                state.stop_loss_price = round(est_prem * (1 - sl_pct / 100), 2)
                state.breakout_price = spot
                state.breakout_time = now.isoformat()
                state.phase = "IN_POSITION"

                # Record direction
                state.trades_taken.append(state.breakout_direction)

                # Place paper/live order
                broker_mode = "PAPER" if strategy.paper_trade else "KITE"
                broker = self.broker_clients.get(broker_mode) or self.broker_clients["PAPER"]
                opt_symbol = f"NIFTY_{now.strftime('%d%b%y').upper()}_{int(state.selected_strike)}_{state.selected_option_type}"

                res = await broker.place_order(
                    strategy_id=strategy.template_id, symbol=opt_symbol,
                    transaction_type="BUY", quantity=qty,
                    option_type=state.selected_option_type,
                    strike_price=state.selected_strike,
                    expiry="WEEKLY", price=est_prem,
                    instance_id=strategy.id
                )

                if res.get("status") == "SUCCESS":
                    self.log_strategy_activity(
                        strategy.id,
                        strategy.name,
                        f"[TRIGGER] BUY entry hit! Direction: {state.breakout_direction} Option: {state.selected_strike} {state.selected_option_type} @ ₹{est_prem:.2f} (Mode: {'PAPER' if strategy.paper_trade else 'LIVE'})"
                    )
                    logger.info(f"🚀 ORB [{strategy.name}] BUY {state.selected_strike} {state.selected_option_type} @ ₹{est_prem}")
                    if self.telegram_bot:
                        ts_str = now.strftime("%d-%b-%Y %I:%M:%S %p")
                        await self.telegram_bot.send_message(
                            f"🟢 <b>ORB DOUBLE BREAKOUT BUY</b>\n\n"
                            f"<b>Strategy:</b> {strategy.name}\n"
                            f"<b>Direction:</b> {state.breakout_direction}\n"
                            f"<b>Option:</b> {state.selected_strike} {state.selected_option_type}\n"
                            f"<b>Entry Price:</b> ₹{est_prem}\n"
                            f"<b>Target (Target Price):</b> ₹{state.target_price} (+{current_target_pct}%)\n"
                            f"<b>Stop Loss:</b> ₹{state.stop_loss_price} (-{sl_pct}%)\n"
                            f"⏰ <b>Trigger Time (IST):</b> {ts_str}\n"
                            f"<b>Mode:</b> {'PAPER' if strategy.paper_trade else 'LIVE'}\n\n"
                            f"📊 <b>Strategy Details (First Candle):</b>\n"
                            f"• Index Open Range High: <b>{state.opening_high:.2f}</b>\n"
                            f"• Index Open Range Low: <b>{state.opening_low:.2f}</b>\n"
                            f"• CE Option ({state.selected_ce_strike:.0f}) Open High: <b>₹{state.ce_option_opening_high:.2f}</b>\n"
                            f"• PE Option ({state.selected_pe_strike:.0f}) Open High: <b>₹{state.pe_option_opening_high:.2f}</b>"
                        )

        # ── Phase: IN_POSITION ──
        elif state.phase == "IN_POSITION":
            # Query real-time premium of the active position from broker feed
            real_premium = 0.0
            try:
                symbol = config.get("symbols", ["NSE:NIFTY 50"])[0]
                premiums = await self.get_live_option_premiums(
                    underlying_symbol=symbol,
                    options=[(state.selected_strike, state.selected_option_type)]
                )
                real_premium = premiums.get((state.selected_strike, state.selected_option_type), 0.0)
            except Exception as e:
                logger.error(f"ORB Live position premium fetch failed: {e}")

            # If broker offline / didn't send data, strictly disable mock fallback for paper/live trading
            if real_premium <= 0.0:
                self.log_strategy_activity(
                    strategy.id,
                    strategy.name,
                    f"[SYSTEM] Live Position Premium currently unavailable from broker feed. Trading suspended."
                )
                return

            current_prem = real_premium

            self.log_strategy_activity(
                strategy.id,
                strategy.name,
                f"[EVAL] Phase: IN_POSITION ({state.selected_strike} {state.selected_option_type}). Premium: ₹{current_prem:.2f} | Target: ₹{state.target_price:.2f} | Stop Loss: ₹{state.stop_loss_price:.2f}"
            )

            exit_reason = None
            exit_price = None

            if current_prem >= state.target_price:
                exit_reason = "TARGET"
                exit_price = state.target_price
            elif current_prem <= state.stop_loss_price:
                exit_reason = "STOP_LOSS"
                exit_price = state.stop_loss_price
            elif now_time >= time(15, 15):
                exit_reason = "TIMELINE"
                exit_price = round(current_prem, 2)

            if exit_reason:
                state.exit_price = exit_price
                state.exit_time = now.isoformat()
                state.exit_reason = exit_reason
                trade_pnl = (exit_price - state.entry_price) * qty
                state.pnl += trade_pnl

                # Re-entry and final state calibration:
                # "Maximum 2 entries only. First candle high breakout and low breakout"
                if exit_reason == "STOP_LOSS" and len(state.trades_taken) < 2:
                    state.first_trade_hit_sl = True
                    state.phase = "WAITING_BREAKOUT"
                    # Reset triggers for opposite direction
                    state.index_high_broke_out = False
                    state.index_low_broke_out = False
                    logger.info(f"ORB [{strategy.name}] Stopped out at SL. Re-entering WAITING_BREAKOUT phase for opposite breakout.")
                else:
                    state.phase = "DONE"

                # Place sell order
                broker_mode = "PAPER" if strategy.paper_trade else "KITE"
                broker = self.broker_clients.get(broker_mode) or self.broker_clients["PAPER"]

                with Session(db_engine) as session:
                    active_trade = session.exec(select(Trade).where(
                        Trade.instance_id == strategy.id, Trade.status == "OPEN"
                    )).first()
                    if active_trade:
                        await broker.place_order(
                            strategy_id=strategy.template_id, symbol=active_trade.symbol,
                            transaction_type="SELL", quantity=qty, price=exit_price,
                            instance_id=strategy.id
                        )

                pnl_icon = "🟢" if trade_pnl >= 0 else "🔴"
                self.log_strategy_activity(
                    strategy.id,
                    strategy.name,
                    f"[TRIGGER] EXIT triggered! Reason: {exit_reason} | Executed at: ₹{exit_price:.2f} | Trade P&L: ₹{trade_pnl:.2f}"
                )
                logger.info(f"{pnl_icon} ORB [{strategy.name}] {exit_reason} @ ₹{exit_price} Trade P&L: ₹{trade_pnl:.2f}")
                if self.telegram_bot:
                    ts_str = now.strftime("%d-%b-%Y %I:%M:%S %p")
                    await self.telegram_bot.send_message(
                        f"{pnl_icon} <b>ORB {exit_reason} TRIGGERED</b>\n\n"
                        f"<b>Strategy:</b> {strategy.name}\n"
                        f"<b>Exit Price:</b> ₹{exit_price} (Entry: ₹{state.entry_price})\n"
                        f"<b>Trade P&L:</b> ₹{round(trade_pnl, 2)}\n"
                        f"<b>Total P&L Today:</b> ₹{round(state.pnl, 2)}\n"
                        f"🕐 <b>Trigger/Buy Time (IST):</b> {state.entry_time}\n"
                        f"🕐 <b>Exit/Sell Time (IST):</b> {ts_str}\n"
                        f"<b>Next Phase Status:</b> {state.phase}\n"
                        f"<b>Mode:</b> {'PAPER' if strategy.paper_trade else 'LIVE'}\n\n"
                        f"📊 <b>Strategy Details (First Candle):</b>\n"
                        f"• Index Open Range High: <b>{state.opening_high:.2f}</b>\n"
                        f"• Index Open Range Low: <b>{state.opening_low:.2f}</b>\n"
                        f"• CE Option ({state.selected_ce_strike:.0f}) Open High: <b>₹{state.ce_option_opening_high:.2f}</b>\n"
                        f"• PE Option ({state.selected_pe_strike:.0f}) Open High: <b>₹{state.pe_option_opening_high:.2f}</b>"
                    )

    async def _fetch_915_candle(self, symbol: str) -> Optional[Dict]:
        """Fetch the 9:15 opening candle from the active broker (Dhan or Zerodha) historical API."""
        try:
            with Session(db_engine) as session:
                active_cred = session.exec(select(BrokerCredential).where(
                    BrokerCredential.broker_name != "telegram",
                    BrokerCredential.active == True
                )).first()

            if active_cred:
                broker_name = active_cred.broker_name.upper()
                if broker_name == "DHAN":
                    from app.brokers.dhan import get_dhan_token
                    with Session(db_engine) as session:
                        dhan_token = get_dhan_token(active_cred, session)
                    if dhan_token:
                        from app.market_data import DhanMarketDataProvider
                        provider = DhanMarketDataProvider(client_id=active_cred.api_key, access_token=dhan_token)
                        today = now_ist().strftime("%Y-%m-%d")
                        loop = asyncio.get_event_loop()
                        candles = await loop.run_in_executor(None, lambda: provider.get_historical_data(
                            symbol=symbol,
                            days=1,
                            from_date=today,
                            to_date=today,
                            interval="minute"
                        ))
                        if candles and len(candles) > 0:
                            c = candles[0]
                            return {"open": float(c["open"]), "high": float(c["high"]),
                                    "low": float(c["low"]), "close": float(c["close"])}
                elif broker_name == "KITE":
                    kite = self._get_kite_client()
                    if kite:
                        today = now_ist().strftime("%Y-%m-%d")
                        token = 256265 if "NIFTY 50" in symbol else 260105
                        loop = asyncio.get_event_loop()
                        candles = await loop.run_in_executor(None, lambda: kite.historical_data(
                            instrument_token=token,
                            from_date=f"{today} 09:15:00",
                            to_date=f"{today} 09:16:00",
                            interval="minute"
                        ))
                        if candles and len(candles) > 0:
                            c = candles[0]
                            return {"open": float(c["open"]), "high": float(c["high"]),
                                    "low": float(c["low"]), "close": float(c["close"])}
        except Exception as e:
            logger.warning(f"Failed to fetch 9:15 candle from active broker: {e}")
        return None

    # ── Main Engine Loop ──────────────────────────────────────────────

    async def engine_loop(self):
        """Continuous polling / streaming evaluation engine loop."""
        logger.info("Starting stock tick polling iteration thread...")
        await self.reload_strategies()

        while self.running:
            try:
                # ── Start/End of Day Telegram Notifications ──
                now = now_ist()
                today_date = now.strftime("%Y-%m-%d")
                now_time = now.time()

                if self.telegram_bot:
                    # 1. Pre-Market Broker Health Check (20 mins before start, at 08:55 AM)
                    if time(8, 55) <= now_time <= time(9, 10):
                        if today_date not in self.pre_market_health_check_sent and self._get_system_state(f"pre_market_health_check_sent_{today_date}") != "true":
                            self.pre_market_health_check_sent[today_date] = True
                            self._set_system_state(f"pre_market_health_check_sent_{today_date}", "true")
                            is_healthy, detail = await self.check_broker_health()
                            if not is_healthy:
                                logger.warning(f"Pre-market health check failed: {detail}")
                                await self.telegram_bot.send_message(
                                    f"⚠️ <b>URGENT: Pre-Market Broker Disconnect!</b>\n\n"
                                    f"Stocker's pre-market health check detected a broker connectivity issue:\n"
                                    f"• <b>Reason:</b> {detail}\n\n"
                                    f"⏰ <b>Market opens in 20 minutes!</b> Please log in and re-authenticate your session via the dashboard settings to ensure automated strategies run successfully today."
                                )
                            else:
                                logger.info("Pre-market broker health check passed successfully.")

                    # 2. Start of Day notification (between 9:15 AM and 3:30 PM)
                    if time(9, 15) <= now_time <= time(15, 30):
                        if today_date not in self.daily_start_sent and self._get_system_state(f"daily_start_sent_{today_date}") != "true":
                            self.daily_start_sent[today_date] = True
                            self._set_system_state(f"daily_start_sent_{today_date}", "true")
                            is_holiday, reason = self.is_market_holiday_today()
                            if is_holiday:
                                await self.telegram_bot.send_message(
                                    f"🏛️ <b>NSE / BSE Market Closed Today</b>\n\n"
                                    f"Stocker engine detected that the Indian stock market is **CLOSED** today:\n"
                                    f"• <b>Reason / Holiday:</b> {reason}\n"
                                    f"• <b>Date:</b> {now.strftime('%d-%b-%Y')}\n\n"
                                    f"💤 <b>All active strategies are paused for today.</b> Regular trading and automated triggers will resume on the next business day."
                                )
                            else:
                                await self.telegram_bot.send_message(
                                    f"🚀 <b>Stocker Engine is Working!</b>\n\n"
                                    f"Stocker automated trading core has booted successfully for today (<b>{now.strftime('%d-%b-%Y')}</b>) "
                                    f"and is actively monitoring options breakouts and strategy rules in the background.\n\n"
                                    f"🟢 <b>Status:</b> Live & Connected"
                                )

                    # 3. End of Day daily summary (at or after 3:30 PM)
                    if now_time >= time(15, 30):
                        if today_date not in self.daily_summary_sent and self._get_system_state(f"daily_summary_sent_{today_date}") != "true":
                            self.daily_summary_sent[today_date] = True
                            self._set_system_state(f"daily_summary_sent_{today_date}", "true")
                            logger.info(f"Triggering automated DailySummary report generation for {today_date}...")
                            await self.telegram_bot.generate_and_send_daily_summary(orb_states=self.orb_states)

                is_holiday, holiday_reason = self.is_market_holiday_today()

                for strat_id, strategy in list(self.active_strategies.items()):
                    if is_holiday:
                        already_logged = any(
                            log["strategy_id"] == strategy.id and "closed today" in log["message"]
                            for log in self.strategy_logs
                        )
                        if not already_logged:
                            self.log_strategy_activity(
                                strategy.id,
                                strategy.name,
                                f"[SYSTEM] Indian market closed today ({holiday_reason}). Live evaluation suspended."
                            )
                        continue

                    config = strategy.get_config()
                    if not config:
                        continue

                    symbol = config.get("symbols", ["NSE:NIFTY 50"])[0]
                    strategy_type = config.get("strategy_type", "custom")

                    # Trigger real-time option chain background recording during market hours
                    asyncio.create_task(self.record_option_chain_snapshot(symbol))

                    # Fetch real LTP (falls back to mock if Kite unavailable and not live paper trade)
                    current_spot_price = await self.fetch_live_spot(symbol, strategy)
                    if current_spot_price <= 0.0:
                        already_logged = any(
                            log["strategy_id"] == strategy.id and "not available" in log["message"]
                            for log in self.strategy_logs
                        )
                        if not already_logged:
                            self.log_strategy_activity(
                                strategy.id,
                                strategy.name,
                                f"[SYSTEM] Live market data feed not available. Mocking disabled for strict live paper trade."
                            )
                        continue

                    # ── ORB Breakout Strategy ──
                    if strategy_type == "orb_breakout":
                        await self.evaluate_orb_strategy(strategy, current_spot_price)
                        continue

                    # ── Custom Indicator Strategy ──
                    with Session(db_engine) as session:
                        active_trade = session.exec(select(Trade).where(
                            Trade.instance_id == strategy.id,
                            Trade.status == "OPEN"
                        )).first()

                        if not active_trade:
                            await self.evaluate_strategy_entry(strategy, current_spot_price)
                        else:
                            # Estimate option premium from spot
                            current_opt_ltp = active_trade.entry_price * (1 + ((current_spot_price - 24500.0) / 24500.0) * 10)
                            if current_opt_ltp < 1:
                                current_opt_ltp = 1.0
                            await self.evaluate_strategy_exit(strategy, active_trade, current_opt_ltp)

            except Exception as e:
                logger.error(f"Error in execution engine loop cycle: {e}")

            await asyncio.sleep(5)
