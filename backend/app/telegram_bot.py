import os
import logging
from datetime import datetime, date
from typing import Optional
import httpx
from sqlmodel import Session, select
from app.database import engine as db_engine, Trade, DailySummary

logger = logging.getLogger("Stocker.TelegramBot")

class TelegramBot:
    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
        # Allow loading from environment variables if not passed directly
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.client = httpx.AsyncClient()
        
        if not self.token or not self.chat_id:
            logger.warning("Telegram token or Chat ID is missing. Notifications will print to console logs.")

    async def update_credentials(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        logger.info("Telegram Bot credentials updated successfully.")

    async def send_message(self, text: str) -> bool:
        """Sends an HTML formatted alert message to the configured Telegram Chat ID."""
        if not self.token or not self.chat_id:
            logger.info(f"[TELEGRAM LOG OUT]:\n{text}\n(Setup Telegram credentials in settings to receive live notifications.)")
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML"
        }

        try:
            response = await self.client.post(url, json=payload, timeout=10.0)
            if response.status_code == 200:
                logger.info("Telegram notification sent successfully.")
                return True
            else:
                logger.error(f"Failed to send Telegram message. Response: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error while dispatching telegram message: {e}")
            return False

    async def generate_and_send_daily_summary(self, orb_states: Optional[dict] = None) -> Optional[DailySummary]:
        """
        Gathers all trades closed today, computes metrics (Win Rate %, total P&L),
        records a DailySummary to database, and posts a premium styled bulletin to Telegram.
        Supports sending empty summary reports so users know system ran successfully.
        """
        today = date.today()
        start_of_day = datetime.combine(today, datetime.min.time())
        end_of_day = datetime.combine(today, datetime.max.time())

        with Session(db_engine) as session:
            # Query all trades closed today
            statement = select(Trade).where(
                Trade.status == "CLOSED",
                Trade.exit_time >= start_of_day,
                Trade.exit_time <= end_of_day
            )
            closed_trades = session.exec(statement).all()

            total = len(closed_trades)
            profitable = sum(1 for t in closed_trades if (t.pnl or 0) > 0)
            losing = total - profitable
            win_rate = (profitable / total) * 100 if total > 0 else 0.0
            net_pnl = sum((t.pnl or 0.0) for t in closed_trades)

            # Store summary to Database (update if exists, otherwise create)
            summary_stmt = select(DailySummary).where(DailySummary.trade_date == today)
            summary = session.exec(summary_stmt).first()

            if not summary:
                summary = DailySummary(trade_date=today)
            
            summary.total_trades = total
            summary.profitable_trades = profitable
            summary.losing_trades = losing
            summary.win_rate = round(win_rate, 2)
            summary.net_pnl = round(net_pnl, 2)
            summary.updated_at = datetime.utcnow()

            session.add(summary)
            session.commit()
            session.refresh(summary)

            # Construct stunning Telegram Summary Message
            pnl_emoji = "🟩" if net_pnl >= 0 else "🟥"
            
            if total > 0:
                msg = (
                    f"📊 <b>DAILY TRADING SUMMARY ({today.strftime('%d %B %Y')})</b>\n"
                    f"===============================\n\n"
                    f"💼 <b>Total Trades Executed:</b> {total}\n"
                    f"🎯 <b>Profitable Trades:</b> {profitable} ✅\n"
                    f"❌ <b>Losing Trades:</b> {losing} 🔻\n"
                    f"📈 <b>Win Rate:</b> {round(win_rate, 1)}%\n\n"
                    f"💸 <b>Total Realized P&L:</b> {pnl_emoji} <b>₹{round(net_pnl, 2)}</b>\n"
                    f"===============================\n\n"
                    f"<b>Trade-by-Trade Performance:</b>\n"
                )

                for index, t in enumerate(closed_trades, 1):
                    indicator = "🟢" if (t.pnl or 0) >= 0 else "🔴"
                    entry_t_str = t.entry_time.strftime("%I:%M:%S %p") if t.entry_time else "N/A"
                    exit_t_str = t.exit_time.strftime("%I:%M:%S %p") if t.exit_time else "N/A"
                    
                    details_str = ""
                    if orb_states and t.instance_id and t.instance_id in orb_states:
                        state = orb_states[t.instance_id]
                        if state.opening_high is not None and state.opening_low is not None:
                            details_str = (
                                f"   • Index Opening Range: H {state.opening_high:.2f} | L {state.opening_low:.2f}\n"
                                f"   • CE Option ({state.selected_ce_strike:.0f}) Open High: ₹{state.ce_option_opening_high:.2f}\n"
                                f"   • PE Option ({state.selected_pe_strike:.0f}) Open High: ₹{state.pe_option_opening_high:.2f}\n"
                            )

                    msg += (
                        f"{index}. {indicator} <b>{t.symbol}</b> ({t.mode})\n"
                        f"   • Entry: ₹{t.entry_price} ({entry_t_str}) | Exit: ₹{t.exit_price} ({exit_t_str})\n"
                        f"   • P&L: ₹{round(t.pnl or 0.0, 2)} ({t.exit_reason})\n"
                        f"{details_str}"
                    )
            else:
                msg = (
                    f"📊 <b>DAILY TRADING SUMMARY ({today.strftime('%d %B %Y')})</b>\n"
                    f"===============================\n\n"
                    f"💼 <b>Total Trades Executed:</b> 0\n"
                    f"🎯 <b>Profitable Trades:</b> 0 ✅\n"
                    f"❌ <b>Losing Trades:</b> 0 🔻\n"
                    f"📈 <b>Win Rate:</b> 0.0%\n\n"
                    f"💸 <b>Total Realized P&L:</b> {pnl_emoji} <b>₹0.00</b>\n"
                    f"===============================\n\n"
                    f"ℹ️ <b>No trades were triggered or executed today.</b> The automated trading core monitored all opening breakout ranges successfully, but no breakout thresholds were breached."
                )

            # Dispatch notification
            await self.send_message(msg)
            return summary
