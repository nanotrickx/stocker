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
            "ALICEBLUE": get_broker("ALICEBLUE")
        }
        self.telegram_bot = None  # Injected later
        self.running = False
        self.historical_data_cache: Dict[str, pd.DataFrame] = {}
        self.orb_states: Dict[str, ORBState] = {}  # per-strategy ORB state
        self._kite_client = None  # cached KiteConnect instance
        self.daily_start_sent: Dict[str, bool] = {}
        self.daily_summary_sent: Dict[str, bool] = {}
        self.pre_market_health_check_sent: Dict[str, bool] = {}

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
                    state = self.orb_states.get(instance_id)
                    if not state:
                        # Fallback if no ticks have updated it yet today
                        return False, "Strategy is not currently initialized in memory. Please start it first."

                    # Calculate dynamic metrics for real-time reporting
                    spot_price = await self.fetch_live_spot(symbol)
                    
                    ce_breakout_status = "🔴 Waiting"
                    pe_breakout_status = "🔴 Waiting"
                    
                    if state.selected_ce_strike:
                        curr_ce = round(max(0.5, max(0, spot_price - state.selected_ce_strike) + state.selected_ce_strike * 0.005), 2)
                        if curr_ce >= state.ce_option_opening_high:
                            ce_breakout_status = f"✅ BREACHED (₹{curr_ce} >= ₹{state.ce_option_opening_high})"
                        else:
                            ce_breakout_status = f"⏳ WAITING (₹{curr_ce} / Target: ₹{state.ce_option_opening_high})"
                            
                    if state.selected_pe_strike:
                        curr_pe = round(max(0.5, max(0, state.selected_pe_strike - spot_price) + state.selected_pe_strike * 0.005), 2)
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

        # Check if daily summary has already been sent today
        try:
            with Session(db_engine) as session:
                today = now_ist().date()
                summary = session.exec(select(DailySummary).where(DailySummary.trade_date == today)).first()
                if summary:
                    self.daily_summary_sent[today.strftime("%Y-%m-%d")] = True
                    logger.info(f"Loaded today's DailySummary from database. EOD Telegram notifications already completed.")
        except Exception as e:
            logger.warning(f"Could not load today's daily summary state on startup: {e}")

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

    async def fetch_ohlc_candles(self, symbol: str) -> pd.DataFrame:
        """
        Fetch candle data for technical indicator calculations.
        If active Zerodha Kite credentials exist, queries real-time 1-minute candles.
        Otherwise, falls back to sandbox simulation.
        """
        if symbol in self.historical_data_cache:
            return self.historical_data_cache[symbol]

        # Try to pull real Zerodha candles
        try:
            from app.database import engine as db_engine, BrokerCredential
            from sqlmodel import Session, select
            with Session(db_engine) as session:
                cred = session.exec(select(BrokerCredential).where(
                    BrokerCredential.broker_name == "kite",
                    BrokerCredential.active == True
                )).first()
                
            if cred and cred.api_key and cred.access_token:
                logger.info(f"Active Zerodha credentials detected. Querying 1-minute candles from Kite for {symbol}...")
                from kiteconnect import KiteConnect
                import asyncio
                
                kite = KiteConnect(api_key=cred.api_key)
                kite.set_access_token(cred.access_token)
                
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
        except Exception as e:
            logger.warning(f"Zerodha historical fetch skipped: {e}. Defaulting to Sandbox candle simulator.")

        # Sandbox Mock candles generator fallback
        logger.info(f"Generating mock historical OHLC dataset for symbol: {symbol}")
        now = now_ist()
        dates = pd.date_range(end=now, periods=100, freq='min')
        
        base_price = 22000.0 if "NIFTY" in symbol else (47000.0 if "BANK" in symbol else 150.0)
        
        closes = [base_price + (i * 0.5) for i in range(100)]
        opens = [c - 0.2 for c in closes]
        highs = [c + 1.0 for c in closes]
        lows = [o - 0.8 for o in opens]
        volumes = [1000 + (i * 10) for i in range(100)]

        df = pd.DataFrame({
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes
        }, index=dates)

        df = calculate_indicators(df)
        self.historical_data_cache[symbol] = df
        return df

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
        df = await self.fetch_ohlc_candles(symbol)
        
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
            
            # Fetch option mock LTP or standard index LTP
            option_ltp = 150.0  # Simulated default premium
            
            res = await broker.place_order(
                strategy_id=strategy.template_id,
                symbol=option_symbol,
                transaction_type="BUY",
                quantity=qty,
                option_type=opt_type,
                strike_price=strike,
                expiry="WEEKLY",
                price=option_ltp,
                instance_id=strategy.id
            )

            if res.get("status") == "SUCCESS" and self.telegram_bot:
                trade = res["trade"]
                # Send immediate Telegram Notification
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
                if exit_triggered:
                    reason = "INDICATOR_EXIT"

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

            if res.get("status") == "SUCCESS" and self.telegram_bot:
                trade: Trade = res["trade"]
                trade.exit_reason = reason
                
                # Commit reason to database
                with Session(db_engine) as session:
                    db_trade = session.get(Trade, trade.id)
                    if db_trade:
                        db_trade.exit_reason = reason
                        session.add(db_trade)
                        session.commit()

                pnl_color = "🟢" if trade.pnl >= 0 else "🔴"
                # Send immediate Telegram Notification
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

    async def fetch_live_spot(self, symbol: str) -> float:
        """Fetch real-time LTP from Zerodha. Falls back to mock if unavailable."""
        try:
            kite = self._get_kite_client()
            if kite:
                loop = asyncio.get_event_loop()
                ltp_key = symbol if ":" in symbol else f"NSE:{symbol}"
                ltp_res = await loop.run_in_executor(None, lambda: kite.ltp([ltp_key]))
                if ltp_res and ltp_key in ltp_res:
                    return float(ltp_res[ltp_key]["last_price"])
        except Exception as e:
            logger.debug(f"LTP fetch failed for {symbol}: {e}")
            self._kite_client = None  # reset so next tick retries auth
        # Fallback mock
        if "NIFTY" in symbol and "BANK" not in symbol:
            return 24500.0 + (now_ist().second % 10 - 5) * 5
        elif "BANK" in symbol:
            return 52000.0 + (now_ist().second % 10 - 5) * 10
        return 100.0

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
        sid = strategy.id
        today_key = f"{sid}_{now.strftime('%Y%m%d')}"

        # Reset state for new day
        if "_day_keys" not in self.orb_states:
            self.orb_states["_day_keys"] = {}
        day_keys = self.orb_states["_day_keys"]

        if sid in self.orb_states and day_keys.get(sid) != today_key:
            del self.orb_states[sid]

        risk = config.get("risk", {})
        sl_pct = risk.get("stop_loss_pct", 10.0)
        opt_sel = config.get("option_selection", {})
        premium_min = opt_sel.get("premium_min", 100)
        premium_max = opt_sel.get("premium_max", 200)
        qty = config.get("action", {}).get("quantity", 50)

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

        state = self.orb_states[sid]
        if state.phase == "DONE":
            return

        # ── Phase: WAITING_OPENING_CANDLE ──
        if state.phase == "WAITING_OPENING_CANDLE":
            # Wait until 09:16 (first candle complete)
            if now_time >= time(9, 16):
                # Fetch the 9:15 candle from Kite
                symbol = config.get("symbols", ["NSE:NIFTY 50"])[0]
                candle = await self._fetch_915_candle(symbol)
                if not candle:
                    # Mock fallback for sandbox / offline mode
                    if "BANK" in symbol:
                        candle = {"open": 52000.0, "high": 52100.0, "low": 51950.0, "close": 52050.0}
                    else:
                        candle = {"open": 24500.0, "high": 24550.0, "low": 24480.0, "close": 24520.0}

                state.opening_high = candle["high"]
                state.opening_low = candle["low"]
                state.opening_close = candle["close"]

                # Pre-select CE and PE strikes based on opening close to measure option breakout high
                step = 50 if "NIFTY" in symbol else 100

                # Setup CE strike
                ce_atm = round(state.opening_close / step) * step
                ce_est = round(max(0, state.opening_close - ce_atm) + ce_atm * 0.005, 2)
                if ce_est > premium_max:
                    for shift in range(1, 15):
                        otm = ce_atm + (shift * step)
                        prem = max(0, state.opening_close - otm) + otm * 0.005
                        if premium_min <= prem <= premium_max:
                            ce_atm = otm
                            ce_est = round(prem, 2)
                            break
                state.selected_ce_strike = ce_atm

                # Setup PE strike
                pe_atm = round(state.opening_close / step) * step
                pe_est = round(max(0, pe_atm - state.opening_close) + pe_atm * 0.005, 2)
                if pe_est > premium_max:
                    for shift in range(1, 15):
                        otm = pe_atm - (shift * step)
                        prem = max(0, otm - state.opening_close) + otm * 0.005
                        if premium_min <= prem <= premium_max:
                            pe_atm = otm
                            pe_est = round(prem, 2)
                            break
                state.selected_pe_strike = pe_atm

                # Set opening high on options charts mathematically
                state.ce_option_opening_high = round(max(0.5, max(0, state.opening_high - state.selected_ce_strike) + state.selected_ce_strike * 0.005), 2)
                state.pe_option_opening_high = round(max(0.5, max(0, state.selected_pe_strike - state.opening_low) + state.selected_pe_strike * 0.005), 2)

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

            # Estimate current premiums
            current_ce_premium = round(max(0.5, max(0, spot - state.selected_ce_strike) + state.selected_ce_strike * 0.005), 2)
            current_pe_premium = round(max(0.5, max(0, state.selected_pe_strike - spot) + state.selected_pe_strike * 0.005), 2)

            # Rule: "If the option chart first candle high breakout before nifty does, then no entry."
            if spot <= state.opening_high and current_ce_premium > state.ce_option_opening_high:
                if not state.ce_option_already_broke_out:
                    state.ce_option_already_broke_out = True
                    logger.info(f"ORB [{strategy.name}] CE option broke out before index did. CE entry invalidated.")

            if spot >= state.opening_low and current_pe_premium > state.pe_option_opening_high:
                if not state.pe_option_already_broke_out:
                    state.pe_option_already_broke_out = True
                    logger.info(f"ORB [{strategy.name}] PE option broke out before index did. PE entry invalidated.")

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

            if state.index_high_broke_out and not state.ce_option_already_broke_out:
                if current_ce_premium > state.ce_option_opening_high:
                    trigger_buy = True
                    selected_type = "CE"
                    selected_strike = state.selected_ce_strike
                    est_prem = current_ce_premium
                    state.breakout_direction = "BULLISH"

            # Double breakout trigger PE
            if state.index_low_broke_out and not state.pe_option_already_broke_out and not trigger_buy:
                if current_pe_premium > state.pe_option_opening_high:
                    trigger_buy = True
                    selected_type = "PE"
                    selected_strike = state.selected_pe_strike
                    est_prem = current_pe_premium
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
                            f"⏰ <b>Time (IST):</b> {ts_str}\n"
                            f"<b>Mode:</b> {'PAPER' if strategy.paper_trade else 'LIVE'}"
                        )

        # ── Phase: IN_POSITION ──
        elif state.phase == "IN_POSITION":
            # Estimate current premium from spot movement
            spot_move = spot - state.breakout_price
            delta = 0.5 if state.selected_option_type == "CE" else -0.5
            current_prem = max(0.5, state.entry_price + spot_move * delta)

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
                logger.info(f"{pnl_icon} ORB [{strategy.name}] {exit_reason} @ ₹{exit_price} Trade P&L: ₹{trade_pnl:.2f}")
                if self.telegram_bot:
                    ts_str = now.strftime("%d-%b-%Y %I:%M:%S %p")
                    await self.telegram_bot.send_message(
                        f"{pnl_icon} <b>ORB {exit_reason} TRIGGERED</b>\n\n"
                        f"<b>Strategy:</b> {strategy.name}\n"
                        f"<b>Exit Price:</b> ₹{exit_price} (Entry: ₹{state.entry_price})\n"
                        f"<b>Trade P&L:</b> ₹{round(trade_pnl, 2)}\n"
                        f"<b>Total P&L Today:</b> ₹{round(state.pnl, 2)}\n"
                        f"🕐 <b>Buy Time (IST):</b> {state.entry_time}\n"
                        f"🕐 <b>Sell Time (IST):</b> {ts_str}\n"
                        f"<b>Next Phase Status:</b> {state.phase}\n"
                        f"<b>Mode:</b> {'PAPER' if strategy.paper_trade else 'LIVE'}"
                    )

    async def _fetch_915_candle(self, symbol: str) -> Optional[Dict]:
        """Fetch the 9:15 opening candle from Kite historical API."""
        try:
            kite = self._get_kite_client()
            if not kite:
                return None
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
            logger.warning(f"Failed to fetch 9:15 candle: {e}")
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
                            await self.telegram_bot.generate_and_send_daily_summary()

                for strat_id, strategy in list(self.active_strategies.items()):
                    config = strategy.get_config()
                    if not config:
                        continue

                    symbol = config.get("symbols", ["NSE:NIFTY 50"])[0]
                    strategy_type = config.get("strategy_type", "custom")

                    # Fetch real LTP (falls back to mock if Kite unavailable)
                    current_spot_price = await self.fetch_live_spot(symbol)

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
