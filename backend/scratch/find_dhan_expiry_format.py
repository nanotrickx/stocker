import sys
import os
import requests
import time
from sqlmodel import Session, select

backend_dir = "/Users/shady/Content/Nanotricks/Stocker/backend"
sys.path.append(backend_dir)

from app.database import engine as db_engine, BrokerCredential

def test_formats():
    with Session(db_engine) as session:
        cred = session.exec(select(BrokerCredential).where(BrokerCredential.broker_name == "dhan")).first()
        if not cred:
            print("No Dhan credentials found.")
            return
            
        headers = {
            "Content-Type": "application/json",
            "access-token": cred.api_secret,
            "client-id": cred.api_key,
        }
        
        # Test Nifty June 2nd expiry formats
        formats_to_test = [
            "02-Jun-2026",
            "02-JUN-2026",
            "2026-06-02",
        ]
        
        url = "https://api.dhan.co/v2/optionchain"
        
        for fmt in formats_to_test:
            print(f"\n⏳ Testing format: {fmt} ...")
            payload = {
                "UnderlyingScrip": 13,
                "UnderlyingSeg": "IDX_I",
                "Expiry": fmt
            }
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=10)
                data = resp.json()
                print(f"Format '{fmt}': Status {resp.status_code} | Result status: {data.get('status')} | Keys: {list(data.keys())}")
                if data.get("status") == "success" and data.get("data"):
                    print(f"  -> SUCCESS! First item: {data.get('data')[0].get('strike')} | Expiry resolved!")
                    break
                else:
                    print(f"  -> FAILED: {data}")
            except Exception as e:
                print(f"Format '{fmt}': Error: {e}")
            print("⏳ Sleeping 4 seconds to respect rate limits...")
            time.sleep(4)

if __name__ == "__main__":
    test_formats()
