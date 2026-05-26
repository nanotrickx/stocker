import sys
import os
import asyncio
from datetime import date
from sqlmodel import Session, create_engine, select

sys.path.append("/Users/shady/Content/Nanotricks/Stocker/backend")

from app.database import engine, SystemState, DailySummary, Trade, BrokerCredential
from app.telegram_bot import TelegramBot

async def trigger_summary():
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    print(f"Targeting Daily Summary for Date: {today_str}")
    
    with Session(engine) as session:
        # 1. Clear sent flags in SystemState
        state_key = f"daily_summary_sent_{today_str}"
        saved_state = session.exec(select(SystemState).where(SystemState.key == state_key)).first()
        if saved_state:
            print(f"Clearing existing SystemState sent flag: {saved_state.value}")
            session.delete(saved_state)
            session.commit()
            
        # 2. Clear sent flag in DailySummary
        existing_summary = session.exec(select(DailySummary).where(DailySummary.trade_date == today)).first()
        if existing_summary:
            print(f"Removing existing DailySummary row (Trades: {existing_summary.total_trades}, P&L: {existing_summary.net_pnl})")
            session.delete(existing_summary)
            session.commit()

        # Let's count open/closed trades today just to print
        closed_trades = session.exec(select(Trade).where(Trade.status == "CLOSED")).all()
        print(f"Found {len(closed_trades)} total closed trades in the database history.")

    # 3. Instantiate TelegramBot, load credentials from DB, and trigger the report
    bot = TelegramBot()
    with Session(engine) as session:
        cred = session.exec(select(BrokerCredential).where(BrokerCredential.broker_name == "telegram")).first()
        if cred:
            print(f"Loaded active Telegram credentials from DB (Bot Token: {cred.api_key[:8]}..., Chat ID: {cred.api_secret})")
            await bot.update_credentials(cred.api_key, cred.api_secret)
        else:
            print("WARNING: No Telegram credentials found in BrokerCredential table.")

    print("Triggering generate_and_send_daily_summary() via Telegram Bot...")
    summary = await bot.generate_and_send_daily_summary()
    if summary:
        print(f"SUCCESS: EOD Daily Summary dispatched successfully! (Trades: {summary.total_trades}, P&L: ₹{summary.net_pnl})")
    else:
        print("FAILED: EOD Daily Summary returned None.")

if __name__ == "__main__":
    asyncio.run(trigger_summary())
