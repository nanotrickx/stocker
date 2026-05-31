import sys
import os
from sqlmodel import Session, select

# Add backend directory to sys.path
sys.path.append("/Users/shady/Content/Nanotricks/Stocker/backend")

from app.database import engine as db_engine, BrokerCredential, StrategyInstance
from app.orb_strategy import ORBStrategyEngine
from app.market_data import DhanMarketDataProvider, KiteMarketDataProvider
import pandas as pd

def main():
    print("=== Running ORB Strategy Backtest for 27-May-2026 ===")
    
    with Session(db_engine) as session:
        # Get active broker session
        active_cred = session.exec(
            select(BrokerCredential).where(
                BrokerCredential.broker_name != "telegram",
                BrokerCredential.active == True
            )
        ).first()
        
        if not active_cred:
            print("Error: No active broker credentials found.")
            return

        token = active_cred.access_token or (active_cred.api_secret if active_cred.broker_name == "dhan" else None)
        print(f"Using active broker: {active_cred.broker_name.upper()} (API Key: {active_cred.api_key})")
        
        if active_cred.broker_name == "dhan":
            provider = DhanMarketDataProvider(
                client_id=active_cred.api_key,
                access_token=token
            )
        else:
            provider = KiteMarketDataProvider(
                api_key=active_cred.api_key,
                access_token=token
            )

        # Get first ORB strategy instance to use its config
        instance = session.exec(select(StrategyInstance)).first()
        if not instance:
            print("Error: No StrategyInstance templates found in database.")
            return
            
        print(f"Using Strategy Template Config from: {instance.name}")
        config = instance.get_config()
        
        # We target NSE:NIFTY 50 on 2026-05-27
        symbol = "NSE:NIFTY 50"
        from_date = "2026-05-27"
        to_date = "2026-05-27"
        expiry_date = "28-May-2026"
        
        print(f"Fetching 1-min index spot candles for {symbol} on {from_date}...")
        try:
            candles = provider.get_historical_data(
                symbol=symbol,
                days=1,
                from_date=from_date,
                to_date=to_date,
                interval="minute",
                instrument_type="STOCK"
            )
        except Exception as e:
            print(f"Error fetching historical data: {e}")
            return
            
        if not candles:
            print("Error: No candles fetched. Please check if Dhan/Kite session is authenticated/valid.")
            return
            
        print(f"Successfully fetched {len(candles)} intraday candles.")
        
        # Build Spot DataFrame
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
        
        # Instantiate ORB strategy and run backtest
        engine = ORBStrategyEngine(config)
        result = engine.run_backtest(
            df,
            initial_capital=100000.0,
            provider=provider,
            expiry_date=expiry_date
        )
        
        # Print results
        print("\n================ BACKTEST SUMMARY ==================")
        summary = result["summary"]
        print(f"Strategy:         {instance.name}")
        print(f"Initial Capital:  ₹{summary['initial_capital']:,.2f}")
        print(f"Final Capital:    ₹{summary['final_capital']:,.2f}")
        print(f"Net realized P&L: {'🟩 +' if summary['net_pnl'] >= 0 else '🟥 '}₹{summary['net_pnl']:,.2f}")
        print(f"Win Rate:         {summary['win_rate']:.1f}%")
        print(f"Total Trades:     {summary['total_trades']}")
        print(f"Profitable:       {summary['profitable_trades']}")
        print(f"Losing:           {summary['losing_trades']}")
        print("====================================================")
        
        print("\n================ DETAILED TRADE LOG ================")
        for idx, t in enumerate(result["trades"], 1):
            indicator = "🟩" if t["pnl"] >= 0 else "🟥"
            print(f"{idx}. {indicator} Option symbol: {t['symbol']}")
            print(f"   • Qty: {t['qty']}")
            print(f"   • Entry: ₹{t['entry_price']:.2f} ({t['entry_time']})")
            print(f"   • Exit:  ₹{t['exit_price']:.2f} ({t['exit_time']}) [{t['exit_reason']}]")
            print(f"   • P&L:   ₹{t['pnl']:,.2f} ({t['pnl_pct']}%)")
            
            # Print strategy parameters
            if t.get("opening_high") is not None:
                print(f"   • Index Opening Range: H {t['opening_high']:.2f} | L {t['opening_low']:.2f}")
                print(f"   • CE {t['selected_ce_strike']:.0f} Opening High: ₹{t['ce_option_opening_high']:.2f}")
                print(f"   • PE {t['selected_pe_strike']:.0f} Opening High: ₹{t['pe_option_opening_high']:.2f}")
            print()
        print("====================================================")

if __name__ == "__main__":
    main()
