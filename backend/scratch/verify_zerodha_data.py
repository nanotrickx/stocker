import sys
import os
from datetime import datetime, date
from sqlmodel import Session, create_engine, select

sys.path.append("/Users/shady/Content/Nanotricks/Stocker/backend")

from app.database import BrokerCredential
from kiteconnect import KiteConnect

engine = create_engine("sqlite:////Users/shady/Content/Nanotricks/Stocker/backend/stocker.db")

def verify_data():
    with Session(engine) as session:
        cred = session.exec(select(BrokerCredential).where(
            BrokerCredential.broker_name == "kite",
            BrokerCredential.active == True
        )).first()
        
        if not cred or not cred.access_token:
            print("ERROR: No active Kite credentials/access token found.")
            return
            
        kite = KiteConnect(api_key=cred.api_key)
        kite.set_access_token(cred.access_token)
        
        print("Fetching instruments to find exact symbol for Nifty 23950 CE...")
        try:
            instruments = kite.instruments("NFO")
            # Filter for NIFTY, 23950 strike, CE type
            options = [inst for inst in instruments if inst["name"] == "NIFTY" and inst["strike"] == 23950.0 and inst["instrument_type"] == "CE"]
            
            if not options:
                print("No active 23950 CE options found.")
                return
                
            # Print the options contracts found
            print("\nFound Option Contracts:")
            for opt in options:
                print(f"Trading Symbol: {opt['tradingsymbol']}, Token: {opt['instrument_token']}, Expiry: {opt['expiry']}")
                
            # Let's fetch historical 1-minute data for today (May 26, 2026) for each of these contracts
            today = date(2026, 5, 26)
            for opt in options[:2]:
                symbol = opt['tradingsymbol']
                token = opt['instrument_token']
                print(f"\n--- 1-Min Candle Data for {symbol} today ---")
                try:
                    candles = kite.historical_data(
                        instrument_token=token,
                        from_date=today,
                        to_date=today,
                        interval="minute"
                    )
                    
                    if not candles:
                        print("No candle data returned.")
                        continue
                        
                    for c in candles:
                        c_time = c["date"].strftime("%H:%M:%S")
                        # Print only key timeframe of interest (09:15 to 09:40)
                        if "09:15" <= c_time <= "09:40":
                            print(f"Time: {c_time} | O: {c['open']} | H: {c['high']} | L: {c['low']} | C: {c['close']}")
                except Exception as ex:
                    print(f"Error fetching candles for {symbol}: {ex}")
                    
        except Exception as e:
            print(f"Error querying Kite: {e}")

if __name__ == "__main__":
    verify_data()
