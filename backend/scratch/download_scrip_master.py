import requests
import io
import csv

def check_master():
    print("⏳ Scanning the entire Dhan Master file for all Nifty F&O expiries...")
    url = "https://images.dhan.co/api-data/api-scrip-master.csv"
    
    try:
        resp = requests.get(url, stream=True, timeout=60)
        lines_iterator = resp.iter_lines()
        
        headers_bytes = next(lines_iterator)
        headers = headers_bytes.decode("utf-8", errors="ignore")
        reader = csv.reader(io.StringIO(headers))
        columns = next(reader)
        
        exch_idx = columns.index("SEM_EXM_EXCH_ID")
        sym_idx = columns.index("SEM_TRADING_SYMBOL")
        exp_idx = columns.index("SEM_EXPIRY_DATE")
        inst_idx = columns.index("SEM_INSTRUMENT_NAME")
        
        nifty_expiries = set()
        count = 0
        nifty_count = 0
        
        for line_bytes in lines_iterator:
            if not line_bytes:
                continue
            count += 1
            
            # Fast filter
            if b"NSE" in line_bytes and b"NIFTY" in line_bytes:
                line = line_bytes.decode("utf-8", errors="ignore")
                reader = csv.reader(io.StringIO(line))
                try:
                    row = next(reader)
                    if len(row) > max(exch_idx, sym_idx, exp_idx, inst_idx):
                        if row[exch_idx] == "NSE" and row[inst_idx] == "OPTIDX" and "NIFTY" in row[sym_idx] and not "BANK" in row[sym_idx] and not "FIN" in row[sym_idx] and not "MID" in row[sym_idx]:
                            nifty_expiries.add(row[exp_idx])
                            nifty_count += 1
                except Exception:
                    pass
                    
        print(f"Processed {count} lines. Found {nifty_count} NIFTY-only OPTIDX contracts.")
        print("\nAll Unique Expiry Dates found in Nifty Options:")
        for exp in sorted(list(nifty_expiries)):
            print(f"  - {exp}")
            
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    check_master()
