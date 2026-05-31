import sys
import os
import requests
import json
from sqlmodel import Session, select

backend_dir = "/Users/shady/Content/Nanotricks/Stocker/backend"
sys.path.append(backend_dir)

from app.database import engine as db_engine, BrokerCredential

def get_expiries():
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
        
        # Test 1: Query optionchain without expiry
        url = "https://api.dhan.co/v2/optionchain"
        payload = {
            "UnderlyingScrip": 13,
            "UnderlyingSeg": "IDX_I"
        }
        
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            print("Status without Expiry:", resp.status_code)
            data = resp.json()
            if data.get("status") == "success":
                chain_list = data.get("data", [])
                print(f"Success! Returned {len(chain_list)} items.")
                expiries = set()
                for item in chain_list[:100]:
                    # Check what keys are in chain items
                    exp = item.get("expiry") or item.get("expiryDate")
                    if exp:
                        expiries.add(exp)
                print("Available expiries in first 100 items:", list(expiries))
            else:
                print("Failed response:", data)
        except Exception as e:
            print("Error:", e)

if __name__ == "__main__":
    get_expiries()
