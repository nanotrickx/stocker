import os
import sys
import asyncio
import json
import logging
from datetime import datetime
import pandas as pd
from sqlmodel import Session, select

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine as db_engine, BrokerCredential
from app.market_data import DhanMarketDataProvider
from app.orb_strategy import ORBStrategyEngine, DEFAULT_ORB_CONFIG

# Enable logging to see the inner workings of backtesting
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

async def main():
    with Session(db_engine) as session:
        statement = select(BrokerCredential).where(BrokerCredential.broker_name == "dhan")
        cred = session.exec(statement).first()
        if not cred:
            print("No Dhan credentials found.")
            return
        
        token = cred.access_token or cred.api_secret
        provider = DhanMarketDataProvider(client_id=cred.api_key, access_token=token)
        
        today_str = datetime.now().strftime("%Y-%m-%d")
        print(f"Fetching Nifty 50 spot candles for {today_str}...")
        
        try:
            candles = provider.get_historical_data(
                symbol="NSE:NIFTY 50",
                days=1,
                from_date=today_str,
                to_date=today_str,
                interval="minute"
            )
            print(f"Loaded {len(candles)} spot candles.")
            if not candles:
                print("No candles fetched.")
                return
            
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
            
            # Use June 4th, 2026 (Thursday) as the expiry date
            expiry_date = "2026-06-04"
            print(f"Running ORB backtest with expiry={expiry_date}...")
            
            orb = ORBStrategyEngine(DEFAULT_ORB_CONFIG)
            result = orb.run_backtest(
                df=df,
                initial_capital=100000.0,
                provider=provider,
                expiry_date=expiry_date
            )
            
            print("\n================ BACKTEST RESULTS ================")
            print(json.dumps(result.get("meta", {}), indent=2))
            print(f"PNL: Rs {result.get('summary', {}).get('net_pnl', 0.0)}")
            print(f"Return: {result.get('summary', {}).get('return_pct', 0.0)}%")
            print(f"Total Trades: {result.get('summary', {}).get('total_trades', 0)}")
            
            print("\n================ TRADES ================")
            for t in result.get("trades", []):
                print(f"Trade: {t['symbol']}")
                print(f"  Entry: {t['entry_time']} @ Rs {t['entry_price']:.2f}")
                print(f"  Exit: {t['exit_time']} @ Rs {t['exit_price']:.2f} ({t['exit_reason']})")
                print(f"  PnL: Rs {t['pnl']:.2f} ({t['pnl_pct']:.2f}%)")
                print(f"  Trigger Info:")
                print(f"    Index Opening High: {t['opening_high']:.2f}, Low: {t['opening_low']:.2f}")
                print(f"    Option CE Opening High: {t['ce_option_opening_high']:.2f}")
                print(f"    Option PE Opening High: {t['pe_option_opening_high']:.2f}")
                
            print("\n================ JOURNAL ================")
            for j in result.get("journal", []):
                if j["action"] in ["REFERENCE", "BUY", "SELL"]:
                    print(f"[{j['ts']}] {j['action']} @ Rs {j['price']:.2f} - Note: {j['note']}")
                    for r in j["reason"]:
                        print(f"  - {r}")
                        
        except Exception as e:
            print("Error running backtest:", e)
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
