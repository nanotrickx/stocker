import os
import sys
import asyncio
import logging
import requests
from sqlmodel import Session, select

# Setup basic logging to console
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("Dhan.Tester")

# Adjust python import path to include backend root directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import engine as db_engine, BrokerCredential

async def run_tester():
    print("\n=======================================================")
    print("        Stocker DhanHQ API Credential Validator        ")
    print("=======================================================\n")
    
    # 1. Look for existing saved credentials
    client_id = None
    access_token = None
    
    try:
        with Session(db_engine) as session:
            statement = select(BrokerCredential).where(BrokerCredential.broker_name == "dhan")
            cred = session.exec(statement).first()
            if cred:
                print(f"🔑 Found saved credentials in stocker.db:")
                print(f"   - Client ID: {cred.api_key}")
                print(f"   - Access Token: {cred.api_secret[:15]}... [hidden]")
                
                use_saved = input("\nUse these saved credentials? (y/n): ").strip().lower()
                if use_saved == 'y':
                    client_id = cred.api_key
                    access_token = cred.api_secret
    except Exception as e:
        logger.error(f"Error reading local SQLite db: {e}")

    # 2. Prompt for manual credentials if not using saved ones
    if not client_id or not access_token:
        print("\nEnter your DhanHQ API credentials below:")
        client_id = input("👉 Enter Dhan CLIENT ID: ").strip()
        access_token = input("👉 Enter Dhan JWT ACCESS TOKEN: ").strip()

    if not client_id or not access_token:
        print("❌ Error: Both Client ID and Access Token are required.")
        return

    # 3. Test Connection
    print("\n⏳ Testing connection to Dhan API server...")
    headers = {
        "Content-Type": "application/json",
        "access-token": access_token,
        "client-id": client_id
    }

    try:
        # A. Verify Profile
        profile_url = "https://api.dhan.co/v2/profile"
        profile_resp = requests.get(profile_url, headers=headers, timeout=15)
        
        if profile_resp.status_code == 200:
            profile_data = profile_resp.json()
            client_name = profile_data.get("dhanClientId", "Active Trader")
            
            print("\n🟢 SUCCESS! Authenticated with DhanHQ server successfully!")
            print(f"👤 Account ID      : {profile_data.get('dhanClientId')}")
            print(f"📝 KYC/Segment details : {profile_data.get('tradingSegments', 'ALL')}")
            
            # B. Verify Fund Limit
            print("\n⏳ Fetching live cash margins and fund limits...")
            fund_url = "https://api.dhan.co/v2/fundlimit"
            fund_resp = requests.get(fund_url, headers=headers, timeout=15)
            
            if fund_resp.status_code == 200:
                fund_data = fund_resp.json()
                print("\n================ Account Funds & Margins ================")
                print(f"💵 Available Balance: ₹{float(fund_data.get('availabelBalance', 0)):,.2f}")
                print(f"📊 Utilized Amount  : ₹{float(fund_data.get('utilizedAmount', 0)):,.2f}")
                print(f"📈 Collateral Amount: ₹{float(fund_data.get('collateralAmount', 0)):,.2f}")
                print("=========================================================\n")
            else:
                print(f"⚠️ Warning: Profile authenticated but failed to fetch funds ({fund_resp.status_code})")
                
            # C. Save validated credentials back to database
            save_db = input("Save these validated credentials to stocker.db database? (y/n): ").strip().lower()
            if save_db == 'y':
                try:
                    with Session(db_engine) as session:
                        statement = select(BrokerCredential).where(BrokerCredential.broker_name == "dhan")
                        cred = session.exec(statement).first()
                        if not cred:
                            cred = BrokerCredential(broker_name="dhan", api_key="", api_secret="")
                        cred.api_key = client_id
                        cred.api_secret = access_token
                        cred.active = True
                        session.add(cred)
                        session.commit()
                        print("💾 Credentials saved successfully to SQLite 'stocker.db'!")
                except Exception as e:
                    print(f"❌ Error saving credentials to database: {e}")
        else:
            print(f"\n🔴 FAILED! Dhan API returned status code: {profile_resp.status_code}")
            print(f"❌ Response details: {profile_resp.text}")
            
    except Exception as e:
        print(f"\n🔴 FAILED! Network connection error while communicating with DhanHQ: {e}")

if __name__ == "__main__":
    asyncio.run(run_tester())
