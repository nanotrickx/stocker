import os
import sys
import asyncio
import logging
from sqlmodel import Session, select

# Setup basic logging to console
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("AliceBlue.Tester")

# Adjust python import path to include backend root directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import engine as db_engine, BrokerCredential
from app.broker_manager import get_broker

async def run_tester():
    print("\n=======================================================")
    print("      Stocker Alice Blue API Credential Validator      ")
    print("=======================================================\n")
    
    # 1. Look for existing saved credentials
    client_id = None
    api_key = None
    
    try:
        with Session(db_engine) as session:
            statement = select(BrokerCredential).where(BrokerCredential.broker_name == "aliceblue")
            cred = session.exec(statement).first()
            if cred:
                print(f"🔑 Found saved credentials in stocker.db:")
                print(f"   - Client ID (User ID): {cred.api_key}")
                print(f"   - API Key (ANT Secret): {cred.api_secret[:6]}... [hidden]")
                
                use_saved = input("\nUse these saved credentials? (y/n): ").strip().lower()
                if use_saved == 'y':
                    client_id = cred.api_key
                    api_key = cred.api_secret
    except Exception as e:
        logger.error(f"Error reading local SQLite db: {e}")

    # 2. Prompt for manual credentials if not using saved ones
    if not client_id or not api_key:
        print("\nEnter your Alice Blue API credentials below:")
        client_id = input("👉 Enter Alice Blue CLIENT ID (e.g. AB123456): ").strip()
        api_key = input("👉 Enter Alice Blue API KEY: ").strip()

    if not client_id or not api_key:
        print("❌ Error: Both Client ID and API Key are required.")
        return

    # 3. Instantiate AliceBlueBroker wrapper
    print("\n⏳ Initializing AliceBlueBroker client and establishing connection...")
    broker = get_broker("ALICEBLUE")
    
    # We clear any stale cached session ID for a fresh test run
    credentials = {
        "client_id": client_id,
        "api_key": api_key,
        "access_token": None 
    }

    success = await broker.login(credentials)
    
    if success:
        print("\n🟢 SUCCESS! Authenticated with Alice Blue ANT A3 server successfully!")
        print(f"📝 Generated Daily Session ID: {broker.session_id}")
        
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
        
        # Save validated credentials back to database
        save_db = input("Save these validated credentials to stocker.db database? (y/n): ").strip().lower()
        if save_db == 'y':
            try:
                with Session(db_engine) as session:
                    statement = select(BrokerCredential).where(BrokerCredential.broker_name == "aliceblue")
                    cred = session.exec(statement).first()
                    if not cred:
                        cred = BrokerCredential(broker_name="aliceblue", api_key="", api_secret="")
                    cred.api_key = client_id
                    cred.api_secret = api_key
                    cred.access_token = broker.session_id
                    cred.active = True
                    session.add(cred)
                    session.commit()
                    print("💾 Credentials saved successfully to SQLite 'stocker.db'!")
            except Exception as e:
                print(f"❌ Error saving credentials to database: {e}")
    else:
        print("\n🔴 FAILED! Unable to log in with Alice Blue ANT server.")
        print("❌ Please verify that:")
        print("   1. Your Client ID and API Key are typed correctly.")
        print("   2. You have logged into the web portal at https://ant.aliceblueonline.com today to activate your API session.")
        print("   3. Your account has API trading enabled by Alice Blue.")

if __name__ == "__main__":
    asyncio.run(run_tester())
