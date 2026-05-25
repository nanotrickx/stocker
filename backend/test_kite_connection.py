import os
import sys
import asyncio
import logging
from sqlmodel import Session, select

# Setup basic logging to console
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("Kite.Tester")

# Adjust python import path to include backend root directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import engine as db_engine, BrokerCredential
from app.broker_manager import get_broker

async def run_tester():
    print("\n=======================================================")
    print("      Stocker Zerodha Kite Connect API Validator      ")
    print("=======================================================\n")
    
    # 1. Look for existing saved credentials
    api_key = None
    api_secret = None
    
    try:
        with Session(db_engine) as session:
            statement = select(BrokerCredential).where(BrokerCredential.broker_name == "kite")
            cred = session.exec(statement).first()
            if cred:
                print(f"🔑 Found saved Zerodha credentials in stocker.db:")
                print(f"   - API Key (Connect ID): {cred.api_key}")
                print(f"   - API Secret (Secret Key): {cred.api_secret[:6]}... [hidden]")
                
                use_saved = input("\nUse these saved credentials? (y/n): ").strip().lower()
                if use_saved == 'y':
                    api_key = cred.api_key
                    api_secret = cred.api_secret
    except Exception as e:
        logger.error(f"Error reading local SQLite db: {e}")

    # 2. Prompt for manual credentials if not using saved ones
    if not api_key or not api_secret:
        print("\nEnter your Zerodha Kite Connect Developer Credentials:")
        api_key = input("👉 Enter Kite API Key: ").strip()
        api_secret = input("👉 Enter Kite API Secret: ").strip()

    if not api_key or not api_secret:
        print("❌ Error: Both API Key and API Secret are required.")
        return

    # 3. Inform the user on the Kite Connect OAuth Login redirect process
    print("\n-------------------------------------------------------")
    print("💡 Zerodha Kite Connect OAuth Step:")
    print("Please open the following login link in your browser to authorize your session:")
    print(f"🔗 https://kite.trade/connect/login?api_key={api_key}&v=3")
    print("-------------------------------------------------------")
    print("\nAfter logging in, you will be redirected to a page that looks like:")
    print("👉 http://127.0.0.1:5173/?request_token=YOUR_TOKEN_HERE")
    print("Please copy the long request_token string from your browser address bar!")
    
    request_token = input("\n👉 Enter the copied request_token: ").strip()
    
    if not request_token:
        print("❌ Error: request_token is required to establish authentication session.")
        return

    # 4. Instantiate KiteBroker wrapper
    print("\n⏳ Exchanging request token and authenticating with Kite Server...")
    broker = get_broker("KITE")
    
    credentials = {
        "api_key": api_key,
        "api_secret": api_secret,
        "request_token": request_token,
        "access_token": None 
    }

    success = await broker.login(credentials)
    
    if success:
        print("\n🟢 SUCCESS! Authenticated with Zerodha Kite Connect successfully!")
        print(f"📝 Generated Daily Access Token: {broker.access_token}")
        
        # Fetch profile balances to verify API endpoints
        print("\n⏳ Fetching live cash margins and account limits...")
        profile = await broker.get_profile()
        print("\n================ Account Profile Statistics ================")
        print(f"👤 Account Name   : {profile.get('client_name')}")
        print(f"🆔 Client/User ID  : {profile.get('client_id')}")
        print(f"💵 Available Funds : ₹{profile.get('available_funds'):,.2f}")
        print(f"📊 Used Margins    : ₹{profile.get('used_margin'):,.2f}")
        print(f"💼 Total Equity    : ₹{profile.get('total_equity'):,.2f}")
        print("============================================================\n")
        
        # Save validated credentials back to database and mark as active
        save_db = input("Save and ACTIVATE these credentials in stocker.db? (y/n): ").strip().lower()
        if save_db == 'y':
            try:
                with Session(db_engine) as session:
                    # Deactivate all other live brokers
                    other_creds = session.exec(select(BrokerCredential).where(
                        BrokerCredential.broker_name != "telegram",
                        BrokerCredential.broker_name != "kite"
                    )).all()
                    for oc in other_creds:
                        oc.active = False
                        session.add(oc)
                        
                    # Save / Update Kite credential
                    statement = select(BrokerCredential).where(BrokerCredential.broker_name == "kite")
                    cred = session.exec(statement).first()
                    if not cred:
                        cred = BrokerCredential(broker_name="kite", api_key="", api_secret="")
                    cred.api_key = api_key
                    cred.api_secret = api_secret
                    cred.access_token = broker.access_token
                    cred.active = True
                    session.add(cred)
                    session.commit()
                    print("💾 Zerodha Kite credentials saved and activated successfully in 'stocker.db'!")
            except Exception as e:
                print(f"❌ Error saving credentials to database: {e}")
    else:
        print("\n🔴 FAILED! Unable to exchange request token with Zerodha servers.")
        print("❌ Please verify that:")
        print("   1. Your API Key and API Secret match your Kite Console app exactly.")
        print("   2. The request token you entered is fresh and has not been used or expired.")
        print("   3. Your Kite developer app has 'Connect' type enabled.")

if __name__ == "__main__":
    asyncio.run(run_tester())
