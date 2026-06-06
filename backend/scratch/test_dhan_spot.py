import os
import sys
import asyncio
from sqlmodel import Session, select
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine as db_engine, BrokerCredential
from app.market_data import DhanMarketDataProvider

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
        print(f"Fetching Nifty 50 for {today_str}...")
        try:
            candles = provider.get_historical_data(
                symbol="NSE:NIFTY 50",
                days=1,
                from_date=today_str,
                to_date=today_str,
                interval="minute"
            )
            print(f"Received {len(candles)} candles.")
            if candles:
                print("First candle:", candles[0])
                print("Last candle:", candles[-1])
        except Exception as e:
            print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
